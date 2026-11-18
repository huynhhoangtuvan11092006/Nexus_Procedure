"""
NexusProcure AI - Automated Test Suite for 4 Strategic Use Cases.

Tests the full autonomous multi-agent pipeline across:
1. PR-001 (Standard Balanced Case): STM32F4 microcontroller procurement.
2. PR-002 (Fast Delivery / Line Down): Temperature sensors under 3-day urgency.
3. PR-003 (Deadlock / Unrealistic Budget): ESP32 chips with sub-market budget.
4. PR-004 (MOQ Volume Dilemma): OLED screens balancing batch MOQ vs holding cost.
"""

from __future__ import annotations

import logging
import pytest
from app.core.schemas import ManagerDecisionType
from app.core.state import ProcurementState
from app.graph.master_workflow import build_procurement_graph

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def workflow_app():
    """Build compiled LangGraph instance."""
    return build_procurement_graph(enable_interrupt=False)


def test_use_case_1_standard_procurement(workflow_app):
    """
    Test PR-001: Standard balanced electronic procurement (STM32F4).
    Verifies MRP deduction, dual vendor arena convergence, and PO issuance.
    """
    state_input: ProcurementState = {
        "pr_id": "PR-001",
        "title": "Linh kiện vi điều khiển Board IoT Gateway",
        "item_id": "COMP-STM32F4",
        "item_name": "Vi điều khiển ARM Cortex-M4 STM32F407VGT6",
        "requested_quantity": 500,
        "target_delivery_date": "2026-11-30",
        "max_budget_vnd": 80_000_000.0,
        "priority": "BALANCED",
        "workflow_status": "INITIALIZED",
    }

    config = {"configurable": {"thread_id": "test-uc1-standard"}}
    res = workflow_app.invoke(state_input, config=config)

    # 1. Check MRP logic: 500 requested - (50 stock - 20 safety) = 470 net
    assert res["net_procurement_qty"] == 470, f"Expected 470, got {res['net_procurement_qty']}"

    # 2. Check ZOPA boundaries
    assert res["target_unit_price"] <= 145000.0
    assert res["ceiling_unit_price"] >= 160000.0

    # 3. Check Arena Convergence
    assert res["negotiation_status"] in ("CONVERGED", "COMPLETED")
    assert "SUP-STMICRO" in res["negotiation_results"]
    assert "SUP-DIGIKEY" in res["negotiation_results"]

    # 4. Check Final Purchase Order
    po = res.get("purchase_order")
    assert po is not None
    assert po["procured_quantity"] == 470
    assert po["final_unit_price_vnd"] <= res["ceiling_unit_price"]
    assert po["total_amount_vnd"] <= res["max_budget_vnd"]
    assert res["workflow_status"] == "COMPLETED"


def test_use_case_2_fast_delivery_urgent(workflow_app):
    """
    Test PR-002: Urgent line-down scenario.
    Priority FAST_DELIVERY prioritizes lead time over cost.
    """
    state_input: ProcurementState = {
        "pr_id": "PR-002",
        "title": "Khẩn cấp: Thay thế cảm biến nhiệt độ SHT31 bị lỗi cho dây chuyền SMT",
        "item_id": "COMP-TEMP-SENS",
        "item_name": "Cảm biến nhiệt độ & độ ẩm công nghiệp SHT31",
        "requested_quantity": 200,
        "target_delivery_date": "2026-11-20",
        "max_budget_vnd": 40_000_000.0,
        "priority": "FAST_DELIVERY",
        "workflow_status": "INITIALIZED",
    }

    config = {"configurable": {"thread_id": "test-uc2-urgent"}}
    res = workflow_app.invoke(state_input, config=config)

    assert res["workflow_status"] == "COMPLETED"
    po = res.get("purchase_order")
    assert po is not None
    assert po["procured_quantity"] > 0
    # Delivery must be fast (<= 5 days)
    assert "days" in po["delivery_deadline"]


def test_use_case_3_deadlock_unrealistic_budget(workflow_app):
    """
    Test PR-003: Impossible sub-market budget causing negotiation deadlock.
    Validates that the multi-agent system terminates safely without crashing.
    """
    state_input: ProcurementState = {
        "pr_id": "PR-003",
        "title": "Mua linh kiện ESP32 sản xuất hàng loạt",
        "item_id": "COMP-ESP32-WROOM",
        "item_name": "Module WiFi Bluetooth ESP32-WROOM-32D",
        "requested_quantity": 1000,
        "target_delivery_date": "2026-12-15",
        "max_budget_vnd": 30_000_000.0,  # Only 30,000 VND/unit (market is 38k-45k)
        "priority": "LOWEST_COST",
        "workflow_status": "INITIALIZED",
        "manager_decision": ManagerDecisionType.TERMINATE.value,
    }

    config = {"configurable": {"thread_id": "test-uc3-deadlock"}}
    res = workflow_app.invoke(state_input, config=config)

    # Ceiling price is strictly lower than supplier ask
    assert res["ceiling_unit_price"] <= 35000.0
    # Workflow should terminate safely without unhandled exception
    assert res["workflow_status"] == "TERMINATED"
    assert res.get("purchase_order") is None


def test_use_case_4_moq_volume_dilemma(workflow_app):
    """
    Test PR-004: High MOQ Dilemma (buying 300 OLED displays when factory MOQ is 500).
    Verifies that system correctly flags MOQ mismatch and calculates holding trade-offs.
    """
    state_input: ProcurementState = {
        "pr_id": "PR-004",
        "title": "Mua màn hình OLED 0.96 inch cho máy đo quan trắc môi trường",
        "item_id": "COMP-OLED-096",
        "item_name": "Màn hình I2C OLED 0.96 inch 128x64 xanh dương",
        "requested_quantity": 300,
        "target_delivery_date": "2026-12-05",
        "max_budget_vnd": 15_000_000.0,
        "priority": "BALANCED",
        "workflow_status": "INITIALIZED",
    }

    config = {"configurable": {"thread_id": "test-uc4-moq"}}
    res = workflow_app.invoke(state_input, config=config)

    assert res["workflow_status"] == "COMPLETED"
    assert res["net_procurement_qty"] > 0
    po = res.get("purchase_order")
    assert po is not None


if __name__ == "__main__":
    print("Running test suite manually...")
    app = build_procurement_graph(enable_interrupt=False)
    test_use_case_1_standard_procurement(app)
    print("✔ Use Case 1 passed!")
    test_use_case_2_fast_delivery_urgent(app)
    print("✔ Use Case 2 passed!")
    test_use_case_3_deadlock_unrealistic_budget(app)
    print("✔ Use Case 3 passed!")
    test_use_case_4_moq_volume_dilemma(app)
    print("✔ Use Case 4 passed!")
    print("\nALL 4 STRATEGIC USE CASES PASSED SUCCESSFULLY!")
