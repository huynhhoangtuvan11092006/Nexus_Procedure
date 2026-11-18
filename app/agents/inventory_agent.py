"""
NexusProcure AI - Inventory Management Agent.

Acts as the intelligent Warehouse & Material Requirements Planning (MRP) Specialist.
Queries SQLite inventory database, checks available and safety stock, and calculates
the exact Net Procurement Quantity needed before engaging suppliers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.core.state import ProcurementState
from app.data.database import get_inventory_item, find_inventory_by_name

logger = logging.getLogger(__name__)


def calculate_net_procurement_quantity(
    requested_quantity: int,
    on_hand_qty: int,
    safety_stock_qty: int,
) -> tuple[int, int, str]:
    """
    Calculate the net procurement quantity factoring in safety stock buffers.

    Parameters
    ----------
    requested_quantity : int
        Raw quantity requested by production in the PR.
    on_hand_qty : int
        Current physical stock present in the warehouse.
    safety_stock_qty : int
        Mandatory buffer stock that must never be depleted.

    Returns
    -------
    tuple[int, int, str]
        (net_procurement_qty, usable_stock, explanation_notes)
    """
    # Usable stock is stock exceeding the mandatory safety buffer
    usable_stock = max(0, on_hand_qty - safety_stock_qty)

    # Net quantity needed from suppliers
    net_procurement_qty = max(0, requested_quantity - usable_stock)

    if usable_stock > 0:
        notes = (
            f"Tồn kho thực tế: {on_hand_qty} chiếc | "
            f"Mức dự phòng an toàn bắt buộc: {safety_stock_qty} chiếc | "
            f"Lượng khả dụng xuất kho ngay: {usable_stock} chiếc. "
            f"-> Lượng thực cần đặt mua: {net_procurement_qty} chiếc "
            f"(Giúp doanh nghiệp tiết kiệm mua dư {usable_stock} chiếc từ nguồn hàng sẵn có)."
        )
    else:
        notes = (
            f"Tồn kho thực tế: {on_hand_qty} chiếc bằng hoặc dưới mức an toàn ({safety_stock_qty} chiếc). "
            f"Không có lượng khả dụng xuất kho. "
            f"-> Cần đặt mua toàn bộ {net_procurement_qty} chiếc từ nhà cung cấp."
        )

    return net_procurement_qty, usable_stock, notes


def inventory_node(state: ProcurementState) -> Dict[str, Any]:
    """
    LangGraph Node for the Inventory Agent.
    
    Reads PR requirements from state, checks stock in SQLite, and writes
    the validated net procurement quantity and inventory notes back to state.
    """
    item_id = state.get("item_id", "")
    requested_qty = state.get("requested_quantity", 0)

    logger.info("[InventoryAgent] Processing inventory check for Item: %s (Requested: %d)", item_id, requested_qty)

    # 1. Query SQLite database for item stock profile
    item_data = get_inventory_item(item_id)
    if not item_data:
        item_data = find_inventory_by_name(state.get("item_name", item_id))

    if not item_data:
        display_name = state.get("item_name") or item_id or "Mặt hàng này"
        logger.warning("[InventoryAgent] Item '%s' not found in inventory DB. Using raw requested quantity.", display_name)
        return {
            "current_stock": 0,
            "safety_stock": 0,
            "net_procurement_qty": requested_qty,
            "inventory_notes": f"Mặt hàng '{display_name}' là sản phẩm mới chưa có trong kho. Cần đặt mua toàn bộ 100% số lượng ({requested_qty:,} chiếc).",
        }

    on_hand_qty = item_data.get("on_hand_qty", 0)
    safety_stock_qty = item_data.get("safety_stock_qty", 0)
    standard_cost = item_data.get("standard_cost_vnd", 0.0)

    # 2. Perform MRP net quantity calculation
    net_qty, usable_stock, notes = calculate_net_procurement_quantity(
        requested_quantity=requested_qty,
        on_hand_qty=on_hand_qty,
        safety_stock_qty=safety_stock_qty,
    )

    savings_estimate_vnd = usable_stock * standard_cost
    if savings_estimate_vnd > 0:
        notes += f" Ước tính giá trị tồn kho tận dụng: {savings_estimate_vnd:,.0f} VNĐ."

    logger.info("[InventoryAgent] Net Quantity to procure: %d (Saved %d from stock)", net_qty, usable_stock)

    # 3. Return state delta
    return {
        "current_stock": on_hand_qty,
        "safety_stock": safety_stock_qty,
        "net_procurement_qty": net_qty,
        "inventory_notes": notes,
    }


# ───────────────────────────────────────────────────────────────────
# Self-Test Runner
# ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("TESTING INVENTORY AGENT (PR-001 Scenario)")
    print("=" * 60)

    mock_state: ProcurementState = {
        "pr_id": "PR-001",
        "item_id": "COMP-STM32F4",
        "requested_quantity": 500,
    }

    result = inventory_node(mock_state)
    print(f"Item ID: {mock_state['item_id']}")
    print(f"Yêu cầu ban đầu: {mock_state['requested_quantity']} chiếc")
    print(f"Tồn kho thực tế: {result['current_stock']} chiếc")
    print(f"Mức an toàn: {result['safety_stock']} chiếc")
    print(f"-> Số lượng thực cần mua: {result['net_procurement_qty']} chiếc")
    print(f"Ghi chú giải trình:\n{result['inventory_notes']}")
    print("=" * 60)

