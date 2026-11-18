"""
NexusProcure - Supplier Simulator (Seller Agent Node).

Responsible for:
1. Simulating vendor counter-responses bound by economic floor (min_price) and cost_basis.
2. Generating natural commercial reasoning protecting supplier margin and highlighting product value.
3. Returning structured output conforming to SellerOffer schema via llm.with_structured_output.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.models.schemas import SellerOffer
from app.graph.state import NegotiationState

logger = logging.getLogger(__name__)


SELLER_SYSTEM_PROMPT = """\
Bạn là Sales Director đại diện cho nhà cung cấp {supplier_name}.
Mục tiêu của bạn là bảo vệ mức giá bán cao nhất có thể nhằm duy trì biên lợi nhuận,
đồng thời sẵn sàng nhượng bộ từng bước nếu bên mua thiện chí để đạt được đơn hàng.

QUY TẮC NGÔN NGỮ TUYỆT ĐỐI (CRITICAL LANGUAGE REQUIREMENT):
- BẮT BUỘC trả lời và lập luận (reasoning, concessions_made) hoàn toàn bằng 100% TIẾNG VIỆT CHUẨN MỰC THƯƠNG MẠI.
- TUYỆT ĐỐI KHÔNG DÙNG TIẾNG ANH (STRICTLY NO ENGLISH). Mọi câu phát biểu chào giá, chứng minh chất lượng, bảo hành phải là tiếng Việt tự nhiên và chuyên nghiệp.

RÀNG BUỘC KINH TẾ (SELLER CONSTRAINTS):
- Mặt hàng: {product_name}
- Số lượng: {quantity:,} chiếc
- Giá chào bán ban đầu (Seller Target): {seller_target:,.0f} {currency}
- Giá sàn tối thiểu (Minimum Floor Price): {min_price:,.0f} {currency} (TUYỆT ĐỐI KHÔNG BÁN THẤP HƠN MỨC NÀY)
- Giá vốn hàng bán (Cost Basis): {cost_basis:,.0f} {currency}

NGUYÊN TẮC CHIẾN LƯỢC:
1. Tại Vòng 1: Bắt buộc chào đúng Giá chào bán ban đầu ({seller_target:,.0f} {currency}) làm giá mở màn thương thảo, đưa ra lý lẽ khẳng định giá trị chất lượng, xuất xứ và bảo hành.
2. Từ Vòng 2 trở đi: Không giảm giá đột ngột; giảm từng bước nhỏ tương ứng với mức giá bên mua nâng lên.
3. Tuyệt đối không bao giờ chào giá thấp hơn Giá Sàn ({min_price:,.0f} {currency}) và không bao giờ tăng giá so với vòng trước.
4. Nếu là nhà máy sản xuất trực tiếp (như Winstar) và số lượng đặt ({quantity} chiếc) thấp hơn ngưỡng lô chuẩn MOQ 500 chiếc của nhà máy: Hãy nêu rõ trong lý lẽ (reasoning) về quy định số lượng tối thiểu MOQ 500 chiếc hoặc phụ phí gia công lô nhỏ, và gợi ý bên mua cam kết hợp đồng khung dài hạn để được giá tốt.
"""

SELLER_HUMAN_PROMPT = """\
THÔNG TIN HIỆN TẠI (VÒNG {current_round}):
- Báo giá chào mua của Buyer: {buyer_price:,.0f} {currency}
- Lý lẽ của Buyer: "{buyer_reasoning}"
- Giá chào gần nhất của Bên bán: {last_seller_price:,.0f} {currency}

