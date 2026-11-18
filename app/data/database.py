"""
NexusProcure AI - Database Management Module.

Provides SQLite connection handling, schema definitions, and query helpers.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional
from app.core.config import settings


def get_db_connection() -> sqlite3.Connection:
    """Create and return a connection to the SQLite procurement database."""
    conn = sqlite3.connect(str(settings.SQLITE_DB_PATH))
    conn.row_factory = sqlite3.Row  # Enables column access by name
    return conn


def init_db(drop_existing: bool = False) -> None:
    """
    Initialize SQLite database tables.
    
    Creates:
    - inventory: Stock levels, safety stock, standard costs
    - suppliers: Vendor profiles, personas, ratings, lead times
    - historical_deals: Past purchase records used by RAG benchmark
    - purchase_requests: Purchase requests and test use cases (PR-001..PR-004)
    - negotiation_logs: Persistent transcript of negotiation rounds
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    if drop_existing:
        cursor.execute("DROP TABLE IF EXISTS negotiation_logs")
        cursor.execute("DROP TABLE IF EXISTS purchase_requests")
        cursor.execute("DROP TABLE IF EXISTS historical_deals")
        cursor.execute("DROP TABLE IF EXISTS suppliers")
        cursor.execute("DROP TABLE IF EXISTS inventory")

    # 1. Inventory Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        item_id TEXT PRIMARY KEY,
        item_name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit TEXT NOT NULL DEFAULT 'chiếc',
        on_hand_qty INTEGER NOT NULL DEFAULT 0,
        safety_stock_qty INTEGER NOT NULL DEFAULT 0,
        standard_cost_vnd REAL NOT NULL,
        description TEXT
    );
    """)

    # 2. Suppliers Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS suppliers (
        supplier_id TEXT PRIMARY KEY,
        supplier_name TEXT NOT NULL,
        tier TEXT NOT NULL,
        reliability_score REAL NOT NULL,
        quality_rating REAL NOT NULL,
        standard_lead_time_days INTEGER NOT NULL,
        payment_terms_default TEXT NOT NULL DEFAULT 'Net 30',
        contact_email TEXT,
        persona_type TEXT NOT NULL,
        description TEXT
    );
    """)

    # 3. Historical Deals Table (used as RAG ground truth)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historical_deals (
        deal_id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT NOT NULL,
        supplier_id TEXT NOT NULL,
        deal_date TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price_vnd REAL NOT NULL,
        discount_pct REAL NOT NULL DEFAULT 0.0,
        lead_time_days INTEGER NOT NULL,
        payment_terms TEXT NOT NULL,
        warranty_months INTEGER NOT NULL DEFAULT 12,
        deal_outcome TEXT NOT NULL,
        notes TEXT,
        FOREIGN KEY (item_id) REFERENCES inventory (item_id),
        FOREIGN KEY (supplier_id) REFERENCES suppliers (supplier_id)
    );
    """)

    # 4. Purchase Requests Table (Stores test usecases and live requests)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS purchase_requests (
        pr_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        item_id TEXT NOT NULL,
        requested_qty INTEGER NOT NULL,
        target_delivery_date TEXT NOT NULL,
        max_budget_vnd REAL NOT NULL,
        priority TEXT NOT NULL DEFAULT 'BALANCED',
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (item_id) REFERENCES inventory (item_id)
    );
    """)

    # 5. Negotiation Logs Table (Audit trail & analytics for each round)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS negotiation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        pr_id TEXT NOT NULL,
        supplier_id TEXT NOT NULL,
        round_number INTEGER NOT NULL,
        buyer_offer_price REAL,
        buyer_lead_time_days INTEGER,
        buyer_terms TEXT,
        buyer_reasoning TEXT,
        supplier_offer_price REAL,
        supplier_lead_time_days INTEGER,
        supplier_terms TEXT,
        supplier_reasoning TEXT,
        gap_pct REAL,
        mediator_status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()


# ───────────────────────────────────────────────────────────────────
# Query Helper Functions
# ───────────────────────────────────────────────────────────────────

