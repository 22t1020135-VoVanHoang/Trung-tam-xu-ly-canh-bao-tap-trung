"""
pages/dashboard.py
Trang Dashboard tổng quan — trạng thái hệ thống, luồng vận hành, chỉ số đỏ hiện tại.

Thay đổi so với bản cũ:
  - Xóa STATE_FILE / DEFAULT_STATE / load_state() duplicate → dùng utils.state_manager
    (DEFAULT_STATE cũ thiếu keys như last_scan_date, latest_email_* → dữ liệu hiển thị
     có thể không đồng bộ với các trang khác dùng bản DEFAULT_STATE đầy đủ hơn)
  - Thay magic string "SOC Canh bao" → DEFAULT_SOC_SENDER
  - Tách render() ~150 dòng → các hàm nhỏ theo Single Responsibility
"""
import streamlit as st
from datetime import datetime

from utils.constants     import DEFAULT_SOC_SENDER
from utils.state_manager import load_state

REFRESH_INTERVAL_MS = 60_000  # 60 giây


def render(config: dict) -> None:
    state      = load_state()
    sched_cfg  = config.get("scheduler", {})
    deadline_h = sched_cfg.get("reply_deadline_hour", 11)
    deadline_m = sched_cfg.get("reply_deadline_minute", 45)
    red_count  = len(state.get("red_indicators", []))
    cfg_ok     = bool(config.get("email", {}).get("address"))

    _render_header()
    _render_status_bar(state, deadline_h, deadline_m, cfg_ok)
    st.markdown("<br>", unsafe_allow_html=True)
    _render_metric_cards(state, red_count)

    col_a, col_b = st.columns([3, 2])
    with col_a:
        _render_workflow_steps(config, state, red_count, deadline_h, deadline_m)
    with col_b:
        _render_red_indicators_panel(state)
        st.markdown("<br>", unsafe_allow_html=True)
        _render_quick_actions()

    # Bỏ qua phần auto-refresh ngay sau khi đăng nhập (tránh rerun-loop khó chịu)
    if st.session_state.pop("just_logged_in", False):
        return

    _render_auto_refresh_section()


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE — UI components
# ─────────────────────────────────────────────────────────────────────────────

