"""Scheduler page"""
import streamlit as st
import json
from pathlib import Path
from datetime import datetime

STATE_FILE  = Path(__file__).parent.parent / "config" / "state.json"
CONFIG_FILE = Path(__file__).parent.parent / "config" / "settings.json"
LOG_FILE    = Path(__file__).parent.parent / "config" / "logs.json"

DEFAULT_STATE = {}

def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return DEFAULT_STATE.copy()
            return json.loads(content)
        except Exception:
            try:
                STATE_FILE.unlink()
            except Exception:
                pass
            return DEFAULT_STATE.copy()
    return DEFAULT_STATE.copy()

def render(config: dict):
    st.markdown("""
    <div class="sys-header">
        <div>
            <h1>⏱️ Lịch trình Tự động</h1>
            <div class="subtitle">Cài đặt APScheduler – quét email và gửi phản hồi tự động đúng deadline</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    state = load_state()
    sched_cfg = config.get("scheduler", {})

    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown('<div class="section-label">LỊCH TRÌNH HIỆN TẠI</div>', unsafe_allow_html=True)

        scan_interval = sched_cfg.get("scan_interval_minutes", 30)
        deadline_h    = sched_cfg.get("reply_deadline_hour", 11)
        deadline_m    = sched_cfg.get("reply_deadline_minute", 45)

        jobs = [
            {
                "name": "SCAN_EMAIL",
                "desc": "Quét email từ SOC Canh Bao",
                "schedule": f"Mỗi {scan_interval} phút",
                "next": "—",
                "status": "active",
                "color": "blue",
            },
            {
                "name": "AUTO_REPLY",
                "desc": "Tổng hợp Sheets & gửi email phản hồi",
                "schedule": f"Hàng ngày lúc {deadline_h:02d}:{deadline_m:02d}",
                "next": f"{deadline_h:02d}:{deadline_m:02d} ngày mai",
                "status": "active",
                "color": "red",
            },
            {
                "name": "PROGRESS_CHECK",
                "desc": "Kiểm tra tiến độ giải trình",
                "schedule": "Mỗi 60 phút (từ 8h-12h)",
                "next": "—",
                "status": "active",
                "color": "orange",
            },
        ]

        for job in jobs:
            st.markdown(f"""
            <div class="config-section" style="padding:16px 20px; margin-bottom:10px;">
                <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
                    <div class="dot {job['color']}"></div>
                    <span style="font-family:var(--mono); font-size:12px; font-weight:600; color:var(--text);">{job['name']}</span>
                    <span style="margin-left:auto; font-family:var(--mono); font-size:10px; color:#48BB78; text-transform:uppercase;">● {job['status']}</span>
                </div>
                <div style="font-size:13px; color:var(--text-muted); margin-bottom:6px;">{job['desc']}</div>
                <div style="display:flex; gap:24px; font-size:11px; font-family:var(--mono);">
                    <span><span style="color:var(--text-muted);">LỊCH:</span> <span style="color:var(--text);">{job['schedule']}</span></span>
                    <span><span style="color:var(--text-muted);">TIẾP THEO:</span> <span style="color:var(--text);">{job['next']}</span></span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-label">NHẬT KÝ LỊCH TRÌNH</div>', unsafe_allow_html=True)

        # Dùng đường dẫn động, KHÔNG hardcode
        if LOG_FILE.exists():
            try:
                with open(LOG_FILE, encoding="utf-8") as f:
                    content = f.read().strip()
                logs = json.loads(content) if content else []
                sched_logs = [l for l in logs if l.get("action", "").startswith(("SCAN", "AUTO", "PROG"))][:5]
                if sched_logs:
                    for log in sched_logs:
                        color = "green" if log.get("status") == "success" else "red"
                        st.markdown(f"""
                        <div class="timeline-item">
                            <div class="timeline-time">{log.get('time','')}</div>
                            <div class="timeline-content">
                                <div class="timeline-title">{log.get('action','')}</div>
                                <div class="timeline-desc">{log.get('detail','')}</div>
                            </div>
                            <div class="dot {color}" style="margin-top:6px;"></div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.markdown('<div class="alert-box info">Chưa có log lịch trình.</div>', unsafe_allow_html=True)
            except Exception:
                st.markdown('<div class="alert-box info">Chưa có log. Lịch trình chưa chạy lần nào.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="alert-box info">Chưa có log. Lịch trình chưa chạy lần nào.</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="section-label">CẤU HÌNH LỊCH TRÌNH</div>', unsafe_allow_html=True)

        scan_interval = sched_cfg.get("scan_interval_minutes", 30)
        deadline_h    = sched_cfg.get("reply_deadline_hour", 11)
        deadline_m    = sched_cfg.get("reply_deadline_minute", 45)

        new_interval   = st.number_input("Quét email mỗi (phút)", min_value=5, max_value=120, value=scan_interval)
        st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)
        new_deadline_h = st.number_input("Giờ gửi tự động (h)", min_value=0, max_value=23, value=deadline_h)
        new_deadline_m = st.number_input("Phút gửi tự động (m)", min_value=0, max_value=59, value=deadline_m)

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("💾 Lưu cấu hình lịch", type="primary", use_container_width=True):
            config["scheduler"]["scan_interval_minutes"]  = new_interval
            config["scheduler"]["reply_deadline_hour"]    = new_deadline_h
            config["scheduler"]["reply_deadline_minute"]  = new_deadline_m
            CONFIG_FILE.parent.mkdir(exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            st.markdown('<div class="alert-box success">✅ Đã lưu cấu hình lịch trình.</div>', unsafe_allow_html=True)
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-label">CHẠY THỦ CÔNG</div>', unsafe_allow_html=True)

        if st.button("🔍 Quét Email Ngay", use_container_width=True):
            st.session_state.page = "email_scan"
            st.session_state.trigger_scan = True
            st.rerun()

        if st.button("📤 Gửi Báo cáo Ngay", use_container_width=True):
            st.session_state.page = "send_email"
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("📖 Hướng dẫn khởi động hệ thống"):
            st.markdown("""
            <div style="font-size:13px; line-height:2.2; color:#E8E8EC;">
                1. Mở <strong>File Explorer</strong> (phím <code style="background:#2A2A30; padding:2px 6px; border-radius:3px;">Windows + E</code>)<br>
                2. Vào thư mục <code style="background:#2A2A30; padding:2px 6px; border-radius:3px;">E:\soc-hue\</code><br>
                3. Bấm đúp chuột vào file <code style="background:#E53E3E; color:white; padding:2px 8px; border-radius:3px;">start_soc.bat</code><br>
                <span style="color:#48BB78;">→ Hệ thống tự động mở 2 cửa sổ: <strong>App</strong> và <strong>Watchdog</strong>.</span>
            </div>
            """, unsafe_allow_html=True)