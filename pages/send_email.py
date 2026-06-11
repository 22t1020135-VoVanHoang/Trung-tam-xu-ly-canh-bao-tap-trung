"""Send Email page"""
import streamlit as st
import json
from pathlib import Path
from datetime import datetime

STATE_FILE = Path(__file__).parent.parent / "config" / "state.json"
LOG_FILE   = Path(__file__).parent.parent / "config" / "logs.json"

DEFAULT_STATE = {
    "red_indicators": [], "report_date": None, "latest_email_sender": "",
    "latest_email_subject": "", "total_emails_sent": 0
}

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

def save_state(state):
    STATE_FILE.parent.mkdir(exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    _backup_state()

def render(config: dict):
    st.markdown("""
    <div class="sys-header">
        <div>
            <h1>📤 Gửi Email Phản hồi</h1>
            <div class="subtitle">Tổng hợp giải trình từ Google Sheets và gửi reply cho SOC</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    state = load_state()
    email_cfg  = config.get("email", {})
    sheets_cfg = config.get("google_sheets", {})

    has_email  = bool(email_cfg.get("address") and email_cfg.get("password"))
    has_sheets = bool(sheets_cfg.get("credentials_path")) or _has_streamlit_secrets()
    red_indicators = state.get("red_indicators", [])

    checks = [
        ("Email đã cấu hình",          has_email,            "Vào Cấu hình > Email"),
        ("Có chỉ số đỏ",               bool(red_indicators), "Quét email trước"),
        ("Google Sheets (tuỳ chọn)",   has_sheets,           "Để tự động lấy giải trình"),
    ]

    st.markdown('<div class="section-label">KIỂM TRA SẴN SÀNG</div>', unsafe_allow_html=True)
    all_required_ok = has_email and bool(red_indicators)

    for label, ok, hint in checks:
        color = "green" if ok else ("orange" if "tuỳ chọn" in label else "red")
        st.markdown(f"""
        <div class="status-row">
            <div class="dot {color}"></div>
            <span style="font-size:13px; font-weight:{'600' if not ok else '400'};">{label}</span>
            {f'<span style="margin-left:auto; font-size:11px; color:var(--text-muted);">{hint}</span>' if not ok else '<span style="margin-left:auto; font-family:var(--mono); font-size:10px; color:#48BB78;">OK</span>'}
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2 = st.columns([3, 2])

    with col2:
        st.markdown('<div class="section-label">CẤU HÌNH GỬI</div>', unsafe_allow_html=True)

        to_address      = st.text_input("Gửi tới (To)", value=state.get("latest_email_sender", ""))
        subject_default = f"Re: {state.get('latest_email_subject', 'SOC Canh bao')} – Giải trình {state.get('report_date','')}"
        subject         = st.text_input("Tiêu đề", value=subject_default)
        cc_input        = st.text_area("CC (mỗi địa chỉ 1 dòng)", height=80, placeholder="email1@fpt.com\nemail2@fpt.com")
        cc_list         = [e.strip() for e in cc_input.split("\n") if e.strip()]

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔍 Xem trước nội dung", use_container_width=True):
            st.session_state.preview_email = True

        st.markdown("<br>", unsafe_allow_html=True)
        send_disabled = not all_required_ok
        if st.button("📤 Gửi Email Ngay", type="primary", use_container_width=True, disabled=send_disabled):
            st.session_state.trigger_send    = True
            st.session_state.send_to         = to_address
            st.session_state.send_subject    = subject
            st.session_state.send_cc         = cc_list

        if send_disabled:
            st.markdown('<div class="alert-box warning" style="font-size:12px;">Cần cấu hình email và có chỉ số đỏ.</div>', unsafe_allow_html=True)

    with col1:
        st.markdown('<div class="section-label">NỘI DUNG EMAIL</div>', unsafe_allow_html=True)

        if st.session_state.get("trigger_send") or st.session_state.get("preview_email"):
            is_send = st.session_state.get("trigger_send", False)
            st.session_state.trigger_send  = False
            st.session_state.preview_email = False

            explanations = []
            if has_sheets and red_indicators:
                with st.spinner("Đang lấy dữ liệu từ Google Sheets..."):
                    try:
                        from utils.sheets_utils import collect_all_explanations, build_email_html
                        explanations = collect_all_explanations(
                            sheets_cfg.get("credentials_path", ""),
                            sheets_cfg.get("spreadsheet_id", ""),
                            red_indicators,
                            state.get("report_date", "")
                        )
                    except Exception as e:
                        st.markdown(f'<div class="alert-box warning">⚠️ Không lấy được Sheets: {str(e)}<br>Sẽ gửi tổng hợp không có chi tiết.</div>', unsafe_allow_html=True)
                        explanations = [{"indicator": ind, "sheet_name": ind, "rows": [], "count": 0, "error": None} for ind in red_indicators]
            else:
                explanations = [{"indicator": ind, "sheet_name": ind, "rows": [], "count": 0, "error": None} for ind in red_indicators]

            from utils.sheets_utils import build_email_html
            html_body = build_email_html(
                state.get("report_date", "N/A"),
                config.get("branch", "HUE"),
                explanations,
            )

            if is_send:
                with st.spinner("Đang gửi email..."):
                    try:
                        from utils.email_utils import send_reply_email
                        send_reply_email(
                            smtp_server=email_cfg.get("smtp_server", "smtp.gmail.com"),
                            address=email_cfg["address"],
                            password=email_cfg["password"],
                            to_address=st.session_state.get("send_to", ""),
                            subject=st.session_state.get("send_subject", subject_default),
                            body_html=html_body,
                            cc_list=st.session_state.get("send_cc", []),
                        )
                        state["last_email_sent"]    = datetime.now().strftime("%d/%m/%Y %H:%M")
                        state["total_emails_sent"]  = state.get("total_emails_sent", 0) + 1
                        save_state(state)

                        st.markdown(f'<div class="alert-box success">✅ Email đã gửi thành công đến <strong>{st.session_state.get("send_to","")}</strong> lúc {datetime.now().strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)

                        # Ghi log
                        _append_log(LOG_FILE, "EMAIL_SENT",
                            f"Gửi đến {st.session_state.get('send_to','')} – {len(red_indicators)} chỉ số",
                            "success")
                    except Exception as e:
                        st.markdown(f'<div class="alert-box error">❌ Gửi thất bại: {str(e)}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="alert-box info">📋 Xem trước – chưa gửi</div>', unsafe_allow_html=True)

            st.components.v1.html(html_body, height=600, scrolling=True)

        else:
            if red_indicators:
                st.markdown(f"""
                <div class="config-section">
                    <h4>TÓM TẮT SẼ GỬI</h4>
                    <div style="font-size:13px; line-height:2;">
                        <div>📅 Ngày báo cáo: <strong>{state.get('report_date','Chưa xác định')}</strong></div>
                        <div>🏢 Chi nhánh: <strong>{config.get('branch','HUE')}</strong></div>
                        <div>🔴 Số chỉ số đỏ: <strong>{len(red_indicators)}</strong></div>
                        <div>📤 Từ: <strong>{email_cfg.get('address','Chưa cấu hình')}</strong></div>
                    </div>
                    <div style="margin-top:12px;">
                        {''.join(f'<div class="status-row" style="margin-bottom:4px;"><div class="dot red"></div><span style="font-size:12px;">{ind}</span></div>' for ind in red_indicators)}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown('<div class="alert-box info">Chưa có dữ liệu. Hãy quét email trước để xác định chỉ số đỏ.</div>', unsafe_allow_html=True)


def _has_streamlit_secrets() -> bool:
    try:
        import streamlit as st
        return hasattr(st, 'secrets') and 'google_service_account' in st.secrets
    except Exception:
        return False


def _append_log(log_file: Path, action: str, detail: str, status: str):
    log_file.parent.mkdir(exist_ok=True)
    logs = []
    if log_file.exists():
        try:
            with open(log_file, encoding="utf-8") as f:
                content = f.read().strip()
            logs = json.loads(content) if content else []
        except Exception:
            logs = []
    logs.insert(0, {
        "time":   datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "action": action,
        "detail": detail,
        "status": status,
    })
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(logs[:100], f, ensure_ascii=False, indent=2)