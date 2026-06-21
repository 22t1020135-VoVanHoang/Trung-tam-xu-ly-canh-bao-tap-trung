"""
pages/send_email.py
Trang Gửi Email Phản hồi — tổng hợp giải trình từ Google Sheets và gửi reply cho SOC.

Thay đổi so với bản cũ:
  - Xóa load_state / save_state / STATE_FILE / LOG_FILE / HISTORY_FILE / DEFAULT_STATE
  - Fix Bug #1: save_state() gọi _backup_state() → crash khi gửi email
  - Fix DRY #2: _has_streamlit_secrets() → dùng state_manager.has_streamlit_secrets()
  - Fix DRY #3: _append_log() / _append_history() → dùng state_manager
  - Fix Logic #1: append_history() nay được gọi đúng chỗ → lịch sử được lưu đầy đủ
  - Fix: gửi thất bại chưa được log → thêm append_log status="error"
  - Tách render() 140 dòng → 7 hàm nhỏ theo đúng SRP
"""
import streamlit as st
from datetime import datetime

from utils.constants     import DEFAULT_BRANCH, DEFAULT_SMTP_SERVER, DEFAULT_SOC_SENDER
from utils.state_manager import (
    load_state, save_state,
    append_log, append_history,
    has_streamlit_secrets,
)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC
# ─────────────────────────────────────────────────────────────────────────────

