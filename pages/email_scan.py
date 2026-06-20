"""
pages/email_scan.py
Trang Quét Email SOC — đọc và phân tích email cảnh báo từ SOC Canh Bao.

Thay đổi so với bản cũ:
  - Xóa load_state / save_state / STATE_FILE duplicate → dùng utils.state_manager
  - Fix Bug #1: _backup_state() NameError đã được giải quyết qua state_manager
  - Tách render() thành _do_scan() + _render_results() → Single Responsibility
  - Thêm append_log cho cả scan thành công lẫn thất bại
  - Lưu thêm latest_email_date vào state
"""
import streamlit as st
from datetime import datetime

from utils.constants    import DEFAULT_SOC_SENDER
from utils.state_manager import load_state, save_state, append_log


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC
# ─────────────────────────────────────────────────────────────────────────────

def render(config: dict) -> None:
    st.markdown("""
    <div class="sys-header">
        <div>
            <h1>📧 Quét Email SOC</h1>
            <div class="subtitle">Đọc và phân tích email cảnh báo từ SOC Canh Bao</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    email_cfg  = config.get("email", {})
    has_config = bool(email_cfg.get("address") and email_cfg.get("password"))

    if not has_config:
        st.markdown("""
        <div class="alert-box warning">
            ⚠️ Chưa cấu hình email. Vui lòng vào <strong>Cấu hình</strong>
            để nhập thông tin tài khoản email trước.
        </div>
        """, unsafe_allow_html=True)
        if st.button("⚙️ Đi đến Cấu hình"):
            st.session_state.page = "settings"
            st.rerun()
        return

    col_result, col_config = st.columns([2, 1])

    with col_config:
        _render_scan_config(config)

    with col_result:
        st.markdown('<div class="section-label">KẾT QUẢ QUÉT</div>', unsafe_allow_html=True)
        # Trigger scan nếu người dùng vừa bấm nút
        if st.session_state.get("trigger_scan"):
            st.session_state.trigger_scan = False
            _do_scan(
                email_cfg,
                st.session_state.get("scan_sender", DEFAULT_SOC_SENDER),
                st.session_state.get("scan_limit", 10),
            )
        _render_results()


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE — UI components
# ─────────────────────────────────────────────────────────────────────────────

def _render_scan_config(config: dict) -> None:
    """Panel cấu hình + nút bấm quét."""
    st.markdown('<div class="section-label">CẤU HÌNH QUÉT</div>', unsafe_allow_html=True)

    sender_name = st.text_input(
        "Tên người gửi",
        value=config.get("soc_sender_name", DEFAULT_SOC_SENDER),
    )
    limit = st.number_input("Số email tối đa", min_value=1, max_value=50, value=10)

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("🔍 Quét Email Ngay", type="primary", use_container_width=True):
        st.session_state.trigger_scan = True
        st.session_state.scan_sender  = sender_name
        st.session_state.scan_limit   = limit


def _render_results() -> None:
    """Hiển thị kết quả parse từ session state, hoặc trạng thái lần quét trước."""
    parsed = st.session_state.get("parsed_email")
    emails = st.session_state.get("scanned_emails", [])

    if not parsed:
        _render_last_scan_summary()
        return

    _render_email_header(emails)
    _render_kpi_cards(parsed)
    _render_red_indicators(parsed)
    _render_manual_add(parsed.get("red_indicators", []))
    _render_raw_email(emails)


def _render_last_scan_summary() -> None:
    """Hiển thị tóm tắt lần quét cuối khi chưa có kết quả mới."""
    state = load_state()
    if state.get("last_scan"):
        indicators_str = ", ".join(state.get("red_indicators", [])) or "Không có"
        st.markdown(f"""
        <div class="alert-box info">
            Lần quét cuối: <strong>{state['last_scan']}</strong><br>
            Chỉ số đỏ: <strong>{indicators_str}</strong>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="alert-box info">Nhấn "Quét Email Ngay" để bắt đầu.</div>',
            unsafe_allow_html=True,
        )


def _render_email_header(emails: list) -> None:
    """Hiển thị thông tin email mới nhất."""
    if not emails:
        return
    latest = emails[0]
    st.markdown(f"""
    <div class="config-section" style="margin-bottom:16px;">
        <h4>EMAIL MỚI NHẤT</h4>
        <div style="font-size:13px; line-height:1.8;">
            <div>
                <span style="color:var(--text-muted); font-family:var(--mono); font-size:11px;">TỪ:</span>
                {latest['sender']}
            </div>
            <div>
                <span style="color:var(--text-muted); font-family:var(--mono); font-size:11px;">CHỦ ĐỀ:</span>
                {latest['subject']}
            </div>
            <div>
                <span style="color:var(--text-muted); font-family:var(--mono); font-size:11px;">NGÀY:</span>
                {latest['date']}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_kpi_cards(parsed: dict) -> None:
    """Ba metric card: ngày báo cáo, deadline, số chỉ số đỏ."""
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="metric-card orange" style="padding:14px;">
            <div class="label">Ngày báo cáo</div>
            <div style="font-size:1rem; font-weight:700; color:var(--orange); margin-top:4px;">
                {parsed.get('report_date') or 'Không xác định'}
            </div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="metric-card red" style="padding:14px;">
            <div class="label">Deadline phản hồi</div>
            <div style="font-size:1rem; font-weight:700; color:var(--red); margin-top:4px;">
                {parsed.get('deadline') or 'Không xác định'}
            </div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="metric-card red" style="padding:14px;">
            <div class="label">Số chỉ số đỏ</div>
            <div class="value">{len(parsed.get('red_indicators', []))}</div>
        </div>
        """, unsafe_allow_html=True)


