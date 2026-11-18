"""
NexusProcure AI - Finance Agent.

Acts as the Procurement Financial Analyst & Commercial Controller.
Calculates Total Cost of Ownership (TCO) including VAT, logistics, and inventory holding costs.
Defines BATNA, Target Price, Ceiling Budget, and the Zone of Possible Agreement (ZOPA).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.core.state import ProcurementState
from app.data.database import get_inventory_item

logger = logging.getLogger(__name__)

# Standard financial constants in Vietnam enterprise manufacturing
DEFAULT_VAT_RATE = 0.08          # 8% VAT for electronic components
ANNUAL_HOLDING_COST_RATE = 0.15  # 15% annual carrying/holding cost for excess inventory


def calculate_supplier_tco(
    unit_price: float,
    procured_qty: int,
    moq: int,
    lead_time_days: int,
    standard_cost: float,
    vat_rate: float = DEFAULT_VAT_RATE,
) -> Dict[str, Any]:
    """
    Calculate the Total Cost of Ownership (TCO) for a supplier proposal.
    
    Factors included:
    1. Base purchase cost = unit_price * actual_order_qty (where actual_order_qty = max(procured_qty, moq))
    2. VAT tax amount
    3. Logistics / expedited shipping cost estimate
    4. Inventory holding cost penalty if forced to purchase excess stock due to high MOQ
    """
    # If supplier has MOQ greater than needed, company is forced to purchase excess
    actual_order_qty = max(procured_qty, moq)
    excess_qty = actual_order_qty - procured_qty

    base_purchase_cost = unit_price * actual_order_qty
    vat_amount = base_purchase_cost * vat_rate

    # Shipping fee estimate: standard is free; expedited (< 5 days) incurs 2% fee
    shipping_fee = base_purchase_cost * 0.02 if lead_time_days <= 3 else 0.0

    # Holding cost penalty for excess inventory stored in warehouse for 6 months (0.5 year)
    excess_holding_cost = excess_qty * standard_cost * (ANNUAL_HOLDING_COST_RATE * 0.5) if excess_qty > 0 else 0.0

    total_tco = base_purchase_cost + vat_amount + shipping_fee + excess_holding_cost

    return {
        "actual_order_qty": actual_order_qty,
        "excess_qty": excess_qty,
        "base_purchase_cost": round(base_purchase_cost, 0),
        "vat_amount": round(vat_amount, 0),
        "shipping_fee": round(shipping_fee, 0),
        "excess_holding_cost": round(excess_holding_cost, 0),
        "total_tco": round(total_tco, 0),
        "effective_unit_cost": round(total_tco / max(1, procured_qty), 0),  # Effective cost per usable unit
    }


def finance_node(state: ProcurementState) -> Dict[str, Any]:
    """
    LangGraph Node for the Finance Agent.
    
    1. Reads net procurement quantity, max budget, and candidate suppliers.
    2. Establishes the negotiation ZOPA:
       - Ceiling Unit Price = max_budget / requested_quantity
       - Target Unit Price = standard_cost * 0.95 (aim for 5% cost reduction)
    3. Calculates TCO breakdown for each candidate supplier.
    4. Identifies BATNA (Best Alternative to a Negotiated Agreement).
    """
    item_id = state.get("item_id", "")
    requested_qty = state.get("requested_quantity", 500)
    net_qty = state.get("net_procurement_qty", requested_qty)
    max_budget = state.get("max_budget_vnd", 80_000_000.0)
    candidates = state.get("candidate_suppliers", [])

    logger.info("[FinanceAgent] Running financial analysis for Item: %s (Budget: %s)", item_id, f"{max_budget:,.0f} VND")

    # 1. Base unit metrics
    item_data = get_inventory_item(item_id)
    standard_cost = item_data.get("standard_cost_vnd", 150_000.0) if item_data else 150_000.0

    # Ceiling price is the maximum budget limit per unit
    ceiling_unit_price = round(max_budget / max(1, requested_qty), 0)

    # Target price: Aiming for 3-5% savings below standard cost
    target_unit_price = round(standard_cost * 0.95, -3)  # ~142,000 - 145,000 VND

    # 2. Compute TCO for each candidate supplier
    tco_breakdown: Dict[str, Any] = {}
    batna_candidate: Dict[str, Any] | None = None
    lowest_tco = float("inf")

    for candidate in candidates:
        sup_id = candidate["supplier_id"]
        quote = candidate["initial_quote"]

        tco = calculate_supplier_tco(
            unit_price=quote["unit_price_vnd"],
            procured_qty=net_qty,
            moq=quote.get("moq", 1),
            lead_time_days=quote.get("lead_time_days", 7),
            standard_cost=standard_cost,
        )
        tco_breakdown[sup_id] = {
            "supplier_name": candidate["supplier_name"],
            "unit_price_quoted": quote["unit_price_vnd"],
            "tco_details": tco,
        }

        # Identify BATNA: Best existing alternative that meets basic feasibility
        if quote.get("moq", 1) <= net_qty and tco["total_tco"] < lowest_tco:
            lowest_tco = tco["total_tco"]
            batna_candidate = {
                "supplier_id": sup_id,
                "supplier_name": candidate["supplier_name"],
                "unit_price": quote["unit_price_vnd"],
                "total_tco": tco["total_tco"],
            }

    # 3. Financial Summary narrative
    tco_summary = {
        "allocated_budget_for_net_qty": round(ceiling_unit_price * net_qty, 0),
        "ceiling_unit_price": ceiling_unit_price,
        "target_unit_price": target_unit_price,
        "standard_cost": standard_cost,
        "batna": batna_candidate,
        "candidates_tco": tco_breakdown,
        "zopa_range_vnd": f"{target_unit_price:,.0f} - {ceiling_unit_price:,.0f} VNĐ",
    }

    logger.info(
        "[FinanceAgent] ZOPA: %s | Target: %s | Ceiling: %s | BATNA: %s",
        tco_summary["zopa_range_vnd"],
        f"{target_unit_price:,.0f}",
        f"{ceiling_unit_price:,.0f}",
        batna_candidate["supplier_id"] if batna_candidate else "None",
    )

    # 4. Return state update
    return {
        "target_unit_price": target_unit_price,
        "ceiling_unit_price": ceiling_unit_price,
        "tco_summary": tco_summary,
    }


# ───────────────────────────────────────────────────────────────────
# Self-Test Runner
# ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("TESTING FINANCE AGENT (PR-001 Scenario)")
    print("=" * 60)

    from app.agents.supplier_sourcing import supplier_sourcing_node

    # Simulate state flowing from Inventory and Sourcing Agents
    state: ProcurementState = {
        "pr_id": "PR-001",
        "item_id": "COMP-STM32F4",
        "requested_quantity": 500,
        "net_procurement_qty": 470,
        "max_budget_vnd": 80_000_000.0,
        "priority": "BALANCED",
    }

    # Populate candidate_suppliers via Sourcing Agent
    sourcing_res = supplier_sourcing_node(state)
    state.update(sourcing_res)

    # Run Finance Agent
    fin_res = finance_node(state)

    print(f"Đơn giá trần ngân sách cho phép (Ceiling): {fin_res['ceiling_unit_price']:,.0f} VNĐ")
    print(f"Đơn giá mục tiêu đàm phán (Target):        {fin_res['target_unit_price']:,.0f} VNĐ")
    print(f"Vùng thương lượng khả thi (ZOPA):         {fin_res['tco_summary']['zopa_range_vnd']}")
    
    batna = fin_res['tco_summary']['batna']
    print(f"\n👉 BATNA (Phương án dự phòng tốt nhất): {batna['supplier_name']} - Giá: {batna['unit_price']:,.0f} đ (TCO: {batna['total_tco']:,.0f} đ)")

    print("\nBảng phân tích TCO chi tiết từng nhà cung cấp:")
    for sup_id, data in fin_res["tco_summary"]["candidates_tco"].items():
        tco = data["tco_details"]
        excess_info = f" (Mua thừa {tco['excess_qty']} c do MOQ, phí lưu kho: +{tco['excess_holding_cost']:,.0f}đ)" if tco['excess_qty'] > 0 else ""
        print(f"- {sup_id:11s} | Giá chào: {data['unit_price_quoted']:>7,.0f} đ | Tổng TCO (gồm VAT + Phí): {tco['total_tco']:>11,.0f} đ{excess_info}")
    print("=" * 60)

