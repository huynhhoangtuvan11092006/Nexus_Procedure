"""
NexusProcure - Strategic Buyer Agent Node.

Responsible for:
1. Grounding counter-offers with ChromaDB RAG market benchmarks.
2. Incorporating Buyer Constraints (Target Price, Budget Ceiling) and injected human guidance.
3. Returning structured output conforming to BuyerOffer schema via llm.with_structured_output.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.models.schemas import BuyerOffer
from app.graph.state import NegotiationState

logger = logging.getLogger(__name__)


BUYER_SYSTEM_PROMPT = """\
Bạn là Strategic Buyer Agent (Đại diện Mua hàng chiến lược) của doanh nghiệp Việt Nam.
Mục tiêu của bạn là đàm phán kéo giá xuống mức hợp lý nhất nhưng vẫn đạt được thỏa thuận, đảm bảo lợi ích tối đa cho công ty.

QUY TẮC NGÔN NGỮ TUYỆT ĐỐI (CRITICAL LANGUAGE REQUIREMENT):
- BẮT BUỘC trả lời và lập luận (reasoning, concessions_made, benchmark_references) hoàn toàn bằng 100% TIẾNG VIỆT CHUẨN MỰC THƯƠNG MẠI.
- TUYỆT ĐỐI KHÔNG DÙNG TIẾNG ANH (STRICTLY NO ENGLISH). Mọi câu chào, phân tích, lập luận phải là tiếng Việt tự nhiên và sắc sảo.

RÀNG BUỘC MUA HÀNG (BUYER CONSTRAINTS):
- Mặt hàng: {product_name}
- Số lượng: {quantity:,} chiếc
- Giá mục tiêu kỳ vọng (Target Price): {target_price:,.0f} {currency}
- Ngân sách trần tối đa (Budget Ceiling): {budget_ceiling:,.0f} {currency} (TUYỆT ĐỐI KHÔNG CHÀO VƯỢT MỨC NÀY)

THÔNG TIN THỊ TRƯỜNG & HỢP ĐỒNG LỊCH SỬ (RAG GROUNDING):
{rag_benchmarks}

CHỈ ĐẠO TRỰC TIẾP TỪ QUẢN LÝ (HUMAN INJECTION NẾU CÓ):
{injected_instruction}

NGUYÊN TẮC CHIẾN LƯỢC:
1. Tại Vòng 1: Bắt buộc chào đúng Giá mục tiêu kỳ vọng ({target_price:,.0f} {currency}) làm mức giá mở đầu. Từ các vòng sau nhượng bộ chậm dần (Round {current_round}/{max_rounds}) tiến dần về vùng thỏa hiệp.
2. Luôn đưa ra lý lẽ dựa trên số lượng đơn hàng, tiến độ giao và cam kết thanh toán nhanh (Net 15). Nếu có CHỈ ĐẠO TRỰC TIẾP TỪ QUẢN LÝ (như cần hàng khẩn cấp cứu dây chuyền sản xuất), hãy nhấn mạnh yêu cầu giao hàng hỏa tốc trong 2-3 ngày.
3. Đưa ra danh sách các nhượng bộ cụ thể và trích dẫn căn cứ benchmark nếu có.
4. Nếu Bên bán (như Winstar) đề cập đến số lượng đặt hàng tối thiểu MOQ (500 chiếc), hãy khéo léo đề xuất giải pháp hợp đồng khung chia 2 đợt hoặc thanh toán Net 15 để được hưởng đơn giá xuất xưởng ưu đãi.
"""

BUYER_HUMAN_PROMPT = """\
THÔNG TIN HIỆN TẠI (VÒNG {current_round}):
- Báo giá chào mới nhất của Bên bán: {seller_price:,.0f} {currency}
- Lý lẽ của Bên bán: "{seller_reasoning}"
- Lịch sử đàm phán các vòng trước:
{history_summary}

YÊU CẦU ĐÀM PHÁN (PHẢI TRẢ LỜI BẰNG 100% TIẾNG VIỆT):
- Ở Vòng 1: Mức giá đề xuất (offer_price) BẮT BUỘC phải là chính xác Giá mục tiêu kỳ vọng: {target_price:,.0f} {currency}. Lập luận thuyết phục mở màn bằng TIẾNG VIỆT dựa trên số lượng lớn và thanh toán Net 15.
- Từ Vòng 2 trở đi: Tính toán mức giá mua đề xuất mới nâng dần từng bước (offer_price >= giá vòng trước) để thu hẹp khoảng cách. Lập luận bằng TIẾNG VIỆT.
"""


def _build_buyer_llm():
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
            return llm.with_structured_output(BuyerOffer)
        except Exception as e:
            logger.warning("[BuyerAgent] LLM init error: %s. Using heuristic fallback.", e)
    return None


def _heuristic_buyer_bid(
    current_round: int,
    budget_ceiling: float,
    target_price: float,
    seller_price: float,
    injected_instruction: Optional[str],
    currency: str,
    last_buyer_price: Optional[float] = None,
    rag_benchmarks: Optional[List[str]] = None,
) -> BuyerOffer:
    """Heuristic logic ensuring robust execution even offline with strict monotonicity."""
    has_history = any("Hợp đồng mua sắm #" in b for b in (rag_benchmarks or []))

    if current_round <= 1:
        offer = round(target_price, -3) if currency == "VNĐ" else target_price
        if injected_instruction:
            reasoning = (
                f"Đơn hàng khẩn cấp: '{injected_instruction}'. "
                f"Chúng tôi đề xuất mức giá khởi điểm {offer:,.0f} {currency} và thanh toán Net 15, "
                f"đổi lại yêu cầu quý đối tác cam kết giao hàng hỏa tốc trong 2-3 ngày để tránh gián đoạn sản xuất."
            )
            concessions = [f"Chấp nhận giá khởi điểm {offer:,.0f} {currency} đổi lấy giao hỏa tốc 2-3 ngày"]
        elif has_history:
            reasoning = (
                f"Chúng tôi đề xuất mức giá khởi điểm {offer:,.0f} {currency} căn cứ vào dữ liệu hợp đồng quá khứ "
                f"và cam kết thanh toán Net 15 để hỗ trợ dòng tiền của quý đối tác."
            )
            concessions = [f"Cam kết thanh toán nhanh Net 15"]
        else:
            reasoning = (
                f"Vì đây là mặt hàng chưa có dữ liệu hợp đồng đối chiếu, chúng tôi đề xuất giá mở đầu {offer:,.0f} {currency} "
                f"dựa trên định mức dự toán và cam kết thanh toán nhanh Net 15 để đôi bên cùng có lợi."
            )
        concessions = [f"Cam kết thanh toán nhanh Net 15"]
    else:
        prev_price = last_buyer_price if (last_buyer_price is not None and last_buyer_price > 0) else target_price
        gap = seller_price - prev_price
        if gap > 0 and prev_price < budget_ceiling:
            step = max(1000.0, round(gap * 0.30, -3)) if currency == "VNĐ" else max(1.0, round(gap * 0.30, 2))
            offer = min(budget_ceiling, round(prev_price + step, -3 if currency == "VNĐ" else 2))
        else:
            offer = budget_ceiling

        # Strict monotonicity: buyer cannot lower offer
        offer = max(prev_price, offer)
        concession_val = offer - prev_price

        if injected_instruction:
            reasoning = (
                f"Theo chỉ đạo của Quản lý: '{injected_instruction}'. "
                f"Chúng tôi điều chỉnh đề xuất lên {offer:,.0f} {currency} nhằm thiện chí chốt hợp đồng."
            )
            concessions = [f"Nâng giá lên {offer:,.0f} {currency} theo chỉ đạo Quản lý"]
        elif concession_val > 0:
            reasoning = (
                f"Chúng tôi tiếp tục thiện chí nâng giá đề xuất lên {offer:,.0f} {currency} "
                f"(tăng {concession_val:,.0f} {currency}) để thu hẹp khoảng cách với mức chào của bên bán."
            )
            concessions = [f"Nâng giá đề xuất lên {offer:,.0f} {currency}"]
        else:
            reasoning = (
                f"Mức đề xuất {offer:,.0f} {currency} đã chạm trần ngân sách cho phép. "
                f"Chúng tôi mong quý đối tác xem xét để tiến tới ký kết hợp đồng."
            )
            concessions = ["Giữ mức giá trần ngân sách"]

    bench_refs = [b for b in (rag_benchmarks or []) if "Hợp đồng mua sắm #" in b]
    if not bench_refs:
        bench_refs = ["Định mức chi phí danh mục (Không có hợp đồng cũ)"]

    return BuyerOffer(
        offer_price=offer,
        reasoning=reasoning,
        concessions_made=concessions,
        benchmark_references=bench_refs[:2],
        lead_time_days=7,
        payment_terms="Net 15",
    )


def buyer_node(state: NegotiationState) -> Dict[str, Any]:
    """
    LangGraph Node: [buyer]
    Executes Buyer Agent reasoning and generates structured counter-offer.
    """
    logger.info("[BuyerNode] Generating strategic counter-offer...")

    current_round = state.get("current_round", 1)
    max_rounds = state.get("max_rounds", 10)
    b_ceil = float(state.get("budget_ceiling", 50000))
    b_tgt = float(state.get("target_price", 35000))
    product_name = state.get("product_name", "Thiết bị")
    quantity = int(state.get("quantity", 100))
    currency = state.get("currency", "$")
    benchmarks = state.get("rag_benchmarks", [])
    injected = state.get("injected_instruction") or "Không có chỉ đạo ghi đè."

    last_seller_offer = state.get("seller_offer", {})
    seller_price = float(last_seller_offer.get("offer_price", state.get("seller_target", b_ceil * 1.2)))
    seller_reasoning = last_seller_offer.get("reasoning", "Báo giá khởi điểm.")

    history = state.get("history", [])
    if history:
        last_buyer_price = float(history[-1].get("buyer_bid", b_tgt))
    else:
        last_buyer_offer = state.get("buyer_offer", {})
        last_buyer_price = float(last_buyer_offer.get("offer_price", b_tgt))

    history_str = "\n".join([
        f"- Vòng {h['round']}: Buyer chào {h['buyer_bid']:,.0f} {currency} | Seller chào {h['seller_ask']:,.0f} {currency}"
        for h in history
    ]) if history else "Vòng đàm phán đầu tiên."

    candidate_models = list(dict.fromkeys([
        settings.GROQ_STRATEGIC_MODEL,
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    ]))
    
    buyer_offer_obj = None
    last_error_msg = None

    if settings.GROQ_API_KEY:
        from langchain_groq import ChatGroq
        prompt = ChatPromptTemplate.from_messages([
            ("system", BUYER_SYSTEM_PROMPT),
            ("human", BUYER_HUMAN_PROMPT),
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
                ).with_structured_output(BuyerOffer)
                chain = prompt | llm
                buyer_offer_obj = chain.invoke({
                    "product_name": product_name,
                    "quantity": quantity,
                    "target_price": b_tgt,
                    "budget_ceiling": b_ceil,
                    "currency": currency,
                    "current_round": current_round,
                    "max_rounds": max_rounds,
                    "rag_benchmarks": "\n".join(benchmarks) if benchmarks else "Không có dữ liệu RAG.",
                    "injected_instruction": injected,
                    "seller_price": seller_price,
                    "seller_reasoning": seller_reasoning,
                    "history_summary": history_str,
                })
                buyer_offer_obj.engine = f"LLM ({model_name})"
                buyer_offer_obj.api_warning = None
                break
            except Exception as e:
                last_error_msg = str(e)
                logger.warning("[BuyerNode] Model %s failed: %s. Trying next...", model_name, e)

    if not buyer_offer_obj:
        if last_error_msg and ("429" in last_error_msg or "rate_limit" in last_error_msg.lower()):
            warning_text = "Hết hạn ngạch API Groq (Rate Limit 429). Hệ thống tự động chuyển sang thuật toán Heuristic toán học."
        elif last_error_msg:
            warning_text = f"API LLM không phản hồi. Hệ thống chuyển sang thuật toán Heuristic toán học."
        else:
            warning_text = "Không tìm thấy cấu hình API. Đang chạy chế độ Heuristic ngoại tuyến."

        buyer_offer_obj = _heuristic_buyer_bid(
            current_round=current_round,
            budget_ceiling=b_ceil,
            target_price=b_tgt,
            seller_price=seller_price,
            injected_instruction=state.get("injected_instruction"),
            currency=currency,
            last_buyer_price=last_buyer_price,
            rag_benchmarks=benchmarks,
        )
        buyer_offer_obj.engine = "HEURISTIC"
        buyer_offer_obj.api_warning = warning_text

    # Guardrail 0: In Round 1, Buyer MUST open with the exact target price (b_tgt)
    if current_round <= 1:
        buyer_offer_obj.offer_price = b_tgt

    # Guardrail 1: Respect hard budget ceiling
    if buyer_offer_obj.offer_price > b_ceil:
        buyer_offer_obj.offer_price = b_ceil

    # Guardrail 2: Monotonicity - Buyer must NEVER lower offer in subsequent rounds
    if current_round > 1 and last_buyer_price > 0:
        if buyer_offer_obj.offer_price < last_buyer_price:
            logger.warning(
                "[BuyerNode] Buyer proposed %.0f < last round %.0f. Clamping to >= %.0f.",
                buyer_offer_obj.offer_price, last_buyer_price, last_buyer_price
            )
            step = max(1000.0, round((min(b_ceil, seller_price) - last_buyer_price) * 0.25, -3))
            buyer_offer_obj.offer_price = min(b_ceil, round(last_buyer_price + step, -3))
            buyer_offer_obj.offer_price = max(last_buyer_price, buyer_offer_obj.offer_price)

    # Guardrail 3: Clean rounding for VNĐ
    if currency == "VNĐ":
        buyer_offer_obj.offer_price = round(buyer_offer_obj.offer_price, -3)

    return {"buyer_offer": buyer_offer_obj.model_dump()}