YÊU CẦU ĐÀM PHÁN (PHẢI TRẢ LỜI BẰNG 100% TIẾNG VIỆT):
- Ở Vòng 1: Mức giá chào bán (offer_price) BẮT BUỘC phải là chính xác Giá chào bán ban đầu: {seller_target:,.0f} {currency}. Lập luận bằng TIẾNG VIỆT khẳng định uy tín, chất lượng và bảo hành.
- Từ Vòng 2 trở đi: Tính toán mức giá chào bán điều chỉnh giảm dần từng bước (offer_price <= giá vòng trước) để đáp lại thiện chí bên mua. Lập luận bằng TIẾNG VIỆT.
"""


def _build_seller_llm():
    """Build LLM instance with structured output."""
    if settings.GROQ_API_KEY:
        try:
            from langchain_groq import ChatGroq
            llm = ChatGroq(
                model=settings.GROQ_STRATEGIC_MODEL,
                api_key=settings.GROQ_API_KEY,
                temperature=settings.GROQ_TEMPERATURE_STRATEGIC,
                max_retries=1,
                timeout=12.0,
            )
            return llm.with_structured_output(SellerOffer)
        except Exception as e:
            logger.warning("[SellerAgent] LLM init error: %s. Using heuristic fallback.", e)
    return None


def _heuristic_seller_ask(
    current_round: int,
    seller_target: float,
    min_price: float,
    buyer_price: float,
    currency: str,
    last_seller_price: Optional[float] = None,
    supplier_name: str = "Bên bán",
    product_name: str = "Thiết bị",
    quantity: int = 100,
) -> SellerOffer:
    """Heuristic concession logic respecting floor price, domain specialty, and strict monotonicity."""
    from app.data.database import check_supplier_item_compatibility
    compat = check_supplier_item_compatibility(product_name, supplier_name)

    if current_round <= 1:
        offer = round(seller_target, -3) if currency == "VNĐ" else seller_target
        if not compat.get("is_compatible", True):
            reasoning = (
                f"Báo giá khởi điểm {offer:,.0f} {currency}. Vì {product_name} là mặt hàng ngoài danh mục sản xuất chính "
                f"của {supplier_name}, báo giá đã bao gồm chi phí nhập ủy thác đặc biệt và cam kết bảo hành tiêu chuẩn."
            )
            concessions = ["Cam kết bảo hành chính hãng 12 tháng"]
        elif "winstar" in supplier_name.lower() and quantity < 500:
            reasoning = (
                f"Báo giá khởi điểm {offer:,.0f} {currency}. Nhà máy Winstar thông thường áp dụng số lượng tối thiểu "
                f"(MOQ) 500 chiếc để có giá xuất xưởng. Với đơn hàng {quantity:,} chiếc, chúng tôi tính phụ phí khởi động dây chuyền, "
                f"nhưng sẵn sàng chiết khấu nếu quý công ty cam kết hợp đồng khung chia đợt."
            )
            concessions = ["Hỗ trợ đơn hàng 300 chiếc dưới ngưỡng MOQ 500 chiếc nếu ký hợp đồng khung"]
        else:
            reasoning = (
                f"Báo giá khởi điểm {offer:,.0f} {currency} phản ánh chất lượng linh kiện đạt chuẩn từ {supplier_name}, "
                f"kèm gói bảo hành chính hãng và hỗ trợ kỹ thuật tận nơi."
            )
            concessions = ["Cam kết bảo hành chính hãng 12 tháng"]
    else:
        # Base price must be the previous seller offer to ensure seller NEVER raises price
        prev_price = last_seller_price if (last_seller_price is not None and last_seller_price > 0) else seller_target
        gap = prev_price - buyer_price
        if gap > 0 and prev_price > min_price:
            step = max(1000.0, round(gap * 0.35, -3)) if currency == "VNĐ" else max(1.0, round(gap * 0.35, 2))
            offer = max(min_price, round(prev_price - step, -3 if currency == "VNĐ" else 2))
        else:
            offer = min_price

        # Strict monotonicity: offer cannot exceed previous price
        offer = min(prev_price, offer)
        concession_val = prev_price - offer

        if concession_val > 0:
            reasoning = (
                f"Để hỗ trợ quý công ty và thể hiện thiện chí hợp tác lâu dài, chúng tôi điều chỉnh giá xuống "
                f"{offer:,.0f} {currency} (giảm {concession_val:,.0f} {currency}), cam kết giao hàng đúng tiến độ."
            )
            concessions = [f"Giảm giá chào xuống {offer:,.0f} {currency}"]
        else:
            reasoning = (
                f"Mức giá {offer:,.0f} {currency} đã là mức giá sàn kịch khung của {supplier_name}. "
                f"Chúng tôi không thể giảm thêm nhưng cam kết hỗ trợ kỹ thuật tối đa và đảm bảo tiến độ."
            )
            concessions = ["Giữ mức giá sàn kỹ thuật tối ưu"]

    return SellerOffer(
        offer_price=offer,
        reasoning=reasoning,
        concessions_made=concessions,
        lead_time_days=7,
        payment_terms="Net 30",
        warranty_months=12,
    )


def seller_node(state: NegotiationState) -> Dict[str, Any]:
    """
    LangGraph Node: [seller]
    Executes Seller Agent reasoning and generates structured counter-response.
    """
    logger.info("[SellerNode] Generating supplier response...")

    current_round = state.get("current_round", 1)
    s_tgt = float(state.get("seller_target", 48000))
    s_floor = float(state.get("min_price", 30000))
    s_cost = float(state.get("cost_basis", 25000))
    product_name = state.get("product_name", "Thiết bị")
    quantity = int(state.get("quantity", 100))
    currency = state.get("currency", "$")
    supplier_name = state.get("supplier_name", "Đối tác Cung ứng")

    buyer_offer = state.get("buyer_offer", {})
    buyer_price = float(buyer_offer.get("offer_price", state.get("target_price", s_floor)))
    buyer_reasoning = buyer_offer.get("reasoning", "Đề xuất đàm phán.")

    history = state.get("history", [])
    if history:
        last_seller_price = float(history[-1].get("seller_ask", s_tgt))
    else:
        last_seller_offer = state.get("seller_offer", {})
        last_seller_price = float(last_seller_offer.get("offer_price", s_tgt))

    candidate_models = list(dict.fromkeys([
        settings.GROQ_STRATEGIC_MODEL,
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    ]))

    seller_offer_obj = None
    last_error_msg = None

    if settings.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        prompt = ChatPromptTemplate.from_messages([
            ("system", SELLER_SYSTEM_PROMPT),
            ("human", SELLER_HUMAN_PROMPT),
        ])
        for model_name in candidate_models:
            if not model_name:
                continue
            try:
                llm = ChatGroq(
                    model=model_name,
                    api_key=settings.GROQ_API_KEY,
                    temperature=settings.GROQ_TEMPERATURE_STRATEGIC,
                    max_retries=1,
                    timeout=10.0,
                ).with_structured_output(SellerOffer)
                chain = prompt | llm
                seller_offer_obj = chain.invoke({
                    "supplier_name": supplier_name,
                    "product_name": product_name,
                    "quantity": quantity,
                    "seller_target": s_tgt,
                    "min_price": s_floor,
                    "cost_basis": s_cost,
                    "currency": currency,
                    "current_round": current_round,
                    "buyer_price": buyer_price,
                    "buyer_reasoning": buyer_reasoning,
                    "last_seller_price": last_seller_price,
                })
                seller_offer_obj.engine = f"LLM ({model_name})"
                seller_offer_obj.api_warning = None
                break
            except Exception as e:
                last_error_msg = str(e)
                logger.warning("[SellerNode] Model %s failed: %s. Trying next...", model_name, e)

    if not seller_offer_obj:
        if last_error_msg and ("429" in last_error_msg or "rate_limit" in last_error_msg.lower()):
            warning_text = "Hết hạn ngạch API Groq (Rate Limit 429). Hệ thống tự động chuyển sang thuật toán Heuristic toán học."
        elif last_error_msg:
            warning_text = f"API LLM không phản hồi. Hệ thống chuyển sang thuật toán Heuristic toán học."
        else:
            warning_text = "Không tìm thấy cấu hình API. Đang chạy chế độ Heuristic ngoại tuyến."

        seller_offer_obj = _heuristic_seller_ask(
            current_round=current_round,
            seller_target=s_tgt,
            min_price=s_floor,
            buyer_price=buyer_price,
            currency=currency,
            last_seller_price=last_seller_price,
            supplier_name=supplier_name,
            product_name=product_name,
            quantity=int(state.get("quantity", 100)),
        )
        seller_offer_obj.engine = "HEURISTIC"
        seller_offer_obj.api_warning = warning_text

    # Guardrail 0: In Round 1, Seller MUST open with the exact initial ask (s_tgt)
    if current_round <= 1:
        seller_offer_obj.offer_price = s_tgt

    # Guardrail 1: Hard floor price is respected
    if seller_offer_obj.offer_price < s_floor:
        seller_offer_obj.offer_price = s_floor

    # Guardrail 2: Monotonicity - Seller must NEVER raise price in subsequent rounds
    if current_round > 1 and last_seller_price > 0:
        if seller_offer_obj.offer_price > last_seller_price:
            logger.warning(
                "[SellerNode] Seller proposed %.0f > last round %.0f. Clamping to <= %.0f.",
                seller_offer_obj.offer_price, last_seller_price, last_seller_price
            )
            step = max(1000.0, round((last_seller_price - max(s_floor, buyer_price)) * 0.25, -3))
            seller_offer_obj.offer_price = max(s_floor, round(last_seller_price - step, -3))
            seller_offer_obj.offer_price = min(last_seller_price, seller_offer_obj.offer_price)

    # Guardrail 3: Clean rounding for VNĐ
    if currency == "VNĐ":
        seller_offer_obj.offer_price = round(seller_offer_obj.offer_price, -3)

    return {"seller_offer": seller_offer_obj.model_dump()}

