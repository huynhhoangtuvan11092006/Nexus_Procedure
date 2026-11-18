"""
NexusProcure AI - Multi-Attribute Utility Theory (MAUT) & Negotiation Arbiter.

Implements the multi-criteria decision analysis (MCDA) framework used to objectively
evaluate competitive supplier packages across 5 dimensions:
1. Total Cost / Unit Price
2. Delivery Lead Time vs Schedule Deadline
3. Commercial Payment Terms (Net 30 vs Net 15)
4. Warranty Coverage
5. Supply Chain Reliability & Operational Risk

Also provides convergence checking (Arbiter) to determine if a negotiation round
has converged, should continue, or has hit a deadlock.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from app.core.schemas import (
    ContractOffer,
    MultiAttributeScore,
    PriorityType,
)

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────
# 1. Multi-Attribute Utility Theory (MAUT) Calculator
# ───────────────────────────────────────────────────────────────────

def calculate_maut_score(
    offer: ContractOffer,
    target_unit_price: float,
    ceiling_unit_price: float,
    max_acceptable_lead_time_days: int = 14,
    supplier_reliability_rating: float = 4.5,
    priority: PriorityType = PriorityType.BALANCED,
) -> MultiAttributeScore:
    """
    Compute normalized Multi-Attribute Utility Theory (MAUT) scores (0.0 to 100.0).
    
    Weights dynamically adapt based on business priority:
    - BALANCED: Cost 40%, Delivery 30%, Terms 15%, Risk 15%
    - FAST_DELIVERY: Delivery 55%, Risk 20%, Cost 15%, Terms 10%
    - LOWEST_COST: Cost 60%, Terms 15%, Delivery 15%, Risk 10%
    """
    # 1. Cost Score (0 - 100)
    # 100 if price <= target_unit_price; 0 if price >= ceiling_unit_price
    price = offer.unit_price_vnd
    if price <= target_unit_price:
        cost_score = 100.0
    elif price >= ceiling_unit_price:
        cost_score = max(0.0, 10.0 * (1.0 - (price - ceiling_unit_price) / max(1.0, ceiling_unit_price)))
    else:
        # Linear interpolation between target (100) and ceiling (20)
        denom = max(1.0, ceiling_unit_price - target_unit_price)
        ratio = (price - target_unit_price) / denom
        cost_score = 100.0 - (ratio * 75.0)  # at ceiling -> 25 points

    # 2. Delivery Lead Time Score (0 - 100)
    # 100 if 3 days or fewer; falls as lead time approaches or exceeds deadline
    lead = offer.lead_time_days
    if lead <= 3:
        delivery_score = 100.0
    elif lead >= max_acceptable_lead_time_days:
        delivery_score = max(5.0, 25.0 - (lead - max_acceptable_lead_time_days) * 5.0)
    else:
        # e.g., 3 days -> 100, 14 days -> 35
        ratio = (lead - 3) / max(1, max_acceptable_lead_time_days - 3)
        delivery_score = 100.0 - (ratio * 65.0)

    # 3. Commercial Terms & Warranty Score (0 - 100)
    # Payment terms: Net 30 is best (buyer keeps cash longer), Net 15 ok, COD/Advance worst
    terms_upper = offer.payment_terms.upper()
    if "NET 30" in terms_upper:
        pay_subscore = 60.0
    elif "NET 15" in terms_upper:
        pay_subscore = 45.0
    else:
        pay_subscore = 20.0

    # Warranty subscore: 24 months = 40 pts, 12 months = 25 pts, <12 = 10 pts
    if offer.warranty_months >= 24:
        war_subscore = 40.0
    elif offer.warranty_months >= 12:
        war_subscore = 25.0
    else:
        war_subscore = 10.0
    terms_score = min(100.0, pay_subscore + war_subscore)

    # 4. Supply Chain Risk & Reliability Score (0 - 100)
    # Supplier rating (1.0 to 5.0) -> scaled to 70 pts
    # Buffer days before deadline -> up to 30 pts
    rel_subscore = (supplier_reliability_rating / 5.0) * 70.0
    buffer_days = max(0, max_acceptable_lead_time_days - lead)
    buffer_subscore = min(30.0, buffer_days * 3.0)
    risk_score = min(100.0, rel_subscore + buffer_subscore)

    # 5. Dynamic Weighting based on Priority
    if priority == PriorityType.FAST_DELIVERY:
        w_cost, w_delivery, w_terms, w_risk = 0.15, 0.55, 0.10, 0.20
    elif priority == PriorityType.LOWEST_COST:
        w_cost, w_delivery, w_terms, w_risk = 0.60, 0.15, 0.15, 0.10
    else:  # BALANCED
        w_cost, w_delivery, w_terms, w_risk = 0.40, 0.30, 0.15, 0.15

    total_utility = (
        (cost_score * w_cost)
        + (delivery_score * w_delivery)
        + (terms_score * w_terms)
        + (risk_score * w_risk)
    )

    return MultiAttributeScore(
        cost_score=round(cost_score, 2),
        delivery_score=round(delivery_score, 2),
        terms_score=round(terms_score, 2),
        risk_score=round(risk_score, 2),
        total_utility=round(total_utility, 2),
    )


# ───────────────────────────────────────────────────────────────────
# 2. Negotiation Convergence Arbiter
# ───────────────────────────────────────────────────────────────────

def evaluate_convergence(
    buyer_offer: ContractOffer,
    supplier_offer: ContractOffer,
    round_number: int,
    max_rounds: int,
    ceiling_unit_price: float,
    convergence_threshold_pct: float = 2.0,
) -> Tuple[str, float, str]:
    """
    Determine if a negotiation round has converged, hit deadlock, or should continue.

    Returns:
        (status, price_gap_pct, summary_message)
        where status is one of:
        - "CONVERGED": Mutual agreement reached (price gap <= 2% and within ceiling)
        - "DEADLOCK": Reached max rounds or supplier price strictly exceeds ceiling budget
        - "MAX_ROUNDS_REACHED": Reached max rounds, final compromise offer available
        - "CONTINUE": Gap still significant, proceed to next round
    """
    b_price = buyer_offer.unit_price_vnd
    s_price = supplier_offer.unit_price_vnd

    price_gap_pct = abs(s_price - b_price) / max(1.0, b_price) * 100.0
    time_gap_days = abs(supplier_offer.lead_time_days - buyer_offer.lead_time_days)

    # Condition 1: Direct Convergence
    # Price difference <= threshold (e.g. 2%) AND supplier price is within ceiling
    if price_gap_pct <= convergence_threshold_pct and s_price <= ceiling_unit_price:
        return (
            "CONVERGED",
            round(price_gap_pct, 2),
            f"Đạt thỏa thuận (Chênh lệch giá chỉ {price_gap_pct:.1f}% <= {convergence_threshold_pct}%). "
            f"Đơn giá chốt: {s_price:,.0f}đ, Giao hàng: {supplier_offer.lead_time_days} ngày.",
        )

    # Condition 2: Max Rounds Reached
    if round_number >= max_rounds:
        if s_price <= ceiling_unit_price:
            return (
                "MAX_ROUNDS_REACHED",
                round(price_gap_pct, 2),
                f"Đã đạt số vòng tối đa ({max_rounds} rounds). Hai bên tiệm cận mức giá chốt {s_price:,.0f}đ "
                f"(trong ngân sách trần {ceiling_unit_price:,.0f}đ).",
            )
        else:
            return (
                "DEADLOCK",
                round(price_gap_pct, 2),
                f"Bế tắc đàm phán: Sau {max_rounds} rounds, giá đối tác ({s_price:,.0f}đ) "
                f"vẫn vượt ngân sách trần cho phép ({ceiling_unit_price:,.0f}đ).",
            )

    # Condition 3: Continue Negotiation
    return (
        "CONTINUE",
        round(price_gap_pct, 2),
        f"Chênh lệch giá còn {price_gap_pct:.1f}% (Bên mua: {b_price:,.0f}đ vs Đối tác: {s_price:,.0f}đ, "
        f"Lệch hạn giao: {time_gap_days} ngày). Tiếp tục thương lượng vòng {round_number + 1}.",
    )


# ───────────────────────────────────────────────────────────────────
# Self-Test Runner
# ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("TESTING MULTI-ATTRIBUTE UTILITY THEORY (MAUT) & ARBITER")
    print("=" * 60)

    # Test 1: STMicroelectronics Offer Evaluation (156k, 3 days, Net 15, 24m)
    stmicro_final = ContractOffer(
        unit_price_vnd=156000.0,
        lead_time_days=3,
        moq=470,
        payment_terms="Net 15",
        warranty_months=24,
    )
    score_stmicro = calculate_maut_score(
        offer=stmicro_final,
        target_unit_price=142000.0,
        ceiling_unit_price=160000.0,
        max_acceptable_lead_time_days=14,
        supplier_reliability_rating=4.9,
        priority=PriorityType.BALANCED,
    )
    print(f"▶ STMicroelectronics Evaluation (156k - Giao 3 ngày):")
    print(f"  Cost Score:     {score_stmicro.cost_score}/100")
    print(f"  Delivery Score: {score_stmicro.delivery_score}/100")
    print(f"  Terms Score:    {score_stmicro.terms_score}/100")
    print(f"  Risk Score:     {score_stmicro.risk_score}/100")
    print(f"  TOTAL UTILITY:  {score_stmicro.total_utility}/100")

    # Test 2: Digi-Key Offer Evaluation (148k, 9 days, Net 30, 12m)
    digikey_final = ContractOffer(
        unit_price_vnd=148000.0,
        lead_time_days=9,
        moq=470,
        payment_terms="Net 30",
        warranty_months=12,
    )
    score_digikey = calculate_maut_score(
        offer=digikey_final,
        target_unit_price=142000.0,
        ceiling_unit_price=160000.0,
        max_acceptable_lead_time_days=14,
        supplier_reliability_rating=4.3,
        priority=PriorityType.BALANCED,
    )
    print(f"\n▶ Digi-Key Evaluation (148k - Giao 9 ngày):")
    print(f"  Cost Score:     {score_digikey.cost_score}/100")
    print(f"  Delivery Score: {score_digikey.delivery_score}/100")
    print(f"  Terms Score:    {score_digikey.terms_score}/100")
    print(f"  Risk Score:     {score_digikey.risk_score}/100")
    print(f"  TOTAL UTILITY:  {score_digikey.total_utility}/100")

    # Test 3: Convergence Test
    buyer_test_offer = ContractOffer(unit_price_vnd=154500.0, lead_time_days=3, moq=470)
    status, gap, msg = evaluate_convergence(
        buyer_offer=buyer_test_offer,
        supplier_offer=stmicro_final,
        round_number=2,
        max_rounds=3,
        ceiling_unit_price=160000.0,
    )
    print(f"\n▶ Convergence Check:")
    print(f"  Status: {status} (Gap: {gap}%)")
    print(f"  Message: {msg}")
    print("=" * 60)