def get_inventory_item(item_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve an inventory item by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory WHERE item_id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def find_inventory_by_name(name_query: str) -> Optional[Dict[str, Any]]:
    """
    Intelligently search inventory by item_name, item_id, or key technical terms.
    Returns matched inventory record or None if not found.
    """
    if not name_query or not name_query.strip():
        return None
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    query_lower = name_query.strip().lower()

    # 1. Exact match on item_id
    for r in rows:
        if r["item_id"].lower() == query_lower:
            return r

    # 2. Substring match on item_name
    for r in rows:
        if r["item_name"].lower() in query_lower or query_lower in r["item_name"].lower():
            return r

    # 3. Technical keyword heuristics
    keywords_map = {
        "stm32": "COMP-STM32F4",
        "esp32": "COMP-ESP32-WROOM",
        "sht31": "COMP-TEMP-SENS",
        "nhiệt": "COMP-TEMP-SENS",
        "oled": "COMP-OLED-096",
        "màn hình": "COMP-OLED-096",
        "relay": "COMP-RELAY-5V",
        "lm2596": "COMP-BUCK-LM2596",
        "hạ áp": "COMP-BUCK-LM2596",
        "ds3231": "COMP-RTC-DS3231",
        "rtc": "COMP-RTC-DS3231",
        "4g": "COMP-TRANS-4G",
        "lte": "COMP-TRANS-4G",
        "quectel": "COMP-TRANS-4G",
        "tụ": "COMP-CAP-100UF",
        "capacitor": "COMP-CAP-100UF",
        "opto": "COMP-OPTOCPL-817",
        "pc817": "COMP-OPTOCPL-817",
    }
    for kw, target_id in keywords_map.items():
        if kw in query_lower:
            for r in rows:
                if r["item_id"] == target_id:
                    return r

    return None


def get_all_inventory() -> List[Dict[str, Any]]:
    """Retrieve all inventory items."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory ORDER BY item_id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_supplier(supplier_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve supplier profile by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suppliers WHERE supplier_id = ?", (supplier_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_suppliers() -> List[Dict[str, Any]]:
    """Retrieve all suppliers."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suppliers ORDER BY supplier_id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_historical_deals(item_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve historical procurement deals, optionally filtered by item_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if item_id:
        cursor.execute("""
            SELECT h.*, s.supplier_name, i.item_name 
            FROM historical_deals h
            JOIN suppliers s ON h.supplier_id = s.supplier_id
            JOIN inventory i ON h.item_id = i.item_id
            WHERE h.item_id = ?
            ORDER BY h.deal_date DESC
        """, (item_id,))
    else:
        cursor.execute("""
            SELECT h.*, s.supplier_name, i.item_name 
            FROM historical_deals h
            JOIN suppliers s ON h.supplier_id = s.supplier_id
            JOIN inventory i ON h.item_id = i.item_id
            ORDER BY h.deal_date DESC
        """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_purchase_request(pr_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a purchase request by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pr.*, i.item_name, i.category, i.unit, i.on_hand_qty, i.safety_stock_qty, i.standard_cost_vnd
        FROM purchase_requests pr
        JOIN inventory i ON pr.item_id = i.item_id
        WHERE pr.pr_id = ?
    """, (pr_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_negotiation_sessions() -> List[Dict[str, Any]]:
    """Retrieve distinct negotiation sessions with summary metrics."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            session_id,
            pr_id,
            supplier_id,
            MAX(round_number) as total_rounds,
            MIN(gap_pct) as final_gap_pct,
            MAX(created_at) as last_updated
        FROM negotiation_logs
        GROUP BY session_id
        ORDER BY last_updated DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]

    for r in rows:
        cursor.execute("""
            SELECT mediator_status, buyer_offer_price, supplier_offer_price 
            FROM negotiation_logs 
            WHERE session_id = ? 
            ORDER BY round_number DESC LIMIT 1
        """, (r["session_id"],))
        last_row = cursor.fetchone()
        if last_row:
            r["final_status"] = last_row["mediator_status"]
            r["final_buyer_price"] = last_row["buyer_offer_price"]
            r["final_supplier_price"] = last_row["supplier_offer_price"]
        else:
            r["final_status"] = "UNKNOWN"
            r["final_buyer_price"] = 0
            r["final_supplier_price"] = 0

    conn.close()
    return rows


def get_session_transcript(session_id: str) -> List[Dict[str, Any]]:
    """Retrieve full chronological transcript of rounds for a session."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM negotiation_logs
        WHERE session_id = ?
        ORDER BY round_number ASC
    """, (session_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def check_supplier_item_compatibility(item_name: str, supplier_name: str) -> Dict[str, Any]:
    """
    Check if the supplier carries or specializes in the requested item.
    Returns compatibility category, description, and status tag.
    """
    item_lower = (item_name or "").lower()
    sup_lower = (supplier_name or "").lower()

    # 1. Broad global distributors carry everything
    if "digi-key" in sup_lower or "mouser" in sup_lower or "toàn cầu" in sup_lower or "đại lý" in sup_lower:
        return {
            "is_compatible": True,
            "status_type": "distributor",
            "badge_color": "#2563EB",
            "status_title": "Đại lý phân phối tổng hợp",
            "message": f"{supplier_name} là nhà phân phối linh kiện quy mô lớn, có năng lực cung ứng đa dạng mặt hàng.",
        }

    # 2. STMicroelectronics: Microcontrollers & semiconductors
    if "stmicro" in sup_lower or "alpha" in sup_lower or "bán dẫn" in sup_lower:
        if any(k in item_lower for k in ["stm32", "arm", "vi điều khiển", "microcontroller", "mcu", "bán dẫn", "chip", "pc817"]):
            return {
                "is_compatible": True,
                "status_type": "authorized",
                "badge_color": "#16A34A",
                "status_title": "Đúng chuyên ngành chính hãng",
                "message": f"{supplier_name} là đối tác ủy quyền chính thức cho dòng vi điều khiển và chip bán dẫn này.",
            }
        else:
            return {
                "is_compatible": False,
                "status_type": "out_of_scope",
                "badge_color": "#D97706",
                "status_title": "Ngoài danh mục chủ lực",
                "message": f"{supplier_name} chuyên về vi điều khiển & bán dẫn. Mặt hàng này sẽ được cung ứng theo dạng nhập ủy thác đặc thù.",
            }

    # 3. Sensirion: Sensors & environmental tech
    if "sensirion" in sup_lower or "cảm biến" in sup_lower or "sensor" in sup_lower:
        if any(k in item_lower for k in ["sht31", "sht", "cảm biến", "sensor", "nhiệt", "ẩm", "ds3231", "gas"]):
            return {
                "is_compatible": True,
                "status_type": "authorized",
                "badge_color": "#16A34A",
                "status_title": "Đúng chuyên ngành chính hãng",
                "message": f"{supplier_name} là đối tác ủy quyền của Sensirion, chuyên biệt dòng cảm biến công nghiệp độ chính xác cao.",
            }
        else:
            return {
                "is_compatible": False,
                "status_type": "out_of_scope",
                "badge_color": "#D97706",
                "status_title": "Ngoài danh mục chủ lực",
                "message": f"{supplier_name} chuyên về cảm biến. Đàm phán mặt hàng này sẽ phản ánh chi phí gom hàng đặc biệt.",
            }

    # 4. Winstar Display: Displays & modules
    if "winstar" in sup_lower or "display" in sup_lower or "màn hình" in sup_lower:
        if any(k in item_lower for k in ["oled", "lcd", "màn hình", "display", "tft"]):
            return {
                "is_compatible": True,
                "status_type": "authorized",
                "badge_color": "#16A34A",
                "status_title": "Nhà máy sản xuất chuyên ngành",
                "message": f"{supplier_name} là nhà máy sản xuất trực tiếp dòng màn hình hiển thị công nghiệp.",
            }
        else:
            return {
                "is_compatible": False,
                "status_type": "out_of_scope",
                "badge_color": "#D97706",
                "status_title": "Ngoài danh mục chủ lực",
                "message": f"{supplier_name} là nhà máy chuyên sản xuất màn hình. Mặt hàng này cần chi phí gia công/nhập ngoài phụ trội.",
            }

    # 5. Default custom supplier
    return {
        "is_compatible": True,
        "status_type": "custom",
        "badge_color": "#475569",
        "status_title": "Đối tác thương mại",
        "message": f"Phiên đàm phán mô phỏng trực tiếp theo các giới hạn và báo giá bạn thiết lập.",
    }


def get_platform_analytics() -> Dict[str, Any]:
    """
    Aggregate overall platform performance metrics across all completed sessions in SQLite:
    - Success Rate %
    - Average rounds
    - Average Buyer Concession
    - Average Seller Concession
    - Average Price Gap %
    """
    sessions = get_all_negotiation_sessions()
    if not sessions:
        return {
            "total_sessions": 0,
            "success_rate_pct": 0.0,
            "avg_rounds": 0.0,
            "avg_buyer_concession": 0.0,
            "avg_seller_concession": 0.0,
            "avg_price_gap_pct": 0.0,
        }

    total = len(sessions)
    successes = sum(1 for s in sessions if s.get("final_status") in ("SUCCESS", "CONVERGED", "COMPLETED"))
    success_rate = (successes / total) * 100.0 if total > 0 else 0.0
    avg_rounds = sum(s.get("total_rounds", 1) for s in sessions) / total if total > 0 else 0.0

    buyer_concessions = []
    seller_concessions = []
    final_gaps = []

    for s in sessions:
        trans = get_session_transcript(s["session_id"])
        if trans:
            first_r = trans[0]
            last_r = trans[-1]
            b_init = first_r.get("buyer_offer_price") or 0.0
            b_final = last_r.get("buyer_offer_price") or 0.0
            s_init = first_r.get("supplier_offer_price") or 0.0
            s_final = last_r.get("supplier_offer_price") or 0.0
            gap = last_r.get("gap_pct") or 0.0

            if b_init > 0 and b_final >= b_init:
                buyer_concessions.append(b_final - b_init)
            if s_init > 0 and s_init >= s_final:
                seller_concessions.append(s_init - s_final)
            final_gaps.append(gap)

    avg_b_conc = sum(buyer_concessions) / len(buyer_concessions) if buyer_concessions else 0.0
    avg_s_conc = sum(seller_concessions) / len(seller_concessions) if seller_concessions else 0.0
    avg_gap = sum(final_gaps) / len(final_gaps) if final_gaps else 0.0

    return {
        "total_sessions": total,
        "success_rate_pct": round(success_rate, 1),
        "avg_rounds": round(avg_rounds, 1),
        "avg_buyer_concession": round(avg_b_conc, 0),
        "avg_seller_concession": round(avg_s_conc, 0),
        "avg_price_gap_pct": round(avg_gap, 1),
    }


