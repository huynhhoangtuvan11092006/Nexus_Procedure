"""
NexusProcure AI - Strategic Reviewer Agent & Supply Chain Risk Auditor.

Acts as the senior auditor before executive sign-off:
1. Conducts Multi-Attribute Utility Theory (MAUT) scoring across all negotiated offers.
2. Performs Supply Chain Risk Analysis (cost trade-off vs production stoppage risks).
3. Produces a clear Executive Recommendation Matrix for the Manager Checkpoint.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.schemas import (
    ContractOffer,
    MultiAttributeScore,
    PriorityType,
    SupplierEvaluation,
)
from app.core.state import ProcurementState
from app.core.utility import calculate_maut_score

logger = logging.getLogger(__name__)


def evaluate_negotiated_offers(
    negotiation_results: Dict[str, Dict[str, Any]],
    candidate_profiles: List[Dict[str, Any]],
    net_procurement_qty: int,
    target_unit_price: float,
    ceiling_unit_price: float,
    max_acceptable_lead_time_days: int = 14,
    priority: PriorityType = PriorityType.BALANCED,
) -> List[SupplierEvaluation]:
    """
    Score and rank all negotiated offers using MAUT and financial risk modeling.
    """
    cand_map = {c["supplier_id"]: c for c in candidate_profiles if isinstance(c, dict)}
    evaluations: List[SupplierEvaluation] = []

    for sid, result in negotiation_results.items():
        offer_data = result.get("final_offer", {})
        offer = ContractOffer(**offer_data) if isinstance(offer_data, dict) else offer_data

        cand = cand_map.get(sid, {})
        supplier_name = cand.get("supplier_name", result.get("supplier_name", sid))
        reliability = cand.get("reliability_score", 4.5)

        # 1. Compute MAUT Scores
        scores = calculate_maut_score(
            offer=offer,
            target_unit_price=target_unit_price,
            ceiling_unit_price=ceiling_unit_price,
            max_acceptable_lead_time_days=max_acceptable_lead_time_days,
            supplier_reliability_rating=reliability,
            priority=priority,
        )

        # 2. Total cost
        total_cost = offer.unit_price_vnd * net_procurement_qty

        # 3. Budget and Schedule checks
        is_within_budget = offer.unit_price_vnd <= ceiling_unit_price
        is_on_time = offer.lead_time_days <= max_acceptable_lead_time_days

        # 4. Risk assessment description
        buffer_days = max_acceptable_lead_time_days - offer.lead_time_days
        if buffer_days >= 7:
            risk_desc = (
                f"Rủi ro CỰC THẤP. Thời gian giao {offer.lead_time_days} ngày tạo vùng đệm an toàn "
                f"{buffer_days} ngày trước hạn dừng chuyền. Uy tín NCC đạt {reliability}/5.0."
            )
        elif buffer_days >= 3:
            risk_desc = (
                f"Rủi ro TRUNG BÌNH. Thời gian giao {offer.lead_time_days} ngày (vùng đệm {buffer_days} ngày). "
                "Cần bộ phận Mua hàng theo dõi sát sao tiến độ giao vận."
            )
        else:
            risk_desc = (
                f"Rủi ro CAO. Thời gian giao {offer.lead_time_days} ngày sát sạt hạn chót. "
                "Bất kỳ sự cố vận chuyển nào cũng có thể làm gián đoạn dây chuyền sản xuất."
            )

        evaluations.append(
            SupplierEvaluation(
                supplier_id=sid,
                supplier_name=supplier_name,
                final_offer=offer,
                total_cost_vnd=total_cost,
                scores=scores,
                is_within_budget=is_within_budget,
                is_on_time=is_on_time,
                risk_assessment=risk_desc,
                recommendation_rank=1,  # Will sort and assign ranks below
            )
        )

    # Rank by total utility descending
    evaluations.sort(key=lambda e: e.scores.total_utility, reverse=True)
    for rank, ev in enumerate(evaluations, start=1):
        ev.recommendation_rank = rank

    return evaluations


def generate_executive_risk_report(
    evaluations: List[SupplierEvaluation],
    net_procurement_qty: int,
    item_name: str,
) -> str:
    """
    Format a comprehensive audit and trade-off comparison report for the Human Manager.
    """
    if not evaluations:
        return "Không có dữ liệu đánh giá nhà cung cấp."

    top_eval = evaluations[0]
    report_lines = [
        "═══════════════════════════════════════════════════════════════════════════════",
        "         BÁO CÁO ĐÁNH GIÁ PHƯƠNG ÁN & TƯ VẤN LỰA CHỌN ĐỐI TÁC MUA HÀNG         ",
        "═══════════════════════════════════════════════════════════════════════════════",
        f"Mặt hàng cần mua: {item_name}",
        f"Số lượng đặt mua thực tế: {net_procurement_qty:,} chiếc\n",
        "1. TỔNG HỢP KẾT QUẢ ĐÀM PHÁN VÀ SO SÁNH CÁC PHƯƠNG ÁN:",
    ]

    for ev in evaluations:
        offer = ev.final_offer
        rank_badge = "★ PHƯƠNG ÁN ĐỀ XUẤT TỐI ƯU" if ev.recommendation_rank == 1 else f"PHƯƠNG ÁN THAM KHẢO #{ev.recommendation_rank}"
        report_lines.extend([
            f"  [{rank_badge}] {ev.supplier_name} ({ev.supplier_id})",
            f"   • Đơn giá thương lượng được: {offer.unit_price_vnd:,.0f} VNĐ/chiếc (Tổng giá trị: {ev.total_cost_vnd:,.0f} VNĐ)",
            f"   • Thời hạn nhận hàng:        {offer.lead_time_days} ngày ({'Kịp tiến độ' if ev.is_on_time else 'Chậm tiến độ'})",
            f"   • Điều khoản hợp đồng:       {offer.payment_terms} | Bảo hành: {offer.warranty_months} tháng",
            f"   • Điểm đánh giá tổng hợp:    {ev.scores.total_utility:.1f}/100 "
            f"(Chi phí: {ev.scores.cost_score:.1f} | Tiến độ: {ev.scores.delivery_score:.1f} | Độ tin cậy: {ev.scores.risk_score:.1f})",
            f"   • Đánh giá mức độ an toàn:   {ev.risk_assessment}",
            "",
        ])

    # Trade-off comparative insight
    if len(evaluations) >= 2:
        ev1 = evaluations[0]
        ev2 = evaluations[1]
        cost_diff = abs(ev1.total_cost_vnd - ev2.total_cost_vnd)
        lead_diff = abs(ev1.final_offer.lead_time_days - ev2.final_offer.lead_time_days)

        report_lines.extend([
            "2. PHÂN TÍCH SO SÁNH GIỮA CÁC ĐỐI TÁC:",
            f"   • Chênh lệch ngân sách giữa 2 bên: {cost_diff:,.0f} VNĐ.",
            f"   • Chênh lệch thời gian giao hàng: {lead_diff} ngày.",
            f"   • CĂN CỨ ĐỀ XUẤT: {ev1.supplier_name} đạt điểm tổng hợp cao nhất ({ev1.scores.total_utility:.1f} điểm).",
        ])

        if ev1.final_offer.lead_time_days < ev2.final_offer.lead_time_days:
            report_lines.append(
                f"     -> Lựa chọn {ev1.supplier_name} giúp nhà máy chủ động hoàn toàn về tiến độ sản xuất (giao sau {ev1.final_offer.lead_time_days} ngày),\n"
                f"        loại bỏ nguy cơ chậm trễ hoặc dừng dây chuyền, với mức chênh lệch chi phí hợp lý ({cost_diff:,.0f} VNĐ)."
            )
        else:
            report_lines.append(
                f"     -> Lựa chọn {ev1.supplier_name} giúp doanh nghiệp tiết kiệm tối đa ngân sách ({cost_diff:,.0f} VNĐ)\n"
                f"        trong khi vẫn đáp ứng tốt thời hạn giao hàng theo yêu cầu."
            )

    report_lines.append("═══════════════════════════════════════════════════════════════════════════════")
    return "\n".join(report_lines)


def reviewer_node(state: ProcurementState) -> Dict[str, Any]:
    """
    LangGraph Node: Reviewer Agent.
    Audits negotiation outcomes, runs MAUT scoring, assesses supply chain risk,
    and produces official purchase recommendation.
    """
    logger.info("[ReviewerNode] Auditing negotiation results and generating recommendations...")

    results = state.get("negotiation_results", {})
    candidates = state.get("candidate_suppliers", [])
    net_qty = state.get("net_procurement_qty", 470)
    item_name = state.get("item_name", "Vi điều khiển")
    target_price = state.get("target_unit_price", 142000.0)
    ceiling_price = state.get("ceiling_unit_price", 160000.0)
    priority_str = state.get("priority", "BALANCED")

    priority = PriorityType[priority_str] if priority_str in PriorityType.__members__ else PriorityType.BALANCED

    evaluations = evaluate_negotiated_offers(
        negotiation_results=results,
        candidate_profiles=candidates,
        net_procurement_qty=net_qty,
        target_unit_price=target_price,
        ceiling_unit_price=ceiling_price,
        priority=priority,
    )

    report = generate_executive_risk_report(evaluations, net_qty, item_name)
    top_supplier_id = evaluations[0].supplier_id if evaluations else ""

    logger.info(
        "[ReviewerNode] Recommendation: %s (Utility: %.2f)",
        top_supplier_id,
        evaluations[0].scores.total_utility if evaluations else 0.0,
    )

    return {
        "evaluations": [ev.model_dump() for ev in evaluations],
        "recommended_supplier_id": top_supplier_id,
        "risk_assessment_report": report,
        "workflow_status": "PENDING_APPROVAL",
    }


# ───────────────────────────────────────────────────────────────────
# Self-Test Runner
# ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 70)
    print("TESTING REVIEWER AGENT")
    print("=" * 70)

    mock_state: ProcurementState = {
        "pr_id": "PR-001",
        "item_name": "Vi điều khiển STM32F407VGT6",
        "net_procurement_qty": 470,
        "target_unit_price": 142000.0,
        "ceiling_unit_price": 160000.0,
        "priority": "BALANCED",
        "candidate_suppliers": [
            {
                "supplier_id": "SUP-STMICRO",
                "supplier_name": "STMicroelectronics Authorized Distributor",
                "reliability_score": 4.9,
            },
            {
                "supplier_id": "SUP-DIGIKEY",
                "supplier_name": "Digi-Key Electronics Asia (Global Distributor)",
                "reliability_score": 4.5,
            },
        ],
        "negotiation_results": {
            "SUP-STMICRO": {
                "supplier_id": "SUP-STMICRO",
                "supplier_name": "STMicroelectronics Authorized Distributor",
                "final_offer": {
                    "unit_price_vnd": 157500.0,
                    "lead_time_days": 3,
                    "moq": 100,
                    "payment_terms": "Net 15",
                    "warranty_months": 24,
                    "concession_notes": "Hạ giá đổi lấy Net 15",
                },
            },
            "SUP-DIGIKEY": {
                "supplier_id": "SUP-DIGIKEY",
                "supplier_name": "Digi-Key Electronics Asia (Global Distributor)",
                "final_offer": {
                    "unit_price_vnd": 153000.0,
                    "lead_time_days": 9,
                    "moq": 200,
                    "payment_terms": "Net 30",
                    "warranty_months": 12,
                    "concession_notes": "Giao 9 ngày có phụ phí",
                },
            },
        },
    }

    res = reviewer_node(mock_state)
    print(res["risk_assessment_report"])

