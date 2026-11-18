"""
NexusProcure - Cyclic LangGraph State Machine Workflow.

Orchestrates the 3-Agent Negotiation Loop:
[setup] -> [rag] -> [buyer] -> [seller] -> [mediator] -> [persist] -> loop / END

Features:
- ChromaDB RAG Grounding for Market Benchmarks
- Pydantic Structured Output across Agents
- Native LangGraph Human-in-the-Loop Interrupt & Resume via MemorySaver
- SQLite Round-by-Round Persistence
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.graph.state import NegotiationState
from app.agents.buyer import buyer_node
from app.agents.seller import seller_node
from app.agents.mediator import mediator_node
from app.memory.vector_store import retrieve_price_benchmarks
from app.data.database import get_db_connection

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────
# Node 1: Setup Node
# ───────────────────────────────────────────────────────────────────
def setup_node(state: NegotiationState) -> Dict[str, Any]:
    """Initialize state, default values, and ensure valid round pointers."""
    logger.info("[Workflow] Setup Node initialized.")
    return {
        "current_round": state.get("current_round", 1),
        "max_rounds": state.get("max_rounds", 10),
        "status": state.get("status", "ACTIVE"),
        "currency": state.get("currency", "$"),
        "history": state.get("history", []),
        "rag_benchmarks": state.get("rag_benchmarks", []),
    }


# ───────────────────────────────────────────────────────────────────
# Node 2: RAG Node
# ───────────────────────────────────────────────────────────────────
def rag_node(state: NegotiationState) -> Dict[str, Any]:
    """Retrieve 3-5 similar past deals from ChromaDB as market benchmarks."""
    product_name = state.get("product_name", "Thiết bị")
    logger.info("[Workflow] RAG Node querying ChromaDB for: %s", product_name)

    benchmarks_data = retrieve_price_benchmarks(
        query=f"Mặt hàng: {product_name}",
        top_k=3,
    )
    formatted = [f"• {b['content']}" for b in benchmarks_data] if benchmarks_data else [
        "• Chưa có dữ liệu lịch sử đối chiếu; áp dụng định mức danh mục."
    ]
    return {"rag_benchmarks": formatted}


# ───────────────────────────────────────────────────────────────────
# Node 6: Persist Node
# ───────────────────────────────────────────────────────────────────
def persist_node(state: NegotiationState) -> Dict[str, Any]:
    """
    Records round outcome to SQLite database (negotiation_logs) and appends to in-memory history.
    """
    curr_round = state.get("current_round", 1)
    b_offer = state.get("buyer_offer", {})
    s_offer = state.get("seller_offer", {})
    m_decision = state.get("mediator_decision", {})
    history = list(state.get("history", []))

    round_rec = {
        "round": curr_round,
        "buyer_bid": b_offer.get("offer_price", 0),
        "seller_ask": s_offer.get("offer_price", 0),
        "price_gap": m_decision.get("price_gap", 0),
        "price_gap_pct": m_decision.get("price_gap_pct", 0),
        "buyer_reasoning": b_offer.get("reasoning", ""),
        "seller_reasoning": s_offer.get("reasoning", ""),
        "buyer_engine": b_offer.get("engine", "LLM"),
        "seller_engine": s_offer.get("engine", "LLM"),
        "api_warning": b_offer.get("api_warning") or s_offer.get("api_warning"),
        "status": state.get("status", "ACTIVE"),
        "summary": m_decision.get("reasoning", ""),
    }
    history.append(round_rec)

    # Persist into SQLite
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO negotiation_logs (
                session_id, pr_id, supplier_id, round_number,
                buyer_offer_price, buyer_lead_time_days, buyer_terms, buyer_reasoning,
                supplier_offer_price, supplier_lead_time_days, supplier_terms, supplier_reasoning,
                gap_pct, mediator_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state.get("session_id", "session-default"),
            state.get("session_id", "PR-001"),
            state.get("supplier_name", "Supplier"),
            curr_round,
            b_offer.get("offer_price", 0),
            b_offer.get("lead_time_days", 7),
            b_offer.get("payment_terms", "Net 15"),
            b_offer.get("reasoning", ""),
            s_offer.get("offer_price", 0),
            s_offer.get("lead_time_days", 7),
            s_offer.get("payment_terms", "Net 30"),
            s_offer.get("reasoning", ""),
            m_decision.get("price_gap_pct", 0),
            state.get("status", "ACTIVE"),
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("[Workflow] Could not log to SQLite: %s", e)

    updates: Dict[str, Any] = {"history": history}

    # If continuing to next round, increment round counter
    if state.get("status") == "CONTINUE":
        updates["current_round"] = curr_round + 1

    return updates


# ───────────────────────────────────────────────────────────────────
# Conditional Edge Router
# ───────────────────────────────────────────────────────────────────
def should_continue(state: NegotiationState) -> Literal["rag", "__end__"]:
    """
    Decides whether to loop back to [rag] for the next round or terminate.
    """
    status = state.get("status", "CONTINUE")
    curr_round = state.get("current_round", 1)
    max_rounds = state.get("max_rounds", 10)

    if status in ("SUCCESS", "TERMINATED", "DEADLOCK"):
        logger.info("[Workflow] Terminating state machine with status: %s", status)
        return END

    if curr_round > max_rounds:
        logger.info("[Workflow] Reached maximum rounds (%d). Ending.", max_rounds)
        return END

    logger.info("[Workflow] Advancing to next round (%d). Looping back to [rag].", curr_round)
    return "rag"


# ───────────────────────────────────────────────────────────────────
# Graph Builder
# ───────────────────────────────────────────────────────────────────
def build_negotiation_graph(checkpointer: Optional[Any] = None):
    """
    Constructs and compiles the 3-Agent cyclic LangGraph negotiation engine.
    Uses MemorySaver checkpointer for Human-in-the-Loop interrupts and resumes.
    """
    builder = StateGraph(NegotiationState)

    # Add 6 sequential nodes
    builder.add_node("setup", setup_node)
    builder.add_node("rag", rag_node)
    builder.add_node("buyer", buyer_node)
    builder.add_node("seller", seller_node)
    builder.add_node("mediator", mediator_node)
    builder.add_node("persist", persist_node)

    # Connect deterministic flow
    builder.add_edge(START, "setup")
    builder.add_edge("setup", "rag")
    builder.add_edge("rag", "buyer")
    builder.add_edge("buyer", "seller")
    builder.add_edge("seller", "mediator")
    builder.add_edge("mediator", "persist")

    # Connect cyclical feedback edge
    builder.add_conditional_edges(
        "persist",
        should_continue,
        {
            "rag": "rag",
            END: END,
        },
    )

    cp = checkpointer or MemorySaver()
    return builder.compile(checkpointer=cp)