def _render_red_indicators(parsed: dict) -> None:
    """Danh sách chỉ số đỏ đã nhận diện."""
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">CHỈ SỐ ĐỎ ĐÃ NHẬN DIỆN</div>', unsafe_allow_html=True)

    red_inds = parsed.get("red_indicators", [])
    if red_inds:
        for ind in red_inds:
            st.markdown(f"""
            <div class="status-row">
                <div class="dot red"></div>
                <span style="font-size:13px; font-weight:500;">{ind}</span>
                <span style="margin-left:auto; font-family:var(--mono); font-size:10px; color:var(--text-muted);">
                    CẦN GIẢI TRÌNH
                </span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="alert-box info">'
            'Hệ thống chưa nhận diện được chỉ số đỏ tự động. '
            'Bạn có thể thêm thủ công bên dưới.</div>',
            unsafe_allow_html=True,
        )


def _render_manual_add(current_indicators: list) -> None:
    """Expander cho phép thêm/sửa chỉ số đỏ thủ công."""
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("➕ Thêm chỉ số đỏ thủ công"):
        from utils.sheets_utils import INDICATOR_TO_SHEET
        all_indicators = list(INDICATOR_TO_SHEET.keys())
        selected = st.multiselect(
            "Chọn chỉ số đỏ",
            all_indicators,
            default=current_indicators,
        )
        if st.button("💾 Cập nhật danh sách", type="primary"):
            state = load_state()
            state["red_indicators"] = selected
            save_state(state)
            # Cập nhật luôn session state để UI phản ánh ngay
            if st.session_state.get("parsed_email"):
                st.session_state.parsed_email["red_indicators"] = selected
            append_log(
                "SCAN_EMAIL",
                f"Cập nhật thủ công chỉ số đỏ: {selected}",
                "warning",
            )
            # B4: bản cũ dùng st.success() ngay trước st.rerun() → bị xóa
            # NGAY LẬP TỨC, không bao giờ kịp hiển thị (cùng lỗi như
            # scheduler_page.py). st.toast() sống sót qua rerun kế tiếp.
            st.toast("Đã cập nhật danh sách chỉ số đỏ", icon="✅")
            st.rerun()


def _render_raw_email(emails: list) -> None:
    """Expander xem nội dung email gốc."""
    with st.expander("📄 Xem nội dung email gốc"):
        if emails:
            st.text_area("Nội dung", value=emails[0]["body"], height=300, disabled=True)
        else:
            st.info("Không có dữ liệu email.")


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE — Business logic
# ─────────────────────────────────────────────────────────────────────────────

def _do_scan(email_cfg: dict, sender_name: str, limit: int) -> None:
    """
    Kết nối IMAP, quét email, parse chỉ số đỏ, lưu state + log.
    Tách riêng khỏi render() để dễ test và dễ đọc.
    """
    with st.spinner("Đang kết nối IMAP và quét email..."):
        try:
            from utils.email_utils import connect_imap, search_soc_emails, parse_soc_email

            mail   = connect_imap(
                email_cfg["address"],
                email_cfg["password"],
                email_cfg.get("imap_server", "imap.gmail.com"),
            )
            emails = search_soc_emails(mail, sender_name, limit)
            mail.logout()

            if not emails:
                st.toast(f'Không tìm thấy email nào từ "{sender_name}"', icon="⚠️")
                append_log("SCAN_EMAIL", f'Không tìm thấy email từ "{sender_name}"', "warning")
                return

            latest = emails[0]
            parsed = parse_soc_email(
                latest["body"],
                latest["date"],
                latest.get("body_html", ""),  # truyền HTML để parse chính xác
            )

            # Lưu vào session state để _render_results() dùng
            st.session_state.scanned_emails = emails
            st.session_state.parsed_email   = parsed

            # Cập nhật state.json qua state_manager (thread-safe + atomic)
            state = load_state()
            state.update({
                "last_scan":            datetime.now().strftime("%d/%m/%Y %H:%M"),
                "last_scan_date":       datetime.now().strftime("%d/%m/%Y"),
                "total_scans":          state.get("total_scans", 0) + 1,
                "red_indicators":       parsed["red_indicators"],
                "report_date":          parsed["report_date"],
                "deadline":             parsed["deadline"],
                "status":               "active",
                "latest_email_sender":  latest["sender"],
                "latest_email_subject": latest["subject"],
                "latest_email_date":    latest["date"],
            })
            save_state(state)

            append_log(
                "SCAN_EMAIL",
                f"Tìm thấy {len(emails)} email · "
                f"{len(parsed['red_indicators'])} chỉ số đỏ · "
                f"Ngày BC: {parsed.get('report_date', '?')}",
                "success",
            )

            # B4: bỏ alert-box chi tiết trùng lặp — _render_results() ngay
            # bên dưới đã hiện đầy đủ KPI card + danh sách chỉ số đỏ, alert-box
            # cũ chỉ lặp lại thông tin "tìm thấy N email" không cần thiết.
            st.toast(f"Đã quét xong · tìm thấy {len(emails)} email", icon="✅")

        except Exception as e:
            err_msg = str(e)
            st.toast("Lỗi kết nối IMAP — xem chi tiết bên dưới", icon="❌")
            st.markdown(
                f'<div class="alert-box error">❌ Lỗi kết nối IMAP: {err_msg}</div>',
                unsafe_allow_html=True,
            )
            append_log("SCAN_EMAIL", f"Lỗi IMAP: {err_msg}", "error")