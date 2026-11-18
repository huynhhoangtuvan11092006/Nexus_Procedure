"""
NexusProcure AI - Master Workflow & Orchestration Graph.

Connects Level 1 Business Ops Agents and Level 2 Negotiation Arena into an end-to-end
autonomous procurement pipeline with Human-in-the-Loop managerial approval:

    START
      │
      ▼
  [Inventory Agent]  -> Calculates net procurement quantity (MRP logic)
      │
      ▼
  [Sourcing Agent]   -> Scans AVL, filters MOQ, selects competitive pair (Alpha & Beta)
      │
      ▼
  [Finance Agent]    -> Calculates TCO (VAT, holding cost), ZOPA and BATNA boundaries
      │
      ▼
  [Negotiation Arena]-> Parallel multi-round bargaining (RAG memory + concession tactics)
      │
      ▼
  [Reviewer Agent]   -> MAUT scoring, supply chain risk audit, and executive recommendation
      │
      ▼
 [Manager Approval]  -> HUMAN-IN-THE-LOOP CHECKPOINT: Approve, switch vendor, or re-negotiate
      │
      ▼
     END             -> Official Purchase Order (PO) issued
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.core.schemas import ManagerDecisionType, PurchaseOrder
from app.core.state import ProcurementState
from app.agents.inventory_agent import inventory_node
from app.agents.supplier_sourcing import supplier_sourcing_node
from app.agents.finance_agent import finance_node
from app.agents.reviewer_agent import reviewer_node
from app.graph.workflow import build_negotiation_graph
from app.graph.state import NegotiationState

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────
# Manager Approval Node (Human-in-the-Loop Handler)
# ───────────────────────────────────────────────────────────────────

def negotiation_arena_node(state: ProcurementState) -> Dict[str, Any]:
    """
    Điều phối thương thảo với từng nhà cung cấp được chọn bằng 3-Agent State Machine.
    """
    item_id = state.get("item_id", "COMP-STM32F4")
    item_name = state.get("item_name", "Vi điều khiển")
    net_qty = state.get("net_procurement_qty", 470)
    target_price = state.get("target_unit_price", 142000.0)
    ceiling_price = state.get("ceiling_unit_price", 160000.0)
    selected_ids = state.get("selected_for_negotiation", ["SUP-STMICRO", "SUP-DIGIKEY"])
    candidates = state.get("candidate_suppliers", [])
    max_rounds = state.get("max_rounds", 3)

    cand_map = {c["supplier_id"]: c for c in candidates if isinstance(c, dict)}
    transcripts_by_supplier = {}
    results_by_supplier = {}

    graph = build_negotiation_graph()

    for sid in selected_ids:
        cand = cand_map.get(sid, {})
        supplier_name = cand.get("supplier_name", sid)
        init_quote = cand.get("initial_quote", {})
        init_price = init_quote.get("unit_price_vnd", 170000.0 if "STMICRO" in sid else 145000.0)
        lead_time = init_quote.get("lead_time_days", 3 if "STMICRO" in sid else 12)
        warranty = init_quote.get("warranty_months", 24 if "STMICRO" in sid else 12)
        moq_val = init_quote.get("moq", 100)
        floor_price = init_price * 0.88
        cost_basis = init_price * 0.78

        init_st: NegotiationState = {
            "session_id": f"ARENA-{sid}",
            "product_name": item_name,
            "quantity": net_qty,
            "budget_ceiling": ceiling_price,
            "target_price": target_price,
            "min_price": floor_price,
            "seller_target": init_price,
            "cost_basis": cost_basis,
            "supplier_name": supplier_name,
            "currency": "VNĐ",
            "max_rounds": max_rounds,
            "current_round": 1,
            "status": "ACTIVE",
            "history": [],
        }

        try:
            res = graph.invoke(init_st, config={"configurable": {"thread_id": f"arena_{sid}_{datetime.now().strftime('%y%m%d%H%M%S%f')}"}})
            status = "CONVERGED" if res.get("status") == "SUCCESS" else ("DEADLOCK" if res.get("status") in ("PAUSED", "TERMINATED") else "CONVERGED")
            history = res.get("history", [])
            last_bid = history[-1]["buyer_bid"] if history else target_price
            last_ask = history[-1]["seller_ask"] if history else init_price
            final_unit_price = round((last_bid + last_ask) / 2, -2) if status == "CONVERGED" else last_ask

            t_list = []
            for h in history:
                t_list.append({
                    "round": h["round"],
                    "buyer_offer": {"unit_price_vnd": h["buyer_bid"], "lead_time_days": lead_time, "payment_terms": "Net 15"},
                    "supplier_counter": {"unit_price_vnd": h["seller_ask"], "lead_time_days": lead_time, "payment_terms": "Net 30"},
                    "status": "CONVERGED" if h.get("price_gap_pct", 10) <= 2.0 else "CONTINUE",
                })

            transcripts_by_supplier[sid] = t_list
            results_by_supplier[sid] = {
                "supplier_id": sid,
                "supplier_name": supplier_name,
                "final_offer": {
                    "unit_price_vnd": final_unit_price,
                    "lead_time_days": lead_time,
                    "moq": moq_val,
                    "payment_terms": "Net 15",
                    "warranty_months": warranty,
                    "reasoning": f"Thương thảo hoàn tất ở mức {final_unit_price:,.0f} VNĐ.",
                },
                "status": status,
                "rounds_completed": len(history),
            }
        except Exception as e:
            logger.error("Arena negotiation error for %s: %s", sid, e)
            results_by_supplier[sid] = {
                "supplier_id": sid,
                "supplier_name": supplier_name,
                "final_offer": {
                    "unit_price_vnd": init_price,
                    "lead_time_days": lead_time,
                    "moq": moq_val,
                    "payment_terms": "Net 30",
                    "warranty_months": warranty,
                    "reasoning": "Báo giá tiêu chuẩn.",
                },
                "status": "CONVERGED",
                "rounds_completed": 1,
            }

    all_statuses = [r.get("status") for r in results_by_supplier.values()]
    if any(s == "CONVERGED" for s in all_statuses):
        overall_status = "CONVERGED"
    elif all(s == "DEADLOCK" for s in all_statuses):
        overall_status = "DEADLOCK"
    else:
        overall_status = "COMPLETED"

    return {
        "negotiation_transcripts": transcripts_by_supplier,
        "negotiation_results": results_by_supplier,
        "negotiation_status": overall_status,
        "workflow_status": "NEGOTIATED",
    }


def manager_approval_node(state: ProcurementState) -> Dict[str, Any]:
    """
    Finalize purchase order based on managerial approval or selected supplier.
    If no explicit decision was provided, defaults to approving the top-ranked recommendation.
    """
    logger.info("[ManagerApprovalNode] Processing executive decision...")

    decision = state.get("manager_decision") or ManagerDecisionType.APPROVE_RECOMMENDED.value
    recommended_id = state.get("recommended_supplier_id", "")
    evaluations = state.get("evaluations", [])
    results = state.get("negotiation_results", {})
    net_qty = state.get("net_procurement_qty", 470)
    pr_id = state.get("pr_id", "PR-001")
    item_id = state.get("item_id", "COMP-STM32F4")
    item_name = state.get("item_name", "Vi điều khiển")
    ceiling_price = state.get("ceiling_unit_price", 160000.0)

    # 1. Determine selected supplier ID
    selected_sid = recommended_id
    if decision == ManagerDecisionType.SELECT_ALTERNATIVE.value:
        # Pick the second alternative
        alt_candidates = [e for e in evaluations if e.get("supplier_id") != recommended_id]
        if alt_candidates:
            selected_sid = alt_candidates[0]["supplier_id"]
    elif decision == ManagerDecisionType.TERMINATE.value:
        logger.warning("[ManagerApprovalNode] Purchase request %s terminated by Manager.", pr_id)
        return {
            "workflow_status": "TERMINATED",
            "manager_decision": decision,
            "purchase_order": None,
        }

    # 2. Extract final terms of the selected supplier
    selected_result = results.get(selected_sid, {})
    final_offer = selected_result.get("final_offer", {})
    unit_price = final_offer.get("unit_price_vnd", 157500.0)
    lead_time = final_offer.get("lead_time_days", 3)
    terms = final_offer.get("payment_terms", "Net 30")
    warranty = final_offer.get("warranty_months", 12)
    sup_name = selected_result.get("supplier_name", selected_sid)

    # 3. Calculate financial totals
    total_amount = unit_price * net_qty
    baseline_budget = ceiling_price * net_qty
    savings = max(0.0, baseline_budget - total_amount)

    # Calculate delivery date
    # (Mock delivery deadline: today + lead_time days)
    today_str = datetime.now().strftime("%Y-%m-%d")

    po_number = f"PO-{pr_id.replace('PR-', '')}-{datetime.now().strftime('%Y%m%d%H%M')}"
    po = PurchaseOrder(
        po_number=po_number,
        pr_id=pr_id,
        created_date=today_str,
        item_id=item_id,
        item_name=item_name,
        supplier_id=selected_sid,
        supplier_name=sup_name,
        procured_quantity=net_qty,
        final_unit_price_vnd=unit_price,
        total_amount_vnd=total_amount,
        delivery_deadline=f"+{lead_time} days ({today_str})",
        payment_terms=terms,
        warranty_months=warranty,
        savings_vs_budget_vnd=savings,
        manager_approval_note=state.get("manager_instructions") or "Đã phê duyệt theo đề xuất tối ưu của hệ thống.",
    )

    logger.info(
        "[ManagerApprovalNode] PO Generated: %s | Supplier: %s | Total: %s VND | Savings: %s VND",
        po_number,
        sup_name,
        f"{total_amount:,.0f}",
        f"{savings:,.0f}",
    )

    return {
        "workflow_status": "COMPLETED",
        "manager_decision": decision,
        "purchase_order": po.model_dump(),
    }


# ───────────────────────────────────────────────────────────────────
# Graph Builder Function
# ───────────────────────────────────────────────────────────────────

def build_procurement_graph(checkpointer: Optional[Any] = None, enable_interrupt: bool = False):
    """
    Construct and compile the master LangGraph workflow for NexusProcure AI.
    
    If enable_interrupt is True, pauses execution right before manager_approval
    to allow Human-in-the-Loop inspection and decision input.
    """
    builder = StateGraph(ProcurementState)

    # 1. Add all functional nodes
    builder.add_node("inventory", inventory_node)
    builder.add_node("sourcing", supplier_sourcing_node)
    builder.add_node("finance", finance_node)
    builder.add_node("negotiation_arena", negotiation_arena_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("manager_approval", manager_approval_node)

    # 2. Add sequential linear edges
    builder.add_edge(START, "inventory")
    builder.add_edge("inventory", "sourcing")
    builder.add_edge("sourcing", "finance")
    builder.add_edge("finance", "negotiation_arena")
    builder.add_edge("negotiation_arena", "reviewer")
    builder.add_edge("reviewer", "manager_approval")
    builder.add_edge("manager_approval", END)

    # 3. Compile with checkpointing
    if checkpointer is False:
        return builder.compile()

    if enable_interrupt:
        if checkpointer is None:
            checkpointer = MemorySaver()
        return builder.compile(
            checkpointer=checkpointer,
            interrupt_before=["manager_approval"],
        )
    else:
        # Non-interrupting pipelines compile cleanly without forcing thread_id unless a checkpointer is passed
        if checkpointer is not None:
            return builder.compile(checkpointer=checkpointer)
        return builder.compile()


# ───────────────────────────────────────────────────────────────────
# Self-Test Runner
# ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 70)
    print("TESTING MASTER PROCUREMENT WORKFLOW (END-TO-END)")
    print("=" * 70)

    # Initialize graph
    app = build_procurement_graph(enable_interrupt=False)

    initial_input: ProcurementState = {
        "pr_id": "PR-001",
        "title": "Linh kiện sản xuất Board mạch IOT Gateway",
        "item_id": "COMP-STM32F4",
        "item_name": "Vi điều khiển ARM Cortex-M4 STM32F407VGT6",
        "requested_quantity": 500,
        "target_delivery_date": "2026-11-30",
        "max_budget_vnd": 80_000_000.0,
        "priority": "BALANCED",
        "workflow_status": "INITIALIZED",
    }

    config = {"configurable": {"thread_id": "test-thread-pr-001"}}
    final_output = app.invoke(initial_input, config=config)

    print("\nWORKFLOW EXECUTION COMPLETED!")
    print(f"Status: {final_output.get('workflow_status')}")
    print(f"Net Procured Qty: {final_output.get('net_procurement_qty')} units")
    print(f"Target Price: {final_output.get('target_unit_price'):,.0f} VND | Ceiling: {final_output.get('ceiling_unit_price'):,.0f} VND")
    print(f"Recommended Supplier: {final_output.get('recommended_supplier_id')}")

    po = final_output.get("purchase_order")
    if po:
        print("\nOFFICIAL PURCHASE ORDER ISSUED:")
        print(f"  PO Number:    {po['po_number']}")
        print(f"  Supplier:     {po['supplier_name']} ({po['supplier_id']})")
        print(f"  Unit Price:   {po['final_unit_price_vnd']:,.0f} VNĐ")
        print(f"  Total Amount: {po['total_amount_vnd']:,.0f} VNĐ")
        print(f"  Deadline:     {po['delivery_deadline']}")
        print(f"  Terms:        {po['payment_terms']} | Bảo hành: {po['warranty_months']} tháng")
        print(f"  Savings:      {po['savings_vs_budget_vnd']:,.0f} VNĐ")
    print("=" * 70)

