"""
Multi-Agent Procurement & Negotiation System.

Core Architecture:
1. Core 3-Agent Negotiation Loop: Buyer Agent ⇄ Seller Agent ⇄ Mediator Agent.
2. Advanced Human Override Controls (6 modes: approve, reject, modify_buyer, modify_seller, inject, terminate).
3. Session Lookup & Replay: Lookup and replay complete historical negotiations by session_id from SQLite.
4. Platform Analytics Dashboard: Aggregated performance metrics (Success Rate, Avg. Rounds, Concessions, Price Gap) when idle.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import plotly.graph_objects as go
import streamlit as st
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.graph.state import NegotiationState
from app.graph.workflow import build_negotiation_graph
import app.data.database as db

# ───────────────────────────────────────────────────────────────────
# Page Configuration
# ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Multi-Agent Procurement & Negotiation System",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-title {
        font-size: 1.85rem;
        font-weight: 700;
        color: #0F172A;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 0.95rem;
        color: #475569;
        margin-bottom: 1.2rem;
    }
    .chat-bubble-buyer {
        background-color: #EFF6FF;
        border-left: 4px solid #2563EB;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 10px;
        font-size: 0.93rem;
    }
    .chat-bubble-supplier {
        background-color: #F0FDF4;
        border-left: 4px solid #16A34A;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 10px;
        font-size: 0.93rem;
    }
    .intervention-box {
        background-color: #FFFBEB;
        border: 2px solid #F59E0B;
        border-radius: 10px;
        padding: 16px 20px;
        margin-top: 15px;
        margin-bottom: 15px;
    }
    .metric-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 14px 18px;
        text-align: center;
    }
    .metric-num {
        font-size: 1.6rem;
        font-weight: 700;
        color: #0F172A;
        margin-top: 4px;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ───────────────────────────────────────────────────────────────────
# Session State Initialization
# ───────────────────────────────────────────────────────────────────
if "checkpointer" not in st.session_state:
    st.session_state["checkpointer"] = MemorySaver()
    st.session_state["nego_graph"] = build_negotiation_graph(st.session_state["checkpointer"])

if "graph_result" not in st.session_state:
    st.session_state["graph_result"] = None

if "replayed_session_id" not in st.session_state:
    st.session_state["replayed_session_id"] = None


# ───────────────────────────────────────────────────────────────────
# SIDEBAR: Cấu Hình Thông Số & Tra Cứu Lịch Sử (Session Lookup)
# ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### CẤU HÌNH THƯƠNG THẢO")
    st.caption("Thiết lập phiên đàm phán trực tiếp giữa Buyer và Seller.")

    # 1. Tra cứu phiên cũ (Session Lookup & Replay)
    st.markdown("---")
    st.markdown("#### Tra cứu & Xem lại phiên (Session Lookup):")
    recent_sessions = db.get_all_negotiation_sessions()
    session_options = ["-- Chọn phiên lịch sử --"] + [
        f"{s['session_id']} | {s['supplier_id'][:20]} ({s['total_rounds']} vòng - {s['final_status']})"
        for s in recent_sessions
    ]
    selected_lookup = st.selectbox("Chọn mã phiên từ hệ thống:", options=session_options, index=0)
    custom_lookup = st.text_input("Hoặc nhập chính xác session_id:", value="", placeholder="Ví dụ: REQ-2611180629")

    target_sid = None
    if custom_lookup.strip():
        target_sid = custom_lookup.strip()
    elif selected_lookup and not selected_lookup.startswith("--"):
        target_sid = selected_lookup.split(" | ")[0].strip()

    c_load, c_clear = st.columns(2)
    with c_load:
        if st.button("Tải lại phiên", use_container_width=True, disabled=not bool(target_sid)):
            st.session_state["replayed_session_id"] = target_sid
            st.session_state["graph_result"] = None
            st.rerun()

    with c_clear:
        if st.button("Về Dashboard", use_container_width=True):
            st.session_state["replayed_session_id"] = None
            st.session_state["graph_result"] = None
            st.rerun()

    # 2. Thiết lập phiên đàm phán mới
    st.markdown("---")
    st.markdown("#### Thiết lập phiên mới:")
    currency = "VNĐ"
    curr_sym = "VNĐ"

    # Danh mục mặt hàng mẫu
    item_presets = [
        "Vi điều khiển ARM Cortex-M4 STM32F407VGT6",
        "Cảm biến nhiệt độ và độ ẩm kỹ thuật số SHT31",
        "Màn hình hiển thị OLED 0.96 inch I2C 128x64",
        "Mô-đun thu phát Wi-Fi/Bluetooth ESP32-WROOM-32E",
        "IC quản lý nguồn PMIC TPS65217C",
        "Tự nhập mặt hàng khác...",
    ]
    def _sync_item_preset():
        chosen_item = st.session_state.get("sb_item_preset")
        if chosen_item and chosen_item != "Tự nhập mặt hàng khác...":
            st.session_state["sb_item_name"] = chosen_item

    if "sb_item_name" not in st.session_state:
        st.session_state["sb_item_name"] = item_presets[0]

    st.selectbox("Chọn nhanh mặt hàng mẫu:", options=item_presets, index=0, key="sb_item_preset", on_change=_sync_item_preset)
    form_item_name = st.text_input("Mặt hàng cần mua:", key="sb_item_name")
    form_qty = st.number_input("Số lượng đặt mua:", min_value=1, value=500, step=10, key="sb_qty")

    st.markdown("**Bên mua (Buyer):**")
    form_buyer_ceiling = st.number_input(
        f"Trần ngân sách (Trần tối đa - {curr_sym}):",
        min_value=1.0,
        value=160_000.0,
        step=5_000.0,
        key="sb_b_ceil",
    )
    form_buyer_target = st.number_input(
        f"Mức giá kỳ vọng mua ({curr_sym}):",
        min_value=1.0,
        value=142_000.0,
        step=5_000.0,
        key="sb_b_tgt",
    )
    priority_mode = st.selectbox(
        "Mục tiêu / Ưu tiên đàm phán:",
        options=[
            "Tiêu chuẩn (Cân bằng Giá & Chất lượng)",
            "Cần hàng khẩn cấp (Hỏa tốc 2-3 ngày, cứu dây chuyền)",
        ],
        index=0,
        key="sb_priority_mode",
    )

    st.markdown("**Bên bán (Seller):**")
    partner_presets = [
        "STMicroelectronics Authorized Distributor",
        "Sensirion Official Partner (Sensirion AG)",
        "Digi-Key Electronics Asia (Global Distributor)",
        "Winstar Display Manufacturing Co.",
        "Mouser Electronics Vietnam",
        "Tự nhập đối tác khác...",
    ]
    def _sync_seller_preset():
        chosen_partner = st.session_state.get("sb_partner_preset")
        if chosen_partner and chosen_partner != "Tự nhập đối tác khác...":
            st.session_state["sb_seller_name"] = chosen_partner
        elif chosen_partner == "Tự nhập đối tác khác...":
            st.session_state["sb_seller_name"] = "Công ty TNHH Linh Kiện Toàn Cầu"

    if "sb_seller_name" not in st.session_state:
        st.session_state["sb_seller_name"] = partner_presets[0]

    sel_preset = st.selectbox(
        "Chọn nhanh đối tác:",
        options=partner_presets,
        index=0,
        key="sb_partner_preset",
        on_change=_sync_seller_preset,
    )
    form_seller_name = st.text_input("Tên đối tác / Nhà cung cấp:", key="sb_seller_name")

    # Kiểm tra năng lực đối tác đối với mặt hàng
    compat_info = db.check_supplier_item_compatibility(form_item_name, form_seller_name)
    if compat_info["is_compatible"]:
        st.success(f"**{compat_info['status_title']}**: {compat_info['message']}")
    else:
        st.warning(f"**{compat_info['status_title']}**: {compat_info['message']}")
    form_seller_target = st.number_input(
        f"Giá chào ban đầu của bên bán ({curr_sym}):",
        min_value=1.0,
        value=170_000.0,
        step=5_000.0,
        key="sb_s_tgt",
    )
    form_seller_floor = st.number_input(
        f"Giá sàn (Mức thấp nhất có thể bán - {curr_sym}):",
        min_value=1.0,
        value=150_000.0,
        step=5_000.0,
        key="sb_s_floor",
    )
    form_seller_cost = st.number_input(
        f"Giá vốn ước tính ({curr_sym}):",
        min_value=1.0,
        value=135_000.0,
        step=5_000.0,
        key="sb_s_cost",
    )
    form_max_rounds = st.slider("Số vòng trao đổi tối đa:", min_value=3, max_value=15, value=10, key="sb_max_rounds")

    st.markdown("---")
    start_btn = st.button("Bắt đầu thương thảo", type="primary", use_container_width=True)


# ───────────────────────────────────────────────────────────────────
# Header Chính
# ───────────────────────────────────────────────────────────────────
st.markdown('<div class="main-title">Multi-Agent Procurement & Negotiation System</div>', unsafe_allow_html=True)


# ───────────────────────────────────────────────────────────────────
# XỬ LÝ KHỞI TẠO PHIÊN MỚI
# ───────────────────────────────────────────────────────────────────
if start_btn:
    session_id = f"REQ-{datetime.now().strftime('%y%m%d%H%M%S')}"
    thread_id = f"nego-thread-{session_id}"
    st.session_state["thread_id"] = thread_id
    st.session_state["replayed_session_id"] = None
    config = {"configurable": {"thread_id": thread_id}}

    init_state: NegotiationState = {
        "session_id": session_id,
        "product_name": form_item_name,
        "quantity": int(form_qty),
        "budget_ceiling": float(form_buyer_ceiling),
        "target_price": float(form_buyer_target),
        "min_price": float(form_seller_floor),
        "seller_target": float(form_seller_target),
        "cost_basis": float(form_seller_cost),
        "supplier_name": form_seller_name,
        "currency": curr_sym,
        "max_rounds": int(form_max_rounds),
        "current_round": 1,
        "status": "ACTIVE",
        "history": [],
        "injected_instruction": (
            "Cần hàng khẩn cấp cứu dây chuyền sản xuất: Ưu tiên cam kết giao hàng hỏa tốc trong 2-3 ngày, sẵn sàng điều chỉnh giá linh hoạt."
            if "khẩn cấp" in str(priority_mode).lower()
            else None
        ),
    }

    with st.spinner("Đang khởi tạo các Agent và bắt đầu phiên thương thảo..."):
        graph = st.session_state["nego_graph"]
        res = graph.invoke(init_state, config=config)
        st.session_state["graph_result"] = res
    st.rerun()


# ───────────────────────────────────────────────────────────────────
# CHẾ ĐỘ 1: XEM LẠI LỊCH SỬ PHIÊN (Session Lookup & Replay)
# ───────────────────────────────────────────────────────────────────
if st.session_state.get("replayed_session_id"):
    replayed_sid = st.session_state["replayed_session_id"]
    transcript = db.get_session_transcript(replayed_sid)

    c_back, c_tit = st.columns([0.2, 0.8])
    with c_back:
        if st.button("Quay lại Dashboard"):
            st.session_state["replayed_session_id"] = None
            st.rerun()
    with c_tit:
        st.subheader(f"Xem Lại Lịch Sử Phiên: {replayed_sid}")

    if not transcript:
        st.warning(f"Không tìm thấy dữ liệu đối thoại cho phiên: {replayed_sid}")
    else:
        last_r = transcript[-1]
        first_r = transcript[0]
        final_status = last_r.get("mediator_status", "UNKNOWN")
        total_r = len(transcript)

        # Metric tóm tắt
        m1, m2, m3, m4 = st.columns(4)
        m1.markdown(f'<div class="metric-card"><div class="metric-label">Số vòng đàm phán</div><div class="metric-num">{total_r}</div></div>', unsafe_allow_html=True)
        m2.markdown(f'<div class="metric-card"><div class="metric-label">Chênh lệch giá cuối</div><div class="metric-num">{last_r.get("gap_pct", 0):.1f}%</div></div>', unsafe_allow_html=True)
        m3.markdown(f'<div class="metric-card"><div class="metric-label">Đối tác bên bán</div><div class="metric-num" style="font-size:1.15rem;">{last_r.get("supplier_id", "Supplier")}</div></div>', unsafe_allow_html=True)
        m4.markdown(f'<div class="metric-card"><div class="metric-label">Trạng thái kết thúc</div><div class="metric-num" style="font-size:1.15rem; color: #16A34A;">{final_status}</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Biểu đồ diễn biến giá qua các vòng
        rounds = [r["round_number"] for r in transcript]
        b_bids = [r["buyer_offer_price"] for r in transcript]
        s_asks = [r["supplier_offer_price"] for r in transcript]

        fig_replay = go.Figure()
        fig_replay.add_trace(go.Scatter(x=rounds, y=b_bids, mode='lines+markers', name='Buyer Offer', line=dict(color='#2563EB', width=3)))
        fig_replay.add_trace(go.Scatter(x=rounds, y=s_asks, mode='lines+markers', name='Seller Ask', line=dict(color='#16A34A', width=3)))
        fig_replay.update_layout(
            title=f"Biểu đồ diễn biến thương thảo qua {total_r} vòng ({replayed_sid})",
            xaxis=dict(title="Vòng đàm phán", tickmode='linear', dtick=1),
            yaxis=dict(title="Mức giá"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=40, t=60, b=40),
            height=340,
        )
        st.plotly_chart(fig_replay, use_container_width=True)

        # Hiển thị Đơn đặt hàng (Purchase Order) nếu phiên đạt thỏa thuận thành công
        if final_status in ("SUCCESS", "APPROVED", "COMPLETED") or last_r.get("gap_pct", 100) <= 2.0:
            conn = db.get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM purchase_requests WHERE pr_id = ? OR pr_id = ?", (replayed_sid, last_r.get("pr_id", "")))
            pr_row = c.fetchone()
            conn.close()

            item_title = pr_row["title"] if pr_row else "Linh kiện thiết bị công nghiệp"
            qty = int(pr_row["requested_qty"]) if pr_row else 500
            max_budget = float(pr_row["max_budget_vnd"]) if pr_row else (last_r["supplier_offer_price"] * 1.1 * qty)

            agreed_unit = round((last_r["buyer_offer_price"] + last_r["supplier_offer_price"]) / 2, -3)
            total_amt = agreed_unit * qty
            savings = max(0.0, max_budget - total_amt)
            po_num = f"PO-{replayed_sid.replace('REQ-', '').replace('PR-', '').replace('SESSION-', '')}"

            st.markdown(
                f"""
                <div style="background-color: #F8FAFC; border: 2px solid #22C55E; border-radius: 8px; padding: 20px; margin-bottom: 24px;">
                    <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #E2E8F0; padding-bottom: 12px;">
                        <div>
                            <span style="font-size: 1.25rem; font-weight: 700; color: #0F172A;">ĐƠN ĐẶT HÀNG: {po_num}</span><br>
                            <span style="font-size: 0.9rem; color: #64748B;">Hợp đồng mua sắm điện tử (Lưu trữ từ phiên {replayed_sid})</span>
                        </div>
                        <div style="text-align: right;">
                            <span style="font-size: 0.9rem; color: #475569;">Điều khoản: Net 15</span><br>
                            <span style="display: inline-block; background-color: #16A34A; color: white; padding: 3px 12px; border-radius: 12px; font-size: 0.82rem; font-weight: 700; margin-top: 4px;">ĐÃ PHÊ DUYỆT (SUCCESS)</span>
                        </div>
                    </div>
                    <div style="margin-top: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 24px;">
                        <div>
                            <p style="margin: 5px 0;"><b>Nhà cung cấp:</b> {last_r.get('supplier_id', 'Đối tác')}</p>
                            <p style="margin: 5px 0;"><b>Mặt hàng:</b> {item_title}</p>
                            <p style="margin: 5px 0;"><b>Số lượng:</b> {qty:,} chiếc</p>
                        </div>
                        <div>
                            <p style="margin: 5px 0;"><b>Đơn giá thống nhất:</b> {agreed_unit:,.0f} VNĐ/chiếc</p>
                            <p style="margin: 5px 0;"><b>Tổng giá trị đơn hàng:</b> <span style="font-size: 1.25rem; color: #0F172A; font-weight: 800;">{total_amt:,.0f} VNĐ</span></p>
                            <p style="margin: 5px 0;"><b>Tiết kiệm so với trần ngân sách:</b> <span style="color: #16A34A; font-weight: 700;">+{savings:,.0f} VNĐ</span></p>
                        </div>
                    </div>
                    <div style="margin-top: 16px; background-color: #EFF6FF; padding: 12px; border-radius: 6px; border: 1px solid #BFDBFE;">
                        <p style="margin: 3px 0; font-size: 0.92rem;"><b>Ghi chú:</b> Đạt thỏa thuận thành công tại Vòng {total_r} với chênh lệch {last_r.get('gap_pct', 0):.2f}%.</p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Chi tiết biên bản đối thoại từng vòng
        st.markdown("#### Chi tiết diễn biến từng vòng:")
        for r_item in reversed(transcript):
            r_num = r_item["round_number"]
            gap_pct = r_item.get("gap_pct", 0)
            is_latest = (r_num == total_r)

            with st.expander(f"Vòng {r_num} (Chênh lệch: {gap_pct:.1f}% - Trạng thái: {r_item.get('mediator_status', 'CONTINUE')})", expanded=is_latest):
                st.markdown(
                    f'<div class="chat-bubble-buyer">'
                    f'<b>Đại diện bên mua (Buyer Agent):</b> Đề xuất <b>{r_item["buyer_offer_price"]:,.0f}</b> | Điều khoản: {r_item.get("buyer_terms", "Net 15")}<br>'
                    f'<i>"{r_item.get("buyer_reasoning", "Đề xuất mức giá hợp lý.")}"</i>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="chat-bubble-supplier">'
                    f'<b>Đại diện bên bán ({r_item.get("supplier_id", "Seller Agent")}):</b> Chào giá <b>{r_item["supplier_offer_price"]:,.0f}</b> | Giao hàng: {r_item.get("supplier_lead_time_days", 7)} ngày<br>'
                    f'<i>"{r_item.get("supplier_reasoning", "Báo giá tiêu chuẩn.")}"</i>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


# ───────────────────────────────────────────────────────────────────
# CHẾ ĐỘ 2: PHIÊN ĐANG CHẠY / VỪA CHẠY XONG (Live Negotiation Arena)
# ───────────────────────────────────────────────────────────────────
elif st.session_state.get("graph_result"):
    res = st.session_state["graph_result"]
    thread_id = st.session_state.get("thread_id", "default-thread")
    history = res.get("history", [])
    status = res.get("status", "ACTIVE")
    curr_round = len(history) or res.get("current_round", 1)
    max_r = res.get("max_rounds", form_max_rounds)
    curr_sym = res.get("currency", currency)

    is_interrupted = bool(res.get("__interrupt__"))
    if is_interrupted:
        status = "PAUSED"

    # Header tóm tắt phiên
    col_hdr, col_btn = st.columns([0.8, 0.2])
    with col_hdr:
        st.markdown(f"**Mã phiên:** `{res.get('session_id', thread_id)}` | **Mặt hàng:** {res.get('product_name', form_item_name)} | **Đối tác:** {res.get('supplier_name', form_seller_name)}")
    with col_btn:
        if st.button("Kết thúc / Về Dashboard", use_container_width=True):
            st.session_state["graph_result"] = None
            st.rerun()

    # 4 Metric Cards
    latest_buyer = history[-1]["buyer_bid"] if history else res.get("target_price", form_buyer_target)
    latest_seller = history[-1]["seller_ask"] if history else res.get("seller_target", form_seller_target)
    current_gap_pct = history[-1].get("price_gap_pct", 0) if history else 100.0

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f'<div class="metric-card"><div class="metric-label">Vòng đàm phán</div><div class="metric-num">{curr_round} / {max_r}</div></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="metric-card"><div class="metric-label">Chênh lệch giá</div><div class="metric-num">{current_gap_pct:.1f}%</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="metric-card"><div class="metric-label">Giá mua đề xuất (Buyer)</div><div class="metric-num">{latest_buyer:,.0f} {curr_sym}</div></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="metric-card"><div class="metric-label">Giá chào bên bán (Seller)</div><div class="metric-num">{latest_seller:,.0f} {curr_sym}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Dữ liệu đối chiếu thị trường (RAG) & Năng lực đối tác
    rag_items = res.get("rag_benchmarks", [])
    compat_arena = db.check_supplier_item_compatibility(res.get("product_name", form_item_name), res.get("supplier_name", form_seller_name))

    with st.expander("Dữ liệu đối chiếu thị trường (RAG Grounding) & Năng lực cung ứng đối tác", expanded=False):
        c_rag1, c_rag2 = st.columns([0.45, 0.55])
        with c_rag1:
            st.markdown(f"**Năng lực cung ứng:** <span style='color:{compat_arena['badge_color']}; font-weight:700;'>{compat_arena['status_title']}</span>", unsafe_allow_html=True)
            st.caption(compat_arena['message'])
        with c_rag2:
            st.markdown("**Căn cứ giá quá khứ (RAG Grounding):**")
            for b in rag_items:
                st.write(b)

    # Biểu đồ diễn tiến giá
    if history:
        rounds = [h["round"] for h in history]
        bids = [h["buyer_bid"] for h in history]
        asks = [h["seller_ask"] for h in history]

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=rounds, y=bids, mode='lines+markers', name='Buyer Offer', line=dict(color='#2563EB', width=3)))
        fig.add_trace(go.Scatter(x=rounds, y=asks, mode='lines+markers', name='Seller Ask', line=dict(color='#16A34A', width=3)))
        fig.add_hline(y=float(res.get("budget_ceiling", form_buyer_ceiling)), line_dash="dash", line_color="#DC2626", annotation_text="Trần ngân sách")
        fig.add_hline(y=float(res.get("min_price", form_seller_floor)), line_dash="dash", line_color="#D97706", annotation_text="Giá sàn đối tác")

        fig.update_layout(
            title="Biểu đồ thu hẹp khoảng cách giá giữa Buyer và Seller",
            xaxis=dict(title="Vòng đàm phán", tickmode='linear', dtick=1),
            yaxis=dict(title=f"Mức giá ({curr_sym})"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=40, t=60, b=40),
            height=340,
        )
        st.plotly_chart(fig, use_container_width=True)

    # ─────────────────────────────────────────────────────────────
    # NÂNG CAO: 6 CHẾ ĐỘ CAN THIỆP CỦA CON NGƯỜI (HUMAN OVERRIDE CONTROLS)
    # ─────────────────────────────────────────────────────────────
    if is_interrupted or status == "PAUSED":
        st.markdown(
            """
            <div class="intervention-box">
                <h3 style="margin-top:0; color:#92400E;">CƠ CHẾ CAN THIỆP CỦA CON NGƯỜI (HUMAN OVERRIDE CONTROLS)</h3>
                <p style="color:#78350F; font-size:0.95rem; margin-bottom: 0;">
                    Cuộc đàm phán đang tạm dừng (PAUSED). Bạn có 6 chế độ can thiệp trực tiếp vào hành vi của các Agent:
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        agree_price = round((latest_buyer + latest_seller) / 2, 0)
        col_act1, col_act2, col_act3 = st.columns(3)

        # Chế độ 1: approve
        with col_act1:
            st.markdown("##### 1. Chấp thuận (Approve)")
            st.caption(f"Đồng ý chốt thỏa thuận ở mức trung bình {agree_price:,.0f} {curr_sym} và kết thúc phiên.")
            if st.button(f"Approve chốt giá {agree_price:,.0f} {curr_sym}", type="primary", use_container_width=True):
                graph = st.session_state["nego_graph"]
                config = {"configurable": {"thread_id": thread_id}}
                updated_res = graph.invoke(Command(resume={"action": "approve"}), config=config)
                st.session_state["graph_result"] = updated_res
                st.success("Đã phê duyệt chốt hợp đồng thành công!")
                st.rerun()

        # Chế độ 2: reject
        with col_act2:
            st.markdown("##### 2. Bác bỏ (Reject)")
            st.caption("Bác bỏ đề xuất vòng vừa rồi và yêu cầu hai bên AI thương lượng lại mức giá khác.")
            if st.button("Reject đề xuất vòng này", use_container_width=True):
                graph = st.session_state["nego_graph"]
                config = {"configurable": {"thread_id": thread_id}}
                updated_res = graph.invoke(Command(resume={"action": "reject"}), config=config)
                st.session_state["graph_result"] = updated_res
                st.info("Đã bác bỏ đề xuất và yêu cầu hai bên tiếp tục trả giá mới!")
                st.rerun()

        # Chế độ 6: terminate
        with col_act3:
            st.markdown("##### 6. Hủy bỏ (Terminate)")
            st.caption("Cưỡng chế hủy bỏ và chấm dứt phiên thương thảo này ngay lập tức.")
            if st.button("Terminate phiên đàm phán", use_container_width=True):
                graph = st.session_state["nego_graph"]
                config = {"configurable": {"thread_id": thread_id}}
                updated_res = graph.invoke(Command(resume={"action": "terminate"}), config=config)
                st.session_state["graph_result"] = updated_res
                st.error("Phiên đàm phán đã bị hủy theo quyết định của Quản lý.")
                st.rerun()

        st.markdown("---")
        col_mod_b, col_mod_s, col_inj = st.columns(3)

        # Chế độ 3: modify_buyer
        with col_mod_b:
            st.markdown("##### 3. Điều chỉnh Bên mua (Modify Buyer)")
            new_b_ceil = st.number_input("Trần ngân sách mới:", value=float(res.get("budget_ceiling", form_buyer_ceiling)), key="ovr_b_ceil")
            new_b_tgt = st.number_input("Giá mục tiêu bên mua mới:", value=float(res.get("target_price", form_buyer_target)), key="ovr_b_tgt")
            if st.button("Áp dụng thông số Bên mua", use_container_width=True):
                graph = st.session_state["nego_graph"]
                config = {"configurable": {"thread_id": thread_id}}
                payload = {
                    "action": "modify_buyer",
                    "new_budget_ceiling": float(new_b_ceil),
                    "new_buyer_target": float(new_b_tgt),
                }
                updated_res = graph.invoke(Command(resume=payload), config=config)
                st.session_state["graph_result"] = updated_res
                st.success("Đã cập nhật ngân sách bên mua!")
                st.rerun()

        # Chế độ 4: modify_seller
        with col_mod_s:
            st.markdown("##### 4. Điều chỉnh Bên bán (Modify Seller)")
            new_s_floor = st.number_input("Giá sàn bên bán mới:", value=float(res.get("min_price", form_seller_floor)), key="ovr_s_floor")
            new_s_cost = st.number_input("Giá vốn bên bán mới:", value=float(res.get("cost_basis", form_seller_cost)), key="ovr_s_cost")
            if st.button("Áp dụng thông số Bên bán", use_container_width=True):
                graph = st.session_state["nego_graph"]
                config = {"configurable": {"thread_id": thread_id}}
                payload = {
                    "action": "modify_seller",
                    "new_min_price": float(new_s_floor),
                    "new_seller_cost": float(new_s_cost),
                }
                updated_res = graph.invoke(Command(resume=payload), config=config)
                st.session_state["graph_result"] = updated_res
                st.success("Đã cập nhật giới hạn bên bán!")
                st.rerun()

        # Chế độ 5: inject (Prompt Injection)
        with col_inj:
            st.markdown("##### 5. Gửi chỉ đạo tự do (Prompt Injection)")
            injected_guidance = st.text_area(
                "Chỉ đạo văn bản gửi thẳng cho Agent:",
                placeholder="Ví dụ: Bảo bên bán nếu chịu bảo hành 2 năm thì mình nâng giá lên 156.000 VNĐ...",
                key="ovr_inject_text",
            )
            if st.button("Gửi chỉ thị (Inject)", type="primary", use_container_width=True):
                if injected_guidance.strip():
                    graph = st.session_state["nego_graph"]
                    config = {"configurable": {"thread_id": thread_id}}
                    payload = {
                        "action": "inject",
                        "injected_guidance": injected_guidance.strip(),
                    }
                    updated_res = graph.invoke(Command(resume=payload), config=config)
                    st.session_state["graph_result"] = updated_res
                    st.success("Đã chuyển chỉ đạo vào Agent!")
                    st.rerun()
                else:
                    st.warning("Vui lòng nhập nội dung chỉ đạo trước khi bấm gửi.")

        st.markdown("---")

    # Hiển thị Đơn đặt hàng (Purchase Order) nếu đã thành công
    po = res.get("purchase_order")
    if po:
        savings = max(0.0, float(res.get("budget_ceiling", form_buyer_ceiling)) - float(po["agreed_unit_price"])) * int(po["quantity"])
        st.markdown(
            f"""
            <div style="background-color: #F8FAFC; border: 2px solid #22C55E; border-radius: 8px; padding: 20px; margin-bottom: 24px;">
                <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #E2E8F0; padding-bottom: 12px;">
                    <div>
                        <span style="font-size: 1.25rem; font-weight: 700; color: #0F172A;">ĐƠN ĐẶT HÀNG: {po['po_number']}</span><br>
                        <span style="font-size: 0.9rem; color: #64748B;">Hợp đồng mua sắm điện tử được lập tự động</span>
                    </div>
                    <div style="text-align: right;">
                        <span style="font-size: 0.9rem; color: #475569;">Ngày tạo: {po['created_at']}</span><br>
                        <span style="display: inline-block; background-color: #16A34A; color: white; padding: 3px 12px; border-radius: 12px; font-size: 0.82rem; font-weight: 700; margin-top: 4px;">ĐÃ PHÊ DUYỆT</span>
                    </div>
                </div>
                <div style="margin-top: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 24px;">
                    <div>
                        <p style="margin: 5px 0;"><b>Nhà cung cấp:</b> {po['supplier_name']}</p>
                        <p style="margin: 5px 0;"><b>Mặt hàng:</b> {po['item_name']}</p>
                        <p style="margin: 5px 0;"><b>Số lượng:</b> {po['quantity']:,} chiếc</p>
                    </div>
                    <div>
                        <p style="margin: 5px 0;"><b>Đơn giá thống nhất:</b> {po['agreed_unit_price']:,.0f} {po['currency']}/chiếc</p>
                        <p style="margin: 5px 0;"><b>Tổng giá trị đơn hàng:</b> <span style="font-size: 1.25rem; color: #0F172A; font-weight: 800;">{po['total_amount']:,.0f} {po['currency']}</span></p>
                        <p style="margin: 5px 0;"><b>Tiết kiệm so với trần ngân sách:</b> <span style="color: #16A34A; font-weight: 700;">+{savings:,.0f} {po['currency']}</span></p>
                    </div>
                </div>
                <div style="margin-top: 16px; background-color: #EFF6FF; padding: 12px; border-radius: 6px; border: 1px solid #BFDBFE;">
                    <p style="margin: 3px 0; font-size: 0.92rem;"><b>Ghi chú:</b> {po.get('approval_note', 'Thỏa thuận đạt tiêu chuẩn.')}</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Biên bản đối thoại chi tiết từng vòng
    st.markdown("#### Nội dung trao đổi chi tiết từng vòng:")

    # Cảnh báo minh bạch nếu có vòng nào dùng Heuristic do chạm hạn ngạch API
    has_api_warning = any(r_item.get("api_warning") for r_item in history)
    if has_api_warning:
        st.warning(
            "**THÔNG BÁO HẠN NGẠCH API:** Mô hình LLM đã chạm hạn ngạch gọi API (Rate limit 429). "
            "Các vòng có nhãn **[Heuristic]** đang tạm thời kích hoạt thuật toán toán học nhượng bộ có kiểm soát "
            "để phiên đàm phán không bị gián đoạn, hoàn toàn minh bạch và không bịa đặt dữ liệu ảo."
        )

    for r_item in reversed(history):
        r_num = r_item["round"]
        gap_pct = r_item.get("price_gap_pct", 0)
        is_latest = (r_num == curr_round)

        b_engine = r_item.get("buyer_engine", "LLM")
        s_engine = r_item.get("seller_engine", "LLM")
        b_badge = "AI LLM" if "LLM" in b_engine else "Heuristic (Hết API)"
        s_badge = "AI LLM" if "LLM" in s_engine else "Heuristic (Hết API)"
        b_color = "#E0F2FE; color:#0369A1" if "LLM" in b_engine else "#FEF3C7; color:#B45309"
        s_color = "#DCFCE7; color:#15803D" if "LLM" in s_engine else "#FEF3C7; color:#B45309"

        with st.expander(f"Vòng trao đổi {r_num} (Chênh lệch: {gap_pct:.1f}%)", expanded=is_latest):
            st.markdown(
                f'<div class="chat-bubble-buyer">'
                f'<b>Đại diện bên mua</b> <span style="font-size:0.75rem; background:{b_color}; padding:1px 6px; border-radius:4px; font-weight:600;">{b_badge}</span>: Đề xuất <b>{r_item["buyer_bid"]:,.0f} {curr_sym}</b><br>'
                f'<i>"{r_item["buyer_reasoning"]}"</i>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="chat-bubble-supplier">'
                f'<b>Đại diện bên bán ({res.get("supplier_name", "Đối tác")})</b> <span style="font-size:0.75rem; background:{s_color}; padding:1px 6px; border-radius:4px; font-weight:600;">{s_badge}</span>: Chào giá <b>{r_item["seller_ask"]:,.0f} {curr_sym}</b><br>'
                f'<i>"{r_item["seller_reasoning"]}"</i>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if r_item.get("api_warning"):
                st.caption(f"Lưu ý trạng thái: {r_item['api_warning']}")
            st.caption(f"{r_item.get('summary', '')}")


# ───────────────────────────────────────────────────────────────────
# CHẾ ĐỘ 3: MÀN HÌNH CHÍNH — PLATFORM ANALYTICS DASHBOARD (KHI RẢNH)
# ───────────────────────────────────────────────────────────────────
else:
    st.markdown('<div class="sub-title">Bảng phân tích hiệu suất tổng thể hệ thống đàm phán tự động (Platform Analytics).</div>', unsafe_allow_html=True)

    analytics = db.get_platform_analytics()
    total_sess = analytics.get("total_sessions", 0)
    succ_rate = analytics.get("success_rate_pct", 0.0)
    avg_rnd = analytics.get("avg_rounds", 0.0)
    avg_b_conc = analytics.get("avg_buyer_concession", 0.0)
    avg_s_conc = analytics.get("avg_seller_concession", 0.0)
    avg_gap = analytics.get("avg_price_gap_pct", 0.0)

    # 5 Metric Thẻ Phân Tích
    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    col_m1.markdown(f'<div class="metric-card"><div class="metric-label">Tỷ lệ thành công</div><div class="metric-num" style="color:#16A34A;">{succ_rate}%</div></div>', unsafe_allow_html=True)
    col_m2.markdown(f'<div class="metric-card"><div class="metric-label">Số vòng trung bình</div><div class="metric-num">{avg_rnd:.1f}</div></div>', unsafe_allow_html=True)
    col_m3.markdown(f'<div class="metric-card"><div class="metric-label">Nhượng bộ Buyer TB</div><div class="metric-num">+{avg_b_conc:,.0f} đ</div></div>', unsafe_allow_html=True)
    col_m4.markdown(f'<div class="metric-card"><div class="metric-label">Nhượng bộ Seller TB</div><div class="metric-num">-{avg_s_conc:,.0f} đ</div></div>', unsafe_allow_html=True)
    col_m5.markdown(f'<div class="metric-card"><div class="metric-label">Chênh lệch giá cuối</div><div class="metric-num">{avg_gap:.1f}%</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Biểu đồ Concession Analytics
    c_chart1, c_chart2 = st.columns([1, 1])

    with c_chart1:
        st.markdown("#### Mức độ nhượng bộ trung bình (Concession Analytics)")
        fig_conc = go.Figure()
        fig_conc.add_trace(go.Bar(
            x=["Bên Mua (Nâng giá)", "Bên Bán (Hạ giá)"],
            y=[avg_b_conc, avg_s_conc],
            marker_color=["#2563EB", "#16A34A"],
            text=[f"+{avg_b_conc:,.0f} đ", f"-{avg_s_conc:,.0f} đ"],
            textposition="auto",
        ))
        fig_conc.update_layout(
            yaxis=dict(title="Mức nhượng bộ (VNĐ)"),
            margin=dict(l=30, r=30, t=20, b=30),
            height=300,
        )
        st.plotly_chart(fig_conc, use_container_width=True)

    with c_chart2:
        st.markdown("#### Phân bổ kết quả các phiên đàm phán")
        sessions_data = db.get_all_negotiation_sessions()
        success_count = sum(1 for s in sessions_data if s.get("final_status") in ("SUCCESS", "CONVERGED", "COMPLETED"))
        other_count = max(0, total_sess - success_count)
        fig_pie = go.Figure(data=[go.Pie(
            labels=["Chốt Deal Thành Công", "Cần Đàm Phán Tiếp / Hủy"],
            values=[success_count, other_count],
            hole=0.45,
            marker_colors=["#16A34A", "#F59E0B"],
        )])
        fig_pie.update_layout(
            margin=dict(l=30, r=30, t=20, b=30),
            height=300,
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # Danh sách các phiên đàm phán gần nhất từ SQLite
    st.markdown("#### Danh Sách Các Phiên Đàm Phán Gần Nhất (Audit Trail)")
    st.caption("Dữ liệu lưu vết tự động trong cơ sở dữ liệu SQLite (bảng negotiation_logs). Bấm 'Xem lại' để replay toàn bộ phiên.")

    if not sessions_data:
        st.info("Chưa có phiên đàm phán nào trong cơ sở dữ liệu. Hãy bấm 'Bắt đầu thương thảo' ở cột bên trái để khởi tạo phiên đầu tiên.")
    else:
        for s_item in sessions_data[:10]:
            sid = s_item["session_id"]
            sup_name = s_item.get("supplier_id", "Supplier")
            rounds_cnt = s_item.get("total_rounds", 1)
            status_txt = s_item.get("final_status", "ACTIVE")
            gap_val = s_item.get("final_gap_pct", 0.0)

            c_s1, c_s2, c_s3, c_s4, c_s5 = st.columns([0.25, 0.35, 0.15, 0.15, 0.1])
            with c_s1:
                st.markdown(f"**`{sid}`**")
            with c_s2:
                st.write(sup_name)
            with c_s3:
                st.write(f"{rounds_cnt} vòng (Gap: {gap_val:.1f}%)")
            with c_s4:
                badge_color = "#16A34A" if status_txt in ("SUCCESS", "CONVERGED", "COMPLETED") else "#D97706"
                st.markdown(f"<span style='color:{badge_color}; font-weight:700;'>{status_txt}</span>", unsafe_allow_html=True)
            with c_s5:
                if st.button("Xem lại", key=f"btn_replay_{sid}", use_container_width=True):
                    st.session_state["replayed_session_id"] = sid
                    st.session_state["graph_result"] = None
                    st.rerun()
