"""
NexusProcure AI - Database Seeding Script.

Generates realistic mock enterprise procurement data:
- 10 electronic components in inventory
- 5 specialized suppliers with distinct personas
- 50 historical procurement contracts (ground truth for RAG)
- 4 official test use cases (PR-001, PR-002, PR-003, PR-004)
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from app.data.database import get_db_connection, init_db

# Fixed seed for deterministic, reproducible enterprise data
random.seed(42)


# ───────────────────────────────────────────────────────────────────
# 1. Master Data: Inventory Items
# ───────────────────────────────────────────────────────────────────
INVENTORY_DATA = [
    {
        "item_id": "COMP-STM32F4",
        "item_name": "Vi điều khiển ARM Cortex-M4 STM32F407VGT6",
        "category": "Microcontroller",
        "unit": "chiếc",
        "on_hand_qty": 50,
        "safety_stock_qty": 20,
        "standard_cost_vnd": 150000.0,
        "description": "Vi điều khiển 32-bit 168MHz 1MB Flash, 192KB RAM cho thiết bị công nghiệp",
    },
    {
        "item_id": "COMP-ESP32-WROOM",
        "item_name": "Module Wi-Fi / BLE ESP32-WROOM-32D",
        "category": "Wireless Module",
        "unit": "chiếc",
        "on_hand_qty": 100,
        "safety_stock_qty": 50,
        "standard_cost_vnd": 36000.0,
        "description": "Module kết nối không dây IoT chuẩn 2.4GHz công suất thấp",
    },
    {
        "item_id": "COMP-TEMP-SENS",
        "item_name": "Cảm biến nhiệt độ & độ ẩm công nghiệp SHT31",
        "category": "Sensor",
        "unit": "chiếc",
        "on_hand_qty": 10,
        "safety_stock_qty": 10,
        "standard_cost_vnd": 180000.0,
        "description": "Cảm biến độ chính xác cao ±1.5% RH, giao tiếp I2C công nghiệp",
    },
    {
        "item_id": "COMP-OLED-096",
        "item_name": "Màn hình I2C OLED 0.96 inch 128x64 xanh dương",
        "category": "Display",
        "unit": "chiếc",
        "on_hand_qty": 25,
        "safety_stock_qty": 20,
        "standard_cost_vnd": 45000.0,
        "description": "Màn hình hiển thị trạng thái thiết bị, điện áp hoạt động 3.3V-5V",
    },
    {
        "item_id": "COMP-RELAY-5V",
        "item_name": "Module Relay 5V 10A cách ly quang Songle",
        "category": "Actuator",
        "unit": "chiếc",
        "on_hand_qty": 80,
        "safety_stock_qty": 30,
        "standard_cost_vnd": 18000.0,
        "description": "Module đóng cắt điện AC 250V/10A hoặc DC 30V/10A",
    },
    {
        "item_id": "COMP-BUCK-LM2596",
        "item_name": "Mạch hạ áp nguồn xung DC-DC LM2596 3A",
        "category": "Power Supply",
        "unit": "chiếc",
        "on_hand_qty": 60,
        "safety_stock_qty": 20,
        "standard_cost_vnd": 22000.0,
        "description": "Mạch chuyển đổi nguồn dải rộng 4V-40V xuống 1.25V-37V hiệu suất 92%",
    },
    {
        "item_id": "COMP-RTC-DS3231",
        "item_name": "Module thời gian thực độ chính xác cao DS3231",
        "category": "Timing Module",
        "unit": "chiếc",
        "on_hand_qty": 40,
        "safety_stock_qty": 15,
        "standard_cost_vnd": 28000.0,
        "description": "RTC tích hợp bộ thạch anh bù nhiệt độ TCXO cho thiết bị đo đếm",
    },
    {
        "item_id": "COMP-TRANS-4G",
        "item_name": "Module truyền thông công nghiệp 4G LTE Quectel EC25",
        "category": "Wireless Module",
        "unit": "chiếc",
        "on_hand_qty": 15,
        "safety_stock_qty": 10,
        "standard_cost_vnd": 480000.0,
        "description": "Module LTE Cat 4 tốc độ 150Mbps, hỗ trợ định vị GNSS/GPS",
    },
    {
        "item_id": "COMP-CAP-100UF",
        "item_name": "Tụ điện nhôm SMD 100uF 25V Low-ESR",
        "category": "Passive Component",
        "unit": "chiếc",
        "on_hand_qty": 2000,
        "safety_stock_qty": 1000,
        "standard_cost_vnd": 1200.0,
        "description": "Tụ dán lọc nguồn tần số cao cho mạch công suất",
    },
    {
        "item_id": "COMP-OPTOCPL-817",
        "item_name": "Optocoupler PC817 DIP-4 cách ly quang tín hiệu",
        "category": "Optoelectronics",
        "unit": "chiếc",
        "on_hand_qty": 500,
        "safety_stock_qty": 200,
        "standard_cost_vnd": 2500.0,
        "description": "IC cách ly điện áp cao 5000Vrms bảo vệ vi điều khiển",
    },
]


# ───────────────────────────────────────────────────────────────────
# 2. Master Data: Real-world Electronics Suppliers
# ───────────────────────────────────────────────────────────────────
SUPPLIERS_DATA = [
    {
        "supplier_id": "SUP-STMICRO",
        "supplier_name": "STMicroelectronics Authorized Distributor",
        "tier": "Chính hãng",
        "reliability_score": 4.9,
        "quality_rating": 4.9,
        "standard_lead_time_days": 3,
        "payment_terms_default": "Net 30",
        "contact_email": "sales@stmicro-partner.vn",
        "persona_type": "PREMIUM_RIGID",
        "description": "Nhà phân phối ủy quyền chính hãng của STMicroelectronics. Hàng chuẩn 100%, sẵn kho giao nhanh 3 ngày. Giá bán cao, đàm phán nguyên tắc, chỉ giảm tối đa về 156k nếu thanh toán sớm Net 15.",
    },
    {
        "supplier_id": "SUP-DIGIKEY",
        "supplier_name": "Digi-Key Electronics Asia (Global Distributor)",
        "tier": "Đại lý cấp 1",
        "reliability_score": 4.5,
        "quality_rating": 4.6,
        "standard_lead_time_days": 12,
        "payment_terms_default": "Net 30",
        "contact_email": "order@digikey-asia.com",
        "persona_type": "CASHFLOW_FLEXIBLE",
        "description": "Đại lý phân phối linh kiện điện tử quy mô lớn. Giá thành cạnh tranh rẻ (145k), kho quốc tế giao hàng 12 ngày. Sẵn sàng phụ phí nếu bên mua cần giao hàng gấp.",
    },
    {
        "supplier_id": "SUP-WINSTAR",
        "supplier_name": "Winstar Display Manufacturing Co.",
        "tier": "Xưởng sản xuất",
        "reliability_score": 4.5,
        "quality_rating": 4.6,
        "standard_lead_time_days": 7,
        "payment_terms_default": "Advance 50%",
        "contact_email": "b2b@winstar-display.com",
        "persona_type": "VOLUME_MOQ",
        "description": "Nhà máy sản xuất & gia công trực tiếp màn hình OLED/LCD và module hiển thị. Giá xuất xưởng cực rẻ nhưng chỉ nhận đơn hàng số lượng lớn (MOQ 1.000 cái).",
    },
    {
        "supplier_id": "SUP-MOUSER",
        "supplier_name": "Mouser Electronics Vietnam",
        "tier": "Đại lý nhập khẩu",
        "reliability_score": 4.3,
        "quality_rating": 4.4,
        "standard_lead_time_days": 8,
        "payment_terms_default": "Net 45",
        "contact_email": "contact@mouser.vn",
        "persona_type": "COMPROMISE",
        "description": "Nhà nhập khẩu và phân phối linh kiện bán dẫn, IC nguồn đa ngành. Phong cách đàm phán ôn hòa, sẵn sàng thỏa hiệp chia đôi khoảng cách giá để giữ quan hệ đối tác.",
    },
    {
        "supplier_id": "SUP-SENSIRION",
        "supplier_name": "Sensirion Official Partner (Sensirion AG)",
        "tier": "Chuyên gia cảm biến",
        "reliability_score": 4.9,
        "quality_rating": 4.9,
        "standard_lead_time_days": 2,
        "payment_terms_default": "Net 15",
        "contact_email": "support@sensirion-partner.vn",
        "persona_type": "RAPID_DISPATCH",
        "description": "Đối tác ủy quyền của hãng Sensirion Thụy Sĩ. Cung cấp độc quyền cảm biến nhiệt độ - độ ẩm SHT31 độ chính xác cao, giao hỏa tốc 2 ngày cứu dây chuyền khẩn cấp.",
    },
]


# ───────────────────────────────────────────────────────────────────
# 3. Master Data: Purchase Requests (Test Use Cases)
# ───────────────────────────────────────────────────────────────────
PURCHASE_REQUESTS_DATA = [
    {
        "pr_id": "PR-001",
        "title": "Mua linh kiện vi điều khiển STM32F4 cho lô sản xuất Gateway IoT",
        "item_id": "COMP-STM32F4",
        "requested_qty": 500,
        "target_delivery_date": "2026-11-30",
        "max_budget_vnd": 80000000.0,  # 160.000 VND / piece
        "priority": "BALANCED",
        "status": "PENDING",
    },
    {
        "pr_id": "PR-002",
        "title": "Khẩn cấp: Thay thế cảm biến nhiệt độ SHT31 bị lỗi cho dây chuyền SMT",
        "item_id": "COMP-TEMP-SENS",
        "requested_qty": 200,
        "target_delivery_date": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"),
        "max_budget_vnd": 40000000.0,  # 200.000 VND / piece (Ngân sách thoáng để ưu tiên giao ngay)
        "priority": "FAST_DELIVERY",
        "status": "PENDING",
    },
    {
        "pr_id": "PR-003",
        "title": "Mua số lượng lớn Chip ESP32 cho dự án Smart Metering",
        "item_id": "COMP-ESP32-WROOM",
        "requested_qty": 1000,
        "target_delivery_date": "2026-12-15",
        "max_budget_vnd": 30000000.0,  # 30.000 VND / piece (Ngân sách thắt chặt phi thực tế -> Test bế tắc)
        "priority": "LOWEST_COST",
        "status": "PENDING",
    },
    {
        "pr_id": "PR-004",
        "title": "Mua màn hình OLED 0.96 inch cho máy đo quan trắc môi trường",
        "item_id": "COMP-OLED-096",
        "requested_qty": 300,
        "target_delivery_date": "2026-12-05",
        "max_budget_vnd": 15000000.0,  # 50.000 VND / piece (Đối mặt bài toán MOQ của nhà máy)
        "priority": "BALANCED",
        "status": "PENDING",
    },
]


# ───────────────────────────────────────────────────────────────────
# 4. Generator: 50 Historical Procurement Deals (RAG Benchmark)
# ───────────────────────────────────────────────────────────────────
OUTCOME_CHOICES = [
    "Ký kết thành công giá tốt nhờ thanh toán Net 15",
    "Thỏa thuận giảm giá 5% kèm cam kết khối lượng",
    "Đồng ý chia đôi chênh lệch giá, bảo hành 24 tháng",
    "Chấp nhận phụ phí giao nhanh 3%",
    "Đàm phán thất bại do vượt ngân sách trần",
    "Chốt hợp đồng khung giao 2 đợt đạt mức chiết khấu 10%",
    "Nhà cung cấp đồng ý miễn phí vận chuyển cho đơn trên 300 cái",
]

TERMS_CHOICES = ["Net 15", "Net 30", "Net 45", "Advance 30% Net 30", "Advance 50%"]

# Phân bổ danh mục mặt hàng chuẩn xác theo chuyên môn thực tế của từng đối tác
SUPPLIER_CATALOG_MAP = {
    "SUP-STMICRO": ["COMP-STM32F4", "COMP-OPTOCPL-817", "COMP-CAP-100UF"],
    "SUP-SENSIRION": ["COMP-TEMP-SENS"],
    "SUP-WINSTAR": ["COMP-OLED-096"],
    "SUP-DIGIKEY": [
        "COMP-STM32F4", "COMP-TEMP-SENS", "COMP-OLED-096", "COMP-ESP32-WROOM",
        "COMP-RELAY-5V", "COMP-BUCK-LM2596", "COMP-RTC-DS3231", "COMP-TRANS-4G",
        "COMP-CAP-100UF", "COMP-OPTOCPL-817",
    ],
    "SUP-MOUSER": [
        "COMP-STM32F4", "COMP-TEMP-SENS", "COMP-OLED-096", "COMP-ESP32-WROOM",
        "COMP-RELAY-5V", "COMP-BUCK-LM2596", "COMP-RTC-DS3231", "COMP-TRANS-4G",
        "COMP-CAP-100UF", "COMP-OPTOCPL-817",
    ],
}


def generate_historical_deals(num_records: int = 50) -> list[dict]:
    """Generate 50 realistic historical procurement contracts strictly matching supplier domains."""
    deals = []
    base_date = datetime.now() - timedelta(days=700)
    items_map = {item["item_id"]: item for item in INVENTORY_DATA}
    suppliers_map = {s["supplier_id"]: s for s in SUPPLIERS_DATA}

    # Đảm bảo mỗi mặt hàng có tối thiểu 5 hợp đồng lịch sử chuẩn ngành
    deal_idx = 1
    for item in INVENTORY_DATA:
        # Tìm các nhà cung cấp có mặt hàng này
        eligible_suppliers = [
            sid for sid, c_items in SUPPLIER_CATALOG_MAP.items()
            if item["item_id"] in c_items
        ]
        if not eligible_suppliers:
            eligible_suppliers = ["SUP-DIGIKEY", "SUP-MOUSER"]

        for _ in range(5):
            if deal_idx > num_records:
                break
            sup_id = random.choice(eligible_suppliers)
            supplier = suppliers_map[sup_id]

            variance = random.uniform(0.92, 1.12)
            unit_price = round(item["standard_cost_vnd"] * variance, -3)

            qty = random.choice([50, 100, 200, 300, 500])
            discount = round(random.uniform(2.0, 12.0), 1) if qty >= 200 else round(random.uniform(0.0, 4.0), 1)
            lead_time = max(2, supplier["standard_lead_time_days"] + random.choice([-1, 0, 1]))
            deal_date = (base_date + timedelta(days=random.randint(1, 680))).strftime("%Y-%m-%d")

            deals.append({
                "deal_id": deal_idx,
                "item_id": item["item_id"],
                "supplier_id": supplier["supplier_id"],
                "deal_date": deal_date,
                "quantity": qty,
                "unit_price_vnd": unit_price,
                "discount_pct": discount,
                "lead_time_days": lead_time,
                "payment_terms": random.choice(TERMS_CHOICES),
                "warranty_months": random.choice([12, 18, 24]),
                "deal_outcome": random.choice(OUTCOME_CHOICES),
                "notes": f"Đơn hàng mua sắm {item['item_name']} từ {supplier['supplier_name']}. Chiết khấu {discount}%, thời hạn giao {lead_time} ngày.",
            })
            deal_idx += 1

    return deals


# ───────────────────────────────────────────────────────────────────
# Main Seeding Function
# ───────────────────────────────────────────────────────────────────
def seed_all_data(drop_existing: bool = True) -> None:
    """Initialize schema and insert all seed data into SQLite database."""
    print("[Database] Initializing SQLite tables...")
    init_db(drop_existing=drop_existing)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Insert Inventory
    print(f"[Database] Inserting {len(INVENTORY_DATA)} inventory items...")
    cursor.executemany("""
        INSERT INTO inventory (item_id, item_name, category, unit, on_hand_qty, safety_stock_qty, standard_cost_vnd, description)
        VALUES (:item_id, :item_name, :category, :unit, :on_hand_qty, :safety_stock_qty, :standard_cost_vnd, :description)
    """, INVENTORY_DATA)

    # 2. Insert Suppliers
    print(f"[Database] Inserting {len(SUPPLIERS_DATA)} supplier profiles...")
    cursor.executemany("""
        INSERT INTO suppliers (supplier_id, supplier_name, tier, reliability_score, quality_rating, standard_lead_time_days, payment_terms_default, contact_email, persona_type, description)
        VALUES (:supplier_id, :supplier_name, :tier, :reliability_score, :quality_rating, :standard_lead_time_days, :payment_terms_default, :contact_email, :persona_type, :description)
    """, SUPPLIERS_DATA)

    # 3. Insert Purchase Requests (Test Use Cases)
    print(f"[Database] Inserting {len(PURCHASE_REQUESTS_DATA)} purchase requests (test use cases)...")
    cursor.executemany("""
        INSERT INTO purchase_requests (pr_id, title, item_id, requested_qty, target_delivery_date, max_budget_vnd, priority, status)
        VALUES (:pr_id, :title, :item_id, :requested_qty, :target_delivery_date, :max_budget_vnd, :priority, :status)
    """, PURCHASE_REQUESTS_DATA)

    # 4. Insert Historical Deals
    historical_deals = generate_historical_deals(num_records=50)
    print(f"[Database] Inserting {len(historical_deals)} historical deals for RAG benchmark...")
    cursor.executemany("""
        INSERT INTO historical_deals (deal_id, item_id, supplier_id, deal_date, quantity, unit_price_vnd, discount_pct, lead_time_days, payment_terms, warranty_months, deal_outcome, notes)
        VALUES (:deal_id, :item_id, :supplier_id, :deal_date, :quantity, :unit_price_vnd, :discount_pct, :lead_time_days, :payment_terms, :warranty_months, :deal_outcome, :notes)
    """, historical_deals)

    # 5. Insert Realistic Historical Negotiation Logs
    mock_logs = [
        # Session 1: STM32F4 with STMicroelectronics Authorized Distributor
        ("REQ-261118-STM32", "PR-001", "STMicroelectronics Authorized Distributor", 1, 142000.0, 7, "Net 15", "Đề xuất giá 142k căn cứ theo hợp đồng cũ và cam kết thanh toán Net 15.", 170000.0, 3, "Net 30", "Báo giá khởi điểm 170k, hàng chính hãng sẵn kho, bảo hành 24 tháng.", 16.5, "CONTINUE"),
        ("REQ-261118-STM32", "PR-001", "STMicroelectronics Authorized Distributor", 2, 149000.0, 5, "Net 15", "Nâng giá lên 149k, đề nghị bên bán hỗ trợ cho lô hàng 500 chiếc.", 163000.0, 3, "Net 30", "Hạ giá xuống 163k thể hiện thiện chí hợp tác lâu dài.", 8.6, "CONTINUE"),
        ("REQ-261118-STM32", "PR-001", "STMicroelectronics Authorized Distributor", 3, 154000.0, 5, "Net 15", "Đề xuất mức 154k, sẵn sàng đặt cọc trước 30%.", 158000.0, 3, "Net 15", "Giảm còn 158k với điều kiện thanh toán nhanh Net 15.", 2.5, "CONTINUE"),
        ("REQ-261118-STM32", "PR-001", "STMicroelectronics Authorized Distributor", 4, 156500.0, 3, "Net 15", "Thống nhất mức giá chốt 156.5k, giao hàng trong 3 ngày.", 156500.0, 3, "Net 15", "Đồng ý chốt đơn hàng ở mức 156.5k.", 0.0, "SUCCESS"),

        # Session 2: SHT31 with Sensirion Official Partner
        ("REQ-261118-SHT31", "PR-002", "Sensirion Official Partner (Sensirion AG)", 1, 170000.0, 2, "Net 15", "Cần cảm biến SHT31 khẩn cấp trong 2 ngày cứu chuyền sản xuất, đề xuất 170k.", 185000.0, 2, "Net 30", "Hàng Thụy Sĩ chính hãng, sẵn kho giao hỏa tốc trong 2 ngày, chào giá 185k.", 8.1, "CONTINUE"),
        ("REQ-261118-SHT31", "PR-002", "Sensirion Official Partner (Sensirion AG)", 2, 176000.0, 2, "Net 15", "Chấp nhận nhượng bộ lên 176k để ưu tiên giao hàng ngay trong 48h.", 180000.0, 2, "Net 15", "Đồng ý hỗ trợ khách hàng khẩn cấp, hạ giá xuống 180k.", 2.2, "CONTINUE"),
        ("REQ-261118-SHT31", "PR-002", "Sensirion Official Partner (Sensirion AG)", 3, 178500.0, 2, "Net 15", "Đạt thỏa thuận đơn giá 178.5k, giao hỏa tốc 48h.", 178500.0, 2, "Net 15", "Chốt đơn hàng thành công.", 0.0, "SUCCESS"),

        # Session 3: ESP32 with Digi-Key Electronics Asia
        ("REQ-261118-ESP32", "PR-003", "Digi-Key Electronics Asia (Global Distributor)", 1, 32000.0, 12, "Net 30", "Mua 1.000 module ESP32-WROOM, đề xuất mức giá ưu đãi 32k.", 38000.0, 12, "Net 30", "Giá chuẩn đại lý quốc tế 38k cho module chính hãng Espressif.", 15.8, "CONTINUE"),
        ("REQ-261118-ESP32", "PR-003", "Digi-Key Electronics Asia (Global Distributor)", 2, 34000.0, 12, "Net 30", "Tăng lên 34k theo định mức ngân sách linh kiện IoT.", 36000.0, 12, "Net 30", "Chiết khấu theo số lượng lớn xuống còn 36k.", 5.6, "CONTINUE"),
        ("REQ-261118-ESP32", "PR-003", "Digi-Key Electronics Asia (Global Distributor)", 3, 35000.0, 12, "Net 30", "Chia đôi chênh lệch tại mức 35k.", 35000.0, 12, "Net 30", "Đồng ý chốt hợp đồng tại 35k/chiếc.", 0.0, "SUCCESS"),

        # Session 4: OLED Display with Winstar Display Manufacturing Co.
        ("REQ-261118-OLED", "PR-004", "Winstar Display Manufacturing Co.", 1, 42000.0, 7, "Net 30", "Nhu cầu mua màn hình OLED 0.96 inch, đề xuất 42k.", 52000.0, 7, "Advance 50%", "Báo giá xuất xưởng 52k kèm chứng nhận QC công nghiệp.", 19.2, "CONTINUE"),
        ("REQ-261118-OLED", "PR-004", "Winstar Display Manufacturing Co.", 2, 45000.0, 7, "Net 30", "Đề xuất hợp đồng khung giao 2 đợt, nâng giá lên 45k.", 48000.0, 7, "Advance 30%", "Đồng ý phương án chia đợt, giảm giá chào về 48k.", 6.3, "CONTINUE"),
        ("REQ-261118-OLED", "PR-004", "Winstar Display Manufacturing Co.", 3, 47000.0, 7, "Net 30", "Thống nhất mức giá 47k.", 47000.0, 7, "Net 30", "Chốt hợp đồng thành công.", 0.0, "SUCCESS"),

        # Session 5: Relay Module with Mouser Electronics Vietnam
        ("REQ-261118-RELAY", "PR-005", "Mouser Electronics Vietnam", 1, 14000.0, 8, "Net 45", "Đề xuất 14k cho module Relay 5V cách ly quang.", 18000.0, 8, "Net 45", "Báo giá tiêu chuẩn 18k bảo hành 12 tháng.", 22.2, "CONTINUE"),
        ("REQ-261118-RELAY", "PR-005", "Mouser Electronics Vietnam", 2, 15500.0, 8, "Net 45", "Điều chỉnh tăng lên 15.5k.", 16500.0, 8, "Net 45", "Giảm xuống 16.5k để hỗ trợ bên mua.", 6.1, "CONTINUE"),
        ("REQ-261118-RELAY", "PR-005", "Mouser Electronics Vietnam", 3, 16000.0, 8, "Net 45", "Chốt thỏa thuận 16k.", 16000.0, 8, "Net 45", "Đồng ý chốt deal.", 0.0, "SUCCESS"),

        # Session 6: Gateway System with Digi-Key Electronics Asia (VNĐ)
        ("REQ-261118-GATEWAY", "PR-006", "Digi-Key Electronics Asia (Global Distributor)", 1, 350000.0, 10, "Net 15", "Đề xuất ngân sách 350.000 VNĐ cho module gateway công nghiệp.", 480000.0, 10, "Net 30", "Chào giá khởi điểm 480.000 VNĐ bao gồm gói dịch vụ hỗ trợ kỹ thuật.", 27.1, "CONTINUE"),
        ("REQ-261118-GATEWAY", "PR-006", "Digi-Key Electronics Asia (Global Distributor)", 2, 385000.0, 10, "Net 15", "Tăng giá chào mua lên 385.000 VNĐ và thanh toán sớm Net 15.", 440000.0, 10, "Net 15", "Giảm giá về 440.000 VNĐ.", 12.5, "CONTINUE"),
        ("REQ-261118-GATEWAY", "PR-006", "Digi-Key Electronics Asia (Global Distributor)", 3, 408000.0, 10, "Net 15", "Đề xuất nâng lên 408.000 VNĐ theo phê duyệt ngân sách.", 420000.0, 10, "Net 15", "Nhượng bộ xuống 420.000 VNĐ.", 2.9, "CONTINUE"),
        ("REQ-261118-GATEWAY", "PR-006", "Digi-Key Electronics Asia (Global Distributor)", 4, 415000.0, 10, "Net 15", "Hai bên thống nhất chốt hợp đồng tại 415.000 VNĐ.", 415000.0, 10, "Net 15", "Thỏa thuận thành công 415.000 VNĐ.", 0.0, "SUCCESS"),

        # Session 7: Gas Sensor with Sensirion Official Partner (VNĐ)
        ("REQ-261118-SENSOR", "PR-007", "Sensirion Official Partner (Sensirion AG)", 1, 120000.0, 3, "Net 15", "Đề xuất 120.000 VNĐ cho lô cảm biến khí chuyên dụng.", 155000.0, 3, "Net 30", "Chào giá 155.000 VNĐ kèm chứng chỉ kiểm định quốc tế.", 22.6, "CONTINUE"),
        ("REQ-261118-SENSOR", "PR-007", "Sensirion Official Partner (Sensirion AG)", 2, 132000.0, 3, "Net 15", "Nâng lên 132.000 VNĐ.", 140000.0, 3, "Net 15", "Hạ giá xuống 140.000 VNĐ.", 5.7, "CONTINUE"),
        ("REQ-261118-SENSOR", "PR-007", "Sensirion Official Partner (Sensirion AG)", 3, 136500.0, 3, "Net 15", "Chốt thỏa thuận đơn hàng tại 136.500 VNĐ.", 136500.0, 3, "Net 15", "Đồng ý chốt deal 136.500 VNĐ.", 0.0, "SUCCESS"),

        # Session 8: Automotive Chip - Deadlock / Intervention Session
        ("REQ-261118-DEADLOCK", "PR-008", "STMicroelectronics Authorized Distributor", 1, 30000.0, 7, "Net 15", "Trần ngân sách bên mua 30k.", 45000.0, 7, "Net 30", "Giá sàn bên bán tối thiểu 42k không thể giảm hơn.", 33.3, "CONTINUE"),
        ("REQ-261118-DEADLOCK", "PR-008", "STMicroelectronics Authorized Distributor", 2, 32000.0, 7, "Net 15", "Chỉ có thể nhượng bộ tối đa 32k.", 42000.0, 7, "Net 30", "Giữ nguyên giá sàn 42k.", 23.8, "PAUSED"),
    ]

    print(f"[Database] Inserting {len(mock_logs)} negotiation log records for realistic platform analytics...")
    cursor.executemany("""
        INSERT INTO negotiation_logs (
            session_id, pr_id, supplier_id, round_number,
            buyer_offer_price, buyer_lead_time_days, buyer_terms, buyer_reasoning,
            supplier_offer_price, supplier_lead_time_days, supplier_terms, supplier_reasoning,
            gap_pct, mediator_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, mock_logs)

    conn.commit()
    conn.close()
    print("[Database] Successfully seeded all enterprise procurement data into procurement.db!")


if __name__ == "__main__":
    seed_all_data()