def render(config: dict) -> None:
    st.markdown("""
    <div class="sys-header">
        <div>
            <h1>📤 Gửi Email Phản hồi</h1>
            <div class="subtitle">Tổng hợp giải trình từ Google Sheets và gửi reply cho SOC</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    state          = load_state()
    email_cfg      = config.get("email", {})
    sheets_cfg     = config.get("google_sheets", {})
    red_indicators = state.get("red_indicators", [])

    has_email      = bool(email_cfg.get("address") and email_cfg.get("password"))
    has_sheets     = bool(sheets_cfg.get("credentials_path")) or has_streamlit_secrets()
    all_required_ok = has_email and bool(red_indicators)

    _render_readiness_check(has_email, has_sheets, red_indicators)
    st.markdown("<br>", unsafe_allow_html=True)

    col_content, col_config = st.columns([3, 2])

    with col_config:
        subject_default = _build_default_subject(state)
        to_address, subject, cc_list = _render_send_config(
            state, subject_default, all_required_ok
        )

    with col_content:
        st.markdown('<div class="section-label primary">NỘI DUNG EMAIL</div>', unsafe_allow_html=True)

        if st.session_state.get("trigger_send") or st.session_state.get("preview_email"):
            is_send = st.session_state.pop("trigger_send", False)
            st.session_state.preview_email = False

            explanations = _collect_explanations(
                sheets_cfg, red_indicators,
                state.get("report_date", ""), has_sheets,
            )

            from utils.sheets_utils import build_email_html
            html_body = build_email_html(
                _safe_report_date(state, fallback="N/A"),
                config.get("branch", DEFAULT_BRANCH),
                explanations,
            )

            if is_send:
                _do_send(
                    email_cfg      = email_cfg,
                    html_body      = html_body,
                    state          = state,
                    config         = config,
                    red_indicators = red_indicators,
                    explanations   = explanations,
                    to_address     = st.session_state.get("send_to", ""),
                    subject        = st.session_state.get("send_subject", subject_default),
                    cc_list        = st.session_state.get("send_cc", []),
                )
            else:
                st.markdown(
                    '<div class="alert-box info">📋 Xem trước – chưa gửi</div>',
                    unsafe_allow_html=True,
                )

            st.components.v1.html(html_body, height=600, scrolling=True)

        else:
            _render_send_summary(state, config, email_cfg, red_indicators)


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE — UI components
# ─────────────────────────────────────────────────────────────────────────────

def _render_readiness_check(
    has_email: bool,
    has_sheets: bool,
    red_indicators: list,
) -> None:
    """Hiển thị 3 dòng kiểm tra: email, chỉ số đỏ, Google Sheets."""
    st.markdown('<div class="section-label">KIỂM TRA SẴN SÀNG</div>', unsafe_allow_html=True)

    checks = [
        ("Email đã cấu hình",        has_email,            "Vào Cấu hình > Email",   False),
        ("Có chỉ số đỏ",             bool(red_indicators), "Quét email trước",        False),
        ("Google Sheets (tuỳ chọn)", has_sheets,           "Để tự động lấy giải trình", True),
    ]

    for label, ok, hint, optional in checks:
        color    = "green" if ok else ("orange" if optional else "red")
        hint_html = (
            f'<span style="margin-left:auto; font-size:var(--fs-xs); color:var(--text-muted);">{hint}</span>'
            if not ok else
            '<span style="margin-left:auto; font-family:var(--mono); font-size:var(--fs-2xs); color:var(--green);">OK</span>'
        )
        st.markdown(f"""
        <div class="status-row">
            <div class="dot {color}"></div>
            <span style="font-size:var(--fs-base); font-weight:{'600' if not ok else '400'};">{label}</span>
            {hint_html}
        </div>
        """, unsafe_allow_html=True)


def _render_send_config(
    state: dict,
    subject_default: str,
    all_required_ok: bool,
) -> tuple:
    """
    Panel cấu hình gửi: To, Subject, CC, nút Xem trước + Gửi.
    Trả về (to_address, subject, cc_list).

    Fix A3: bản cũ chỉ disable nút Gửi dựa trên all_required_ok (email đã cấu
    hình + có chỉ số đỏ) — KHÔNG kiểm tra to_address có rỗng hay không. Nếu
    state chưa từng có latest_email_sender (ví dụ thêm chỉ số đỏ thủ công mà
    chưa quét email thật), người dùng vẫn bấm gửi được với ô "To" trống →
    SMTP sẽ lỗi khi gửi cho danh sách người nhận rỗng.
    """
    st.markdown('<div class="section-label">CẤU HÌNH GỬI</div>', unsafe_allow_html=True)

    to_address = st.text_input("Gửi tới (To)", value=state.get("latest_email_sender", ""))
    subject    = st.text_input("Tiêu đề", value=subject_default)
    cc_input   = st.text_area(
        "CC (mỗi địa chỉ 1 dòng)", height=80,
        placeholder="email1@fpt.com\nemail2@fpt.com",
    )
    cc_list = [e.strip() for e in cc_input.split("\n") if e.strip()]

    # Tính lại điều kiện gửi NGAY TẠI ĐÂY, sau khi đã biết to_address thực tế
    # người dùng vừa nhập/sửa trong ô — all_required_ok truyền từ ngoài vào
    # chưa thể biết giá trị này vì ô "To" render SAU khi all_required_ok được tính.
    has_recipient = bool(to_address.strip())
    can_send      = all_required_ok and has_recipient

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔍 Xem trước nội dung", use_container_width=True):
        st.session_state.preview_email = True

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(
        "📤 Gửi Email Ngay", type="primary",
        use_container_width=True,
        disabled=not can_send,
    ):
        st.session_state.trigger_send   = True
        st.session_state.send_to        = to_address
        st.session_state.send_subject   = subject
        st.session_state.send_cc        = cc_list

    if not all_required_ok:
        st.markdown(
            '<div class="alert-box warning" style="font-size:var(--fs-sm);">'
            'Cần cấu hình email và có chỉ số đỏ.</div>',
            unsafe_allow_html=True,
        )
    elif not has_recipient:
        st.markdown(
            '<div class="alert-box warning" style="font-size:var(--fs-sm);">'
            '⚠️ Vui lòng nhập địa chỉ người nhận (To) trước khi gửi.</div>',
            unsafe_allow_html=True,
        )

    return to_address, subject, cc_list


def _render_send_summary(
    state: dict,
    config: dict,
    email_cfg: dict,
    red_indicators: list,
) -> None:
    """Hiển thị tóm tắt sẽ gửi khi người dùng chưa bấm nút nào."""
    if not red_indicators:
        st.markdown(
            '<div class="alert-box info">'
            'Chưa có dữ liệu. Hãy quét email trước để xác định chỉ số đỏ.</div>',
            unsafe_allow_html=True,
        )
        return

    indicators_html = "".join(
        f'<div class="status-row" style="margin-bottom:4px;">'
        f'<div class="dot red"></div>'
        f'<span style="font-size:var(--fs-sm);">{ind}</span></div>'
        for ind in red_indicators
    )
    st.markdown(f"""
    <div class="config-section">
        <h4>TÓM TẮT SẼ GỬI</h4>
        <div style="font-size:var(--fs-base); line-height:2;">
            <div>📅 Ngày báo cáo: <strong>{state.get('report_date', 'Chưa xác định')}</strong></div>
            <div>🏢 Chi nhánh: <strong>{config.get('branch', DEFAULT_BRANCH)}</strong></div>
            <div>🔴 Số chỉ số đỏ: <strong>{len(red_indicators)}</strong></div>
            <div>📤 Từ: <strong>{email_cfg.get('address', 'Chưa cấu hình')}</strong></div>
        </div>
        <div style="margin-top:12px;">{indicators_html}</div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE — Business logic
# ─────────────────────────────────────────────────────────────────────────────

def _collect_explanations(
    sheets_cfg: dict,
    red_indicators: list,
    report_date: str,
    has_sheets: bool,
) -> list:
    """
    Lấy dữ liệu giải trình từ Google Sheets cho từng chỉ số đỏ.
    Trả về list rỗng placeholder nếu chưa cấu hình Sheets.
    """
    if has_sheets and red_indicators:
        with st.spinner("Đang lấy dữ liệu từ Google Sheets..."):
            try:
                from utils.sheets_utils import collect_all_explanations
                return collect_all_explanations(
                    sheets_cfg.get("credentials_path", ""),
                    sheets_cfg.get("spreadsheet_id", ""),
                    red_indicators,
                    report_date,
                )
            except Exception as e:
                st.markdown(
                    f'<div class="alert-box warning">'
                    f'⚠️ Không lấy được Sheets: {str(e)}<br>'
                    f'Sẽ gửi tổng hợp không có chi tiết.</div>',
                    unsafe_allow_html=True,
                )

    # Fallback: placeholder không có dữ liệu
    return [
        {"indicator": ind, "sheet_name": ind, "rows": [], "count": 0, "error": None}
        for ind in red_indicators
    ]


def _do_send(
    email_cfg:      dict,
    html_body:      str,
    state:          dict,
    config:         dict,
    red_indicators: list,
    explanations:   list,
    to_address:     str,
    subject:        str,
    cc_list:        list,
) -> None:
    """
    Gửi email SMTP, cập nhật state, ghi log và lưu history.
    Tách riêng để dễ test và dễ theo dõi luồng xử lý.
    """
    branch = config.get("branch", DEFAULT_BRANCH)

    with st.spinner("Đang gửi email..."):
        try:
            from utils.email_utils import send_reply_email
            send_reply_email(
                smtp_server = email_cfg.get("smtp_server", DEFAULT_SMTP_SERVER),
                address     = email_cfg["address"],
                password    = email_cfg["password"],
                to_address  = to_address,
                subject     = subject,
                body_html   = html_body,
                cc_list     = cc_list,
            )

            # Cập nhật state
            # Quan trọng: cập nhật cả last_sent_report_date — nếu Admin gửi thủ
            # công, scheduler tự động (job_send_report) sẽ biết report_date này
            # ĐÃ được xử lý và không gửi trùng lại vào lần chạy tiếp theo.
            # Dùng _safe_report_date() để KHÔNG lưu None vào state/history —
            # nếu không, history_page.py hiển thị sẽ in chữ "None" (cùng lỗi
            # .get() y hệt khi đọc lại từ history.json).
            safe_report_date = _safe_report_date(state)
            state["last_email_sent"]       = datetime.now().strftime("%d/%m/%Y %H:%M")
            state["total_emails_sent"]     = state.get("total_emails_sent", 0) + 1
            state["last_sent_report_date"] = safe_report_date
            save_state(state)

            # Ghi log thành công
            append_log(
                "EMAIL_SENT",
                f"Gửi đến {to_address} – {len(red_indicators)} chỉ số đỏ",
                "success",
            )

            # Lưu lịch sử (Fix Logic #1: đảm bảo history được ghi)
            append_history(
                report_date    = safe_report_date,
                branch         = branch,
                to_address     = to_address,
                subject        = subject,
                red_indicators = red_indicators,
                explanations   = explanations,
                status         = "success",
            )

            # B4: hành động "gửi email cho SOC" có rủi ro cao — giữ alert-box
            # PERSISTENT (không tự biến mất) làm bằng chứng rõ ràng, đồng thời
            # thêm toast để có phản hồi tức thì ngay khi vừa bấm gửi. Đây là
            # lựa chọn có chủ đích, khác với các hành động ít rủi ro hơn
            # (lưu cấu hình...) chỉ dùng toast đơn thuần.
            st.toast(f"Đã gửi email đến {to_address}", icon="✅")
            st.markdown(
                f'<div class="alert-box success">'
                f'✅ Email đã gửi thành công đến <strong>{to_address}</strong> '
                f'lúc {datetime.now().strftime("%H:%M:%S")}</div>',
                unsafe_allow_html=True,
            )

        except Exception as e:
            err_msg = str(e)

            # Ghi log thất bại (Fix: bản cũ không log lỗi này)
            append_log(
                "EMAIL_SENT",
                f"Gửi thất bại đến {to_address}: {err_msg}",
                "error",
            )

            # Lưu lịch sử thất bại để truy vết
            append_history(
                report_date    = _safe_report_date(state),
                branch         = branch,
                to_address     = to_address,
                subject        = subject,
                red_indicators = red_indicators,
                explanations   = explanations,
                status         = "error",
            )

            st.toast("Gửi email thất bại — xem chi tiết bên dưới", icon="❌")
            st.markdown(
                f'<div class="alert-box error">❌ Gửi thất bại: {err_msg}</div>',
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE — Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_report_date(state: dict, fallback: str = "chưa xác định") -> str:
    """
    Lấy report_date an toàn — tránh lỗi 'None' lọt vào email gửi cho SOC.

    Fix A1: `state.get("report_date", "")` KHÔNG bảo vệ được trường hợp key
    TỒN TẠI với giá trị None (chỉ áp dụng default khi key bị THIẾU hoàn toàn).
    Vì DEFAULT_STATE có "report_date": None, và parse có thể thất bại không
    tìm được ngày → giá trị thực trong state là None → f"...{None}" in ra
    chữ "None" y nguyên trong tiêu đề/nội dung email gửi cho SOC.
    """
    return state.get("report_date") or fallback


def _build_default_subject(state: dict) -> str:
    """Xây dựng tiêu đề email mặc định từ state."""
    original_subject = state.get("latest_email_subject") or DEFAULT_SOC_SENDER
    report_date       = _safe_report_date(state)
    return f"Re: {original_subject} – Giải trình {report_date}"