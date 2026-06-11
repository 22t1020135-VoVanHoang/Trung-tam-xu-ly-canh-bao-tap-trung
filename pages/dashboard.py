"""Dashboard page"""
import streamlit as st
from datetime import datetime
import json
from pathlib import Path

STATE_FILE = Path(__file__).parent.parent / "config" / "state.json"

DEFAULT_STATE = {
    "last_scan":        None,
    "last_email_sent":  None,
    "red_indicators":   [],
    "report_date":      None,
    "deadline":         None,
    "status":           "idle",
    "total_scans":      0,
    "total_emails_sent": 0,
}

REFRESH_INTERVAL_MS = 60_000  # 60 giây


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            content = STATE_FILE.read_text(encoding="utf-8").strip()
            return json.loads(content) if content else DEFAULT_STATE.copy()
        except Exception:
            try:
                STATE_FILE.unlink()
            except Exception:
                pass
    return DEFAULT_STATE.copy()


def render(config: dict):
    state      = load_state()
    sched_cfg  = config.get("scheduler", {})
    deadline_h = sched_cfg.get("reply_deadline_hour", 11)
    deadline_m = sched_cfg.get("reply_deadline_minute", 45)
    red_count  = len(state.get("red_indicators", []))
    cfg_ok     = bool(config.get("email", {}).get("address"))

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="sys-header">
        <div>
            <div class="badge">LIVE</div>
            <h1>SOC Alert Automation Dashboard</h1>
            <div class="subtitle">Chi nhánh Huế – Hệ thống tự động hóa cảnh báo chỉ số đỏ</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Status bar ────────────────────────────────────────────────────────────
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

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Metric cards ──────────────────────────────────────────────────────────
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

    # ── Main content ──────────────────────────────────────────────────────────
    col_a, col_b = st.columns([3, 2])

    with col_a:
        st.markdown('<div class="section-label">LUỒNG VẬN HÀNH</div>', unsafe_allow_html=True)
        steps = [
            ("01", "Tiếp nhận Email",
             f"Quét email từ '{config.get('soc_sender_name', 'SOC Canh bao')}' qua IMAP",
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

    with col_b:
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

        st.markdown("<br>", unsafe_allow_html=True)
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

    # ── Auto-refresh ──────────────────────────────────────────────────────────
    # Bỏ qua lần đầu sau đăng nhập để tránh refresh ngay lập tức
    if st.session_state.pop("just_logged_in", False):
        return

    col_label, col_toggle = st.columns([4, 1])
    with col_toggle:
        auto_refresh = st.toggle("🔄 Tự động cập nhật", value=False, key="dash_auto_refresh")

    if auto_refresh:
        from streamlit_autorefresh import st_autorefresh
        with col_label:
            st.markdown(
                '<div style="font-family:var(--mono); font-size:11px; '
                'color:var(--text-muted); padding:8px 0;">'
                f'🔄 Tự động cập nhật mỗi {REFRESH_INTERVAL_MS // 1000} giây</div>',
                unsafe_allow_html=True,
            )
        st_autorefresh(interval=REFRESH_INTERVAL_MS, key="dash_refresh_timer")