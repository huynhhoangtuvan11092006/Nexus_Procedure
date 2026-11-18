"""
NexusProcure - Mediator Agent Node.

Responsible for:
1. Acting as an impartial arbiter calculating price_gap and concession velocity.
2. Checking convergence:
   - Gap <= 2.0% (or Buyer Bid >= Seller Ask): SUCCESS
   - Deadlock / Max rounds / Review needed: triggers langgraph.types.interrupt()
   - Progressing normally: CONTINUE
3. Handling human override resumption payload when woken up via Command(resume=...).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from langgraph.types import interrupt

from app.models.schemas import MediatorDecision, PurchaseOrder
from app.graph.state import NegotiationState

logger = logging.getLogger(__name__)


def mediator_node(state: NegotiationState) -> Dict[str, Any]:
    """
    LangGraph Node: [mediator]
    Analyzes current round offers, assesses ZOPA convergence, and manages Human-in-the-Loop interrupt.
    """
    logger.info("[MediatorNode] Evaluating round offers and checking convergence...")

    curr_round = state.get("current_round", 1)
    max_rounds = state.get("max_rounds", 10)
    currency = state.get("currency", "$")
    b_ceil = float(state.get("budget_ceiling", 50000))
    s_floor = float(state.get("min_price", 30000))

    b_offer = state.get("buyer_offer", {})
    s_offer = state.get("seller_offer", {})

    buyer_price = float(b_offer.get("offer_price", 0))
    seller_price = float(s_offer.get("offer_price", 0))

    gap = max(0.0, seller_price - buyer_price)
    gap_pct = (gap / max(1.0, seller_price)) * 100.0

    # 1. Condition: Agreement Reached (Gap <= 2.0% or Buyer Bid >= Seller Ask)
    if buyer_price >= seller_price or gap_pct <= 2.0:
        raw_agreed = (buyer_price + seller_price) / 2
        agreed_price = round(raw_agreed, -3) if currency == "VNĐ" else round(raw_agreed, 2)
        po = PurchaseOrder(
            po_number=f"PO-{datetime.now().strftime('%y%m%d%H%M')}",
            item_name=state.get("product_name", "Thiết bị"),
            quantity=int(state.get("quantity", 100)),
            agreed_unit_price=agreed_price,
            total_amount=agreed_price * int(state.get("quantity", 100)),
            currency=currency,
            supplier_name=state.get("supplier_name", "Đối tác"),
            created_at=datetime.now().strftime("%Y-%m-%d"),
            status="APPROVED",
            approval_note=f"Đạt thỏa thuận thành công tại Vòng {curr_round} với chênh lệch {gap_pct:.2f}%.",
        )
        decision = MediatorDecision(
            status="SUCCESS",
            price_gap=gap,
            price_gap_pct=gap_pct,
            reasoning=f"🎉 Hai bên đã đạt được thỏa thuận tại mức đơn giá {agreed_price:,.0f} {currency}!",
            requires_human=False,
        )
        return {
            "mediator_decision": decision.model_dump(),
            "status": "SUCCESS",
            "purchase_order": po.model_dump(),
        }

    # 2. Condition: Deadlock, Out of Rounds, or Review Trigger -> HITL interrupt()
    should_interrupt = (
        (curr_round >= max_rounds) or
        (buyer_price >= b_ceil and seller_price <= s_floor and curr_round > 1) or
        (state.get("human_action") is not None)
    )

    if should_interrupt:
        logger.info("[MediatorNode] Interrupting graph for Human-in-the-Loop decision...")
        # Freezes graph execution here; returns PAUSED to caller
        human_response = interrupt({
            "reason": f"Offers gap is {gap_pct:.1f}% ({gap:,.0f} {currency}) at Round {curr_round}",
            "current_round": curr_round,
            "buyer_price": buyer_price,
            "seller_price": seller_price,
            "options": ["approve", "reject", "modify_buyer", "modify_seller", "inject", "terminate"],
        })

        # Resumed via graph.invoke(Command(resume=...))
        logger.info("[MediatorNode] Resumed with human response: %s", human_response)
        action = human_response.get("action") if isinstance(human_response, dict) else str(human_response)

        if action == "approve":
            raw_agreed = (buyer_price + seller_price) / 2
            agreed_price = round(raw_agreed, -3) if currency == "VNĐ" else round(raw_agreed, 2)
            po = PurchaseOrder(
                po_number=f"PO-{datetime.now().strftime('%y%m%d%H%M')}",
                item_name=state.get("product_name", "Thiết bị"),
                quantity=int(state.get("quantity", 100)),
                agreed_unit_price=agreed_price,
                total_amount=agreed_price * int(state.get("quantity", 100)),
                currency=currency,
                supplier_name=state.get("supplier_name", "Đối tác"),
                created_at=datetime.now().strftime("%Y-%m-%d"),
                status="APPROVED",
                approval_note="Chốt hợp đồng trực tiếp theo quyết định phê duyệt của Quản lý (Approve).",
            )
            decision = MediatorDecision(
                status="SUCCESS",
                price_gap=gap,
                price_gap_pct=gap_pct,
                reasoning=f"Quản lý đã ký duyệt Approve chốt đơn giá {agreed_price:,.0f} {currency}!",
                requires_human=False,
            )
            return {
                "mediator_decision": decision.model_dump(),
                "status": "SUCCESS",
                "purchase_order": po.model_dump(),
            }

        elif action == "reject":
            decision = MediatorDecision(
                status="CONTINUE",
                price_gap=gap,
                price_gap_pct=gap_pct,
                reasoning="Quản lý đã bác bỏ đề xuất vòng vừa rồi. Yêu cầu hai bên thương lượng lại.",
                requires_human=False,
            )
            return {
                "mediator_decision": decision.model_dump(),
                "status": "CONTINUE",
                "injected_instruction": "Quản lý đã bác bỏ mức giá vừa rồi. Đề nghị hai bên nhượng bộ thực chất hơn.",
            }

        elif action == "modify_buyer":
            new_ceiling = float(human_response.get("new_budget_ceiling", b_ceil))
            new_target = float(human_response.get("new_buyer_target", state.get("target_price", buyer_price)))
            decision = MediatorDecision(
                status="CONTINUE",
                price_gap=gap,
                price_gap_pct=gap_pct,
                reasoning=f"Đã cập nhật ngân sách bên mua: Trần {new_ceiling:,.0f} {currency}, Mục tiêu {new_target:,.0f} {currency}.",
                requires_human=False,
            )
            return {
                "budget_ceiling": new_ceiling,
                "target_price": new_target,
                "mediator_decision": decision.model_dump(),
                "status": "CONTINUE",
            }

        elif action == "modify_seller":
            new_floor = float(human_response.get("new_min_price", s_floor))
            new_cost = float(human_response.get("new_seller_cost", state.get("cost_basis", s_floor * 0.9)))
            decision = MediatorDecision(
                status="CONTINUE",
                price_gap=gap,
                price_gap_pct=gap_pct,
                reasoning=f"Đã cập nhật giới hạn bên bán: Giá sàn {new_floor:,.0f} {currency}, Giá vốn {new_cost:,.0f} {currency}.",
                requires_human=False,
            )
            return {
                "min_price": new_floor,
                "cost_basis": new_cost,
                "mediator_decision": decision.model_dump(),
                "status": "CONTINUE",
            }

        elif action == "inject":
            injected = human_response.get("injected_guidance", "")
            decision = MediatorDecision(
                status="CONTINUE",
                price_gap=gap,
                price_gap_pct=gap_pct,
                reasoning=f"Đã inject chỉ đạo văn bản từ Quản lý: '{injected}'",
                requires_human=False,
            )
            return {
                "injected_instruction": injected,
                "mediator_decision": decision.model_dump(),
                "status": "CONTINUE",
            }

        elif action in ("terminate", "cancel"):
            decision = MediatorDecision(
                status="TERMINATED",
                price_gap=gap,
                price_gap_pct=gap_pct,
                reasoning="Phiên đàm phán đã bị Quản lý cưỡng chế hủy bỏ ngay lập tức.",
                requires_human=False,
            )
            return {
                "mediator_decision": decision.model_dump(),
                "status": "TERMINATED",
                "purchase_order": None,
            }

        elif action == "modify":
            new_ceiling = float(human_response.get("new_budget_ceiling", b_ceil))
            new_floor = float(human_response.get("new_min_price", s_floor))
            injected = human_response.get("injected_guidance")
            decision = MediatorDecision(
                status="CONTINUE",
                price_gap=gap,
                price_gap_pct=gap_pct,
                reasoning="Đã cập nhật lại thông số ràng buộc ngân sách theo chỉ đạo Quản lý.",
                requires_human=False,
            )
            updates: Dict[str, Any] = {
                "budget_ceiling": new_ceiling,
                "min_price": new_floor,
                "mediator_decision": decision.model_dump(),
                "status": "CONTINUE",
            }
            if injected:
                updates["injected_instruction"] = injected
            return updates

    # 3. Normal continuation
    decision = MediatorDecision(
        status="CONTINUE",
        price_gap=gap,
        price_gap_pct=gap_pct,
        reasoning=f"Khoảng cách giá đang thu hẹp ({gap:,.0f} {currency} - {gap_pct:.1f}%). Tiếp tục đàm phán.",
        requires_human=False,
    )
    return {
        "mediator_decision": decision.model_dump(),
        "status": "CONTINUE",
    }