def _render_header() -> None:
    st.markdown("""
    <div class="sys-header">
        <div>
            <div class="badge">LIVE</div>
            <h1>SOC Alert Automation Dashboard</h1>
            <div class="subtitle">Chi nhánh Huế – Hệ thống tự động hóa cảnh báo chỉ số đỏ</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_status_bar(state: dict, deadline_h: int, deadline_m: int, cfg_ok: bool) -> None:
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.markdown(f"""
        <div class="status-row">
            <div class="dot {'green' if state['status'] == 'active' else 'gray'}"></div>
            <span style="font-family:var(--mono); font-size:12px;">
                HỆ THỐNG: {'ĐANG CHẠY' if state['status'] == 'active' else 'STANDBY'}
            </span>
            <span style="margin-left:auto; font-family:var(--mono); font-size:11px; color:var(--text-muted);">
                {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
            </span>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="status-row">
            <div class="dot orange"></div>
            <span style="font-size:12px;">Deadline: <strong>{deadline_h:02d}:{deadline_m:02d}</strong> ngày hôm sau</span>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="status-row">
            <div class="dot {'green' if cfg_ok else 'red'}"></div>
            <span style="font-size:12px;">Config: {'Đã cấu hình' if cfg_ok else 'Chưa cấu hình'}</span>
        </div>
        """, unsafe_allow_html=True)


def _render_metric_cards(state: dict, red_count: int) -> None:
    st.markdown(f"""
    <div class="metric-grid">
        <div class="metric-card red">
            <div class="label">Chỉ số đỏ</div>
            <div class="value">{red_count}</div>
            <div class="sub">Cần giải trình</div>
        </div>
        <div class="metric-card orange">
            <div class="label">Báo cáo ngày</div>
            <div class="value" style="font-size:1.1rem; padding-top:8px;">{state.get('report_date') or '—'}</div>
            <div class="sub">Deadline: {state.get('deadline') or '—'}</div>
        </div>
        <div class="metric-card green">
            <div class="label">Tổng email đã gửi</div>
            <div class="value">{state.get('total_emails_sent', 0)}</div>
            <div class="sub">Phản hồi tự động</div>
        </div>
        <div class="metric-card blue">
            <div class="label">Lần quét cuối</div>
            <div class="value" style="font-size:1rem; padding-top:10px;">{state.get('last_scan') or '—'}</div>
            <div class="sub">Tổng: {state.get('total_scans', 0)} lần</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_workflow_steps(
    config: dict, state: dict, red_count: int, deadline_h: int, deadline_m: int
) -> None:
    st.markdown('<div class="section-label">LUỒNG VẬN HÀNH</div>', unsafe_allow_html=True)

    sender_name = config.get("soc_sender_name", DEFAULT_SOC_SENDER)
    steps = [
        ("01", "Tiếp nhận Email",
         f"Quét email từ '{sender_name}' qua IMAP",
         "green" if state.get("last_scan") else "gray"),
        ("02", "Bóc tách Chỉ số Đỏ",
         f"{red_count} chỉ số đỏ được nhận diện từ bảng KPI",
         "red" if red_count > 0 else "gray"),
        ("03", "Nhân viên Giải trình",
         "Cập nhật nội dung vào Google Sheets theo từng tab",
         "orange" if red_count > 0 else "gray"),
        ("04", "Tổng hợp & Phản hồi",
         f"Tự động gửi reply trước deadline {deadline_h:02d}:{deadline_m:02d}",
         "green" if state.get("last_email_sent") else "gray"),
    ]
    for num, title, desc, color in steps:
        text_color = "red" if color == "red" else ("text-muted" if color == "gray" else color)
        st.markdown(f"""
        <div class="status-row" style="gap:14px; align-items:flex-start;">
            <div style="font-family:var(--mono); font-size:1.5rem; font-weight:700;
                color:var(--{text_color}); min-width:32px; line-height:1;">{num}</div>
            <div>
                <div style="font-weight:600; font-size:13px; color:var(--text);">{title}</div>
                <div style="font-size:12px; color:var(--text-muted); margin-top:2px;">{desc}</div>
            </div>
            <div class="dot {color}" style="margin-left:auto; margin-top:6px; flex-shrink:0;"></div>
        </div>
        """, unsafe_allow_html=True)


def _render_red_indicators_panel(state: dict) -> None:
    st.markdown('<div class="section-label">CHỈ SỐ ĐỎ HIỆN TẠI</div>', unsafe_allow_html=True)
    indicators = state.get("red_indicators", [])
    if indicators:
        for ind in indicators:
            st.markdown(f"""
            <div class="status-row">
                <div class="dot red"></div>
                <span style="font-size:13px; font-weight:500;">{ind}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="alert-box info">
            Chưa có dữ liệu. Hãy quét email để nhận diện chỉ số đỏ.
        </div>
        """, unsafe_allow_html=True)


def _render_quick_actions() -> None:
    st.markdown('<div class="section-label">THAO TÁC NHANH</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📧 Quét Email", use_container_width=True):
            st.session_state.page = "email_scan"
            st.rerun()
    with c2:
        if st.button("📤 Gửi Báo cáo", use_container_width=True):
            st.session_state.page = "send_email"
            st.rerun()
    if st.button("⚙️ Vào Cài đặt", use_container_width=True):
        st.session_state.page = "settings"
        st.rerun()


def _render_auto_refresh_section() -> None:
    st.markdown(
        "<hr style='border:none; border-top:1px solid var(--border); margin:8px 0;'>",
        unsafe_allow_html=True,
    )
    col_status, col_toggle = st.columns([5, 1])
    with col_toggle:
        auto_refresh = st.toggle("Tự động cập nhật", value=False, key="dash_auto_refresh")
    with col_status:
        if auto_refresh:
            interval_s = REFRESH_INTERVAL_MS // 1000
            st.markdown(
                f'<div style="font-family:var(--mono); font-size:11px; '
                f'color:#48BB78; padding:10px 0; display:flex; align-items:center; gap:6px;">'
                f'<span style="width:6px;height:6px;border-radius:50%;background:#48BB78;'
                f'display:inline-block;box-shadow:0 0 6px #48BB78;"></span>'
                f'Đang tự động cập nhật · mỗi {interval_s} giây</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="font-family:var(--mono); font-size:11px; '
                'color:var(--text-muted); padding:10px 0;">'
                'Bật toggle để tự động cập nhật dữ liệu</div>',
                unsafe_allow_html=True,
            )

    if auto_refresh:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=REFRESH_INTERVAL_MS, key="dash_refresh_timer")