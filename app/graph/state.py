"""
NexusProcure - LangGraph State Definitions.

Defines:
1. NegotiationState: State machine schema for the 3-Agent Negotiation Arena (Buyer, Seller, Mediator).
2. ProcurementState: Backward-compatible state schema for enterprise Business Ops.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict

try:
    from langgraph.graph.message import add_messages
except ImportError:
    def add_messages(left: list, right: list) -> list:
        if not isinstance(left, list):
            left = [left]
        if not isinstance(right, list):
            right = [right]
        return left + right


class NegotiationState(TypedDict, total=False):
    """
    Central State flowing through the cyclical LangGraph State Machine:
    [setup] -> [rag] -> [buyer] -> [seller] -> [mediator] -> [persist] -> loop / end
    """
    # ── Session & Metadata ─────────────────────────────────────────
    session_id: str
    current_round: int
    max_rounds: int
    status: str                         # "ACTIVE", "CONTINUE", "PAUSED", "SUCCESS", "DEADLOCK", "TERMINATED"
    currency: str                       # "$" or "VNĐ"

    # ── Buyer Constraints ─────────────────────────────────────────
    product_name: str
    quantity: int
    budget_ceiling: float
    target_price: float

    # ── Seller Constraints ────────────────────────────────────────
    supplier_name: str
    min_price: float
    seller_target: float
    cost_basis: float

    # ── RAG Grounding ─────────────────────────────────────────────
    rag_benchmarks: List[str]

    # ── Agent Round Offers ────────────────────────────────────────
    buyer_offer: Dict[str, Any]
    seller_offer: Dict[str, Any]
    mediator_decision: Dict[str, Any]

    # ── Full Round History & Transcript ───────────────────────────
    history: List[Dict[str, Any]]

    # ── Human-in-the-Loop Interaction ─────────────────────────────
    human_action: Optional[Dict[str, Any]] # {"action": "approve"|"reject"|"modify"|"inject", ...}
    injected_instruction: Optional[str]
    purchase_order: Optional[Dict[str, Any]]


class ProcurementState(TypedDict, total=False):
    """
    Enterprise procurement state schema for Level 1 Business Ops.
    """
    pr_id: str
    title: str
    item_id: str
    item_name: str
    requested_quantity: int
    target_delivery_date: str
    max_budget_vnd: float
    priority: str

    current_stock: int
    safety_stock: int
    net_procurement_qty: int
    inventory_notes: str

    candidate_suppliers: List[Dict[str, Any]]
    selected_for_negotiation: List[str]

    target_unit_price: float
    ceiling_unit_price: float
    tco_summary: Dict[str, Any]

    retrieved_benchmarks: List[str]

    current_round: int
    max_rounds: int
    negotiation_transcripts: Dict[str, List[Dict[str, Any]]]
    negotiation_results: Dict[str, Dict[str, Any]]
    negotiation_status: str

    evaluations: List[Dict[str, Any]]
    recommended_supplier_id: str
    risk_assessment_report: str

    manager_decision: Optional[str]
    manager_instructions: Optional[str]
    purchase_order: Optional[Dict[str, Any]]

    workflow_status: str
    error: Optional[str]
    messages: Annotated[list, add_messages]

