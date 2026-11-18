"""
NexusProcure AI - Supplier Sourcing Agent.

Acts as the strategic Vendor Sourcing Specialist.
Queries the Approved Vendor List (AVL) from SQLite, gathers initial quotes,
evaluates supplier fit against PR constraints (MOQ, lead times), and selects
the top candidate suppliers for competitive parallel negotiation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.core.schemas import ContractOffer, PriorityType
from app.core.state import ProcurementState
from app.data.database import get_all_suppliers, get_inventory_item

logger = logging.getLogger(__name__)


def generate_initial_quote_for_supplier(
    supplier: Dict[str, Any],
    standard_cost: float,
    net_quantity: int,
) -> ContractOffer:
    """
    Generate the realistic initial quotation for a supplier based on their persona.
    
    Parameters
    ----------
    supplier : dict
        Supplier master record from SQLite.
    standard_cost : float
        Internal standard cost of the component.
    net_quantity : int
        Calculated quantity needed.
    """
    persona = supplier.get("persona_type", "")
    lead_time = supplier.get("standard_lead_time_days", 7)
    payment_terms = supplier.get("payment_terms_default", "Net 30")

    if persona == "PREMIUM_RIGID":
        # STMicroelectronics: High price (+13% above standard cost), fast lead time (3 days), high warranty
        unit_price = round(standard_cost * 1.133, -3)  # ~170,000 for STM32
        moq = 100
        warranty = 24
        reasoning = "Hàng chính hãng phân phối ủy quyền, mới 100%, bảo hành 24 tháng, kho sẵn giao ngay."

    elif persona == "CASHFLOW_FLEXIBLE":
        # Digi-Key: Low price (-3% below standard cost), slow lead time (15 days), standard warranty
        unit_price = round(standard_cost * 0.967, -3)  # ~145,000 for STM32
        moq = 200
        warranty = 12
        reasoning = "Giá đại lý phân phối chiết khấu cạnh tranh, giao hàng theo chuyến container định kỳ 15 ngày."

    elif persona == "VOLUME_MOQ":
        # Winstar: Very cheap (-13% below standard), requires high MOQ (1,000)
        unit_price = round(standard_cost * 0.867, -3)  # ~130,000 for STM32
        moq = 1000
        warranty = 12
        reasoning = "Giá xuất xưởng sản xuất trực tiếp, chỉ áp dụng cho đơn hàng số lượng lớn MOQ từ 1.000 chiếc."

    elif persona == "RAPID_DISPATCH":
        # Sensirion: Emergency stock, high price (+20%), delivery in 2 days
        unit_price = round(standard_cost * 1.20, -3)  # ~180,000 for STM32
        moq = 50
        lead_time = 2
        warranty = 12
        reasoning = "Dịch vụ cung ứng hỏa tốc 48h phục vụ dây chuyền sự cố, có sẵn hàng bay trực tiếp."

    else:
        # Delta / Default Compromise
        unit_price = round(standard_cost * 1.033, -3)  # ~155,000 for STM32
        moq = 150
        lead_time = 10
        warranty = 12
        reasoning = "Báo giá tiêu chuẩn thương mại linh kiện nhập khẩu."

    return ContractOffer(
        unit_price_vnd=unit_price,
        lead_time_days=lead_time,
        moq=moq,
        payment_terms=payment_terms,
        warranty_months=warranty,
        reasoning=reasoning,
        concession_notes="Báo giá khởi điểm ban đầu.",
    )


def select_best_negotiation_pair(
    candidates: List[Dict[str, Any]],
    net_quantity: int,
    priority: str,
) -> List[str]:
    """
    Select the top 2 candidate suppliers for competitive parallel negotiation.
    
    Creates meaningful trade-offs:
    - For FAST_DELIVERY: Prioritizes fastest lead time candidates (STMicroelectronics, Sensirion).
    - For LOWEST_COST: Prioritizes lowest price candidates (Digi-Key, Winstar).
    - For BALANCED: Selects the classic contrast pair (STMicroelectronics - Fast/Premium vs Digi-Key - Global/Low Cost).
    """
    if priority == PriorityType.FAST_DELIVERY.value:
        # Sort by lead time ascending
        sorted_candidates = sorted(candidates, key=lambda c: c["initial_quote"]["lead_time_days"])
        selected = [sorted_candidates[0]["supplier_id"], sorted_candidates[1]["supplier_id"]]

    elif priority == PriorityType.LOWEST_COST.value:
        # Sort by unit price ascending
        sorted_candidates = sorted(candidates, key=lambda c: c["initial_quote"]["unit_price_vnd"])
        selected = [sorted_candidates[0]["supplier_id"], sorted_candidates[1]["supplier_id"]]

    else:
        # Default BALANCED: Pick STMicroelectronics and Digi-Key to form a trade-off arena
        candidate_ids = [c["supplier_id"] for c in candidates]
        selected = []
        if "SUP-STMICRO" in candidate_ids:
            selected.append("SUP-STMICRO")
        if "SUP-DIGIKEY" in candidate_ids:
            selected.append("SUP-DIGIKEY")

        # Fallback if preferred are missing
        if len(selected) < 2:
            remaining = [cid for cid in candidate_ids if cid not in selected]
            selected.extend(remaining[: 2 - len(selected)])

    return selected


def supplier_sourcing_node(state: ProcurementState) -> Dict[str, Any]:
    """
    LangGraph Node for the Supplier Sourcing Agent.
    
    1. Reads net quantity and priority from state.
    2. Queries AVL suppliers from SQLite.
    3. Generates quotes and flags candidates with MOQ constraints.
    4. Selects the top 2 suppliers to enter the parallel negotiation arena.
    """
    item_id = state.get("item_id", "")
    net_quantity = state.get("net_procurement_qty", state.get("requested_quantity", 0))
    priority = state.get("priority", PriorityType.BALANCED.value)

    logger.info("[SourcingAgent] Sourcing suppliers for %s (Net Qty: %d, Priority: %s)", item_id, net_quantity, priority)

    # 1. Get standard cost for pricing baseline
    item_data = get_inventory_item(item_id)
    standard_cost = item_data.get("standard_cost_vnd", 150000.0) if item_data else 150000.0

    # 2. Query suppliers from SQLite
    suppliers = get_all_suppliers()
    candidate_profiles = []

    for sup in suppliers:
        quote = generate_initial_quote_for_supplier(
            supplier=sup,
            standard_cost=standard_cost,
            net_quantity=net_quantity,
        )

        candidate_profiles.append({
            "supplier_id": sup["supplier_id"],
            "supplier_name": sup["supplier_name"],
            "tier": sup["tier"],
            "reliability_score": sup["reliability_score"],
            "quality_rating": sup["quality_rating"],
            "persona_type": sup["persona_type"],
            "standard_lead_time_days": sup["standard_lead_time_days"],
            "initial_quote": quote.model_dump(),
            "moq_compatible": quote.moq <= net_quantity,
        })

    # 3. Select top 2 suppliers to enter competitive negotiation arena
    selected_ids = select_best_negotiation_pair(
        candidates=candidate_profiles,
        net_quantity=net_quantity,
        priority=priority,
    )

    logger.info("[SourcingAgent] Identified %d candidates. Selected for negotiation: %s", len(candidate_profiles), selected_ids)

    # 4. Return state update
    return {
        "candidate_suppliers": candidate_profiles,
        "selected_for_negotiation": selected_ids,
    }


# ───────────────────────────────────────────────────────────────────
# Self-Test Runner
# ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("TESTING SUPPLIER SOURCING AGENT (PR-001 Scenario)")
    print("=" * 60)

    mock_state: ProcurementState = {
        "pr_id": "PR-001",
        "item_id": "COMP-STM32F4",
        "net_procurement_qty": 470,
        "priority": "BALANCED",
    }

    result = supplier_sourcing_node(mock_state)

    print(f"Tổng số nhà cung cấp trong danh bạ: {len(result['candidate_suppliers'])}")
    print("\nBáo giá ban đầu thu thập được:")
    for c in result["candidate_suppliers"]:
        q = c["initial_quote"]
        moq_status = "✔ Phù hợp" if c["moq_compatible"] else f"❌ Vượt MOQ ({q['moq']} > {mock_state['net_procurement_qty']})"
        print(f"- {c['supplier_id']:11s} | {c['supplier_name'][:32]:32s} | Giá: {q['unit_price_vnd']:>9,.0f} đ | Hạn: {q['lead_time_days']:2d} ngày | MOQ: {moq_status}")

    print(f"\n👉 Hai nhà cung cấp được chọn vào Đấu trường Đàm phán Song song: {result['selected_for_negotiation']}")
    print("=" * 60)

