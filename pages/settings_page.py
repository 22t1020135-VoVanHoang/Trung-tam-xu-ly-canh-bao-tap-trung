"""
pages/settings_page.py
Trang Cấu hình Hệ thống — email, Google Sheets, thông tin chi nhánh, lịch trình, mật khẩu.

Thay đổi so với bản cũ:
  - render() KHÔNG còn nhận save_config làm tham số → tự import từ
    utils.state_manager, nhất quán với mọi trang khác (dashboard, scheduler_page...)
  - Xóa _has_streamlit_secrets() duplicate (lần thứ 3 trong dự án) → dùng
    state_manager.has_streamlit_secrets()
  - Thay hardcode "imap.gmail.com", "smtp.gmail.com", spreadsheet ID, "HUE",
    "SOC Canh bao" → dùng hằng số trong utils.constants
  - Xóa import DEFAULT_PASSWORD không dùng đến trong render_password_section()
  - Thêm append_log() cho mỗi lần lưu cấu hình — trước đây không có audit trail
    nào ghi lại ai đổi cấu hình gì, lúc nào
  - B4: 4 xác nhận lưu/đổi mật khẩu (vốn là hành động đơn lẻ, ít rủi ro) chuyển
    từ alert-box tĩnh (tồn tại vô thời hạn cho đến lần rerun kế tiếp) sang
    st.toast (tự biến mất sau ~4s, không cần tương tác thêm để dismiss). 3
    thông báo LỖI XÁC THỰC khi đổi mật khẩu vẫn giữ alert-box vì cần hiển thị
    liên tục cho đến khi người dùng sửa đúng — không phù hợp với toast vốn tự
    biến mất bất kể người dùng đã đọc hay chưa. Kết quả test kết nối (IMAP/
    SMTP/Sheets) cũng GIỮ NGUYÊN alert-box vì chứa nội dung debug chi tiết cần
    đọc kỹ, không phải xác nhận đơn giản.
"""
import streamlit as st

from utils.constants     import (
    DEFAULT_IMAP_SERVER, DEFAULT_SMTP_SERVER,
    DEFAULT_SPREADSHEET_ID, DEFAULT_BRANCH, DEFAULT_SOC_SENDER,
    DEFAULT_SCAN_INTERVAL, DEFAULT_REPLY_HOUR, DEFAULT_REPLY_MINUTE,
)
from utils.state_manager import save_config, append_log, has_streamlit_secrets


def render(config: dict) -> None:
    st.markdown("""
    <div class="sys-header">
        <div>
            <h1>⚙️ Cấu hình Hệ thống</h1>
            <div class="subtitle">Thiết lập email, Google Sheets, và thông số hoạt động</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["📧  Email", "📊  Google Sheets", "🏢  Hệ thống", "🔑  Kết nối test"])

    with tab1:
        _render_email_tab(config)
    with tab2:
        _render_sheets_tab(config)
    with tab3:
        _render_system_tab(config)
        render_password_section(config)
    with tab4:
        _render_connection_test_tab(config)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — EMAIL
# ─────────────────────────────────────────────────────────────────────────────

def _render_email_tab(config: dict) -> None:
    st.markdown("<br>", unsafe_allow_html=True)
    email_cfg = config.get("email", {})

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="config-section"><h4>TÀI KHOẢN ADMIN</h4>', unsafe_allow_html=True)
        address  = st.text_input("Địa chỉ email (Admin)", value=email_cfg.get("address", ""), placeholder="admin@gmail.com")
        password = st.text_input("Mật khẩu / App Password", value=email_cfg.get("password", ""), type="password", placeholder="Dùng App Password nếu bật 2FA")
        st.markdown("</div>", unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="config-section"><h4>MÁY CHỦ EMAIL</h4>', unsafe_allow_html=True)
        imap_server = st.text_input("IMAP Server", value=email_cfg.get("imap_server", DEFAULT_IMAP_SERVER))
        smtp_server = st.text_input("SMTP Server", value=email_cfg.get("smtp_server", DEFAULT_SMTP_SERVER))
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class="alert-box info" style="font-size:12px;">
        💡 <strong>Gmail:</strong> Dùng <strong>App Password</strong> (Tài khoản Google → Bảo mật → Xác minh 2 bước → Mật khẩu ứng dụng).
    </div>
    """, unsafe_allow_html=True)

    if st.button("💾 Lưu cấu hình Email", type="primary"):
        config["email"] = {
            "address": address, "password": password,
            "imap_server": imap_server, "smtp_server": smtp_server,
        }
        save_config(config)
        append_log("CONFIG_UPDATE", f"Cập nhật cấu hình Email ({address or 'trống'})", "success")
        st.toast("Đã lưu cấu hình email", icon="✅")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — GOOGLE SHEETS
# ─────────────────────────────────────────────────────────────────────────────

def _render_sheets_tab(config: dict) -> None:
    st.markdown("<br>", unsafe_allow_html=True)
    sheets_cfg = config.get("google_sheets", {})

    st.markdown('<div class="config-section"><h4>GOOGLE SHEETS</h4>', unsafe_allow_html=True)
    spreadsheet_id = st.text_input(
        "Spreadsheet ID",
        value=sheets_cfg.get("spreadsheet_id", DEFAULT_SPREADSHEET_ID),
        help="Lấy từ URL: https://docs.google.com/spreadsheets/d/[ID]/edit"
    )
    creds_path = st.text_input(
        "Đường dẫn Service Account JSON",
        value=sheets_cfg.get("credentials_path", ""),
        placeholder="service-account.json hoặc đường dẫn đầy đủ",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    if st.button("💾 Lưu cấu hình Sheets", type="primary"):
        config["google_sheets"] = {"spreadsheet_id": spreadsheet_id, "credentials_path": creds_path}
        save_config(config)
        append_log("CONFIG_UPDATE", "Cập nhật cấu hình Google Sheets", "success")
        st.toast("Đã lưu cấu hình Google Sheets", icon="✅")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — HỆ THỐNG
# ─────────────────────────────────────────────────────────────────────────────

def _render_system_tab(config: dict) -> None:
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="config-section"><h4>THÔNG TIN HỆ THỐNG</h4>', unsafe_allow_html=True)
        branch     = st.text_input("Chi nhánh", value=config.get("branch", DEFAULT_BRANCH))
        soc_sender = st.text_input("Tên người gửi SOC", value=config.get("soc_sender_name", DEFAULT_SOC_SENDER))
        st.markdown("</div>", unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="config-section"><h4>LỊCH TRÌNH</h4>', unsafe_allow_html=True)
        sched    = config.get("scheduler", {})
        scan_min = st.number_input("Quét mỗi (phút)",    5, 120, sched.get("scan_interval_minutes", DEFAULT_SCAN_INTERVAL))
        reply_h  = st.number_input("Giờ gửi tự động",     0, 23,  sched.get("reply_deadline_hour",    DEFAULT_REPLY_HOUR))
        reply_m  = st.number_input("Phút gửi tự động",    0, 59,  sched.get("reply_deadline_minute",  DEFAULT_REPLY_MINUTE))
        st.markdown("</div>", unsafe_allow_html=True)

    if st.button("💾 Lưu cài đặt hệ thống", type="primary"):
        config["branch"]          = branch
        config["soc_sender_name"] = soc_sender
        config["scheduler"] = {
            "scan_interval_minutes": scan_min,
            "reply_deadline_hour":   reply_h,
            "reply_deadline_minute": reply_m,
        }
        save_config(config)
        append_log(
            "CONFIG_UPDATE",
            f"Cập nhật hệ thống: chi nhánh={branch}, quét mỗi {scan_min}p, gửi lúc {reply_h:02d}:{reply_m:02d}",
            "success",
        )
        st.toast("Đã lưu cài đặt hệ thống", icon="✅")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — KẾT NỐI TEST
# ─────────────────────────────────────────────────────────────────────────────

def _render_connection_test_tab(config: dict) -> None:
    st.markdown("<br>", unsafe_allow_html=True)
    email_cfg  = config.get("email", {})
    sheets_cfg = config.get("google_sheets", {})

    st.markdown('<div class="section-label">KIỂM TRA KẾT NỐI</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔌 Test IMAP", use_container_width=True, disabled=not email_cfg.get("address")):
            with st.spinner("Đang kết nối IMAP..."):
                from utils.email_utils import test_imap_connection
                ok, msg = test_imap_connection(
                    email_cfg["address"], email_cfg["password"],
                    email_cfg.get("imap_server", DEFAULT_IMAP_SERVER),
                )
                st.markdown(f'<div class="alert-box {"success" if ok else "error"}">{"✅" if ok else "❌"} {msg}</div>', unsafe_allow_html=True)
    with col2:
        if st.button("📤 Test SMTP", use_container_width=True, disabled=not email_cfg.get("address")):
            with st.spinner("Đang kết nối SMTP..."):
                from utils.email_utils import test_smtp_connection
                ok, msg = test_smtp_connection(
                    email_cfg["address"], email_cfg["password"],
                    email_cfg.get("smtp_server", DEFAULT_SMTP_SERVER),
                )
                st.markdown(f'<div class="alert-box {"success" if ok else "error"}">{"✅" if ok else "❌"} {msg}</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(
        "📊 Test Google Sheets + Liệt kê Tab", use_container_width=True,
        disabled=not (sheets_cfg.get("credentials_path") or has_streamlit_secrets()),
    ):
        with st.spinner("Đang kết nối Google Sheets..."):
            try:
                from utils.sheets_utils import get_all_sheets_info
                tabs = get_all_sheets_info(sheets_cfg.get("credentials_path", ""), sheets_cfg.get("spreadsheet_id", ""))
                st.markdown(f'<div class="alert-box success">✅ Kết nối thành công! {len(tabs)} tab:</div>', unsafe_allow_html=True)
                for t in tabs:
                    st.markdown(f'<div class="status-row"><div class="dot green"></div><code>{t}</code></div>', unsafe_allow_html=True)
            except Exception as e:
                st.markdown(f'<div class="alert-box error">❌ Lỗi Sheets: {str(e)}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# ĐỔI MẬT KHẨU
# ─────────────────────────────────────────────────────────────────────────────

def render_password_section(config: dict) -> None:
    """Section đổi mật khẩu — gọi từ tab Hệ thống."""
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">ĐỔI MẬT KHẨU ĐĂNG NHẬP</div>', unsafe_allow_html=True)

    with st.expander("🔑 Đổi mật khẩu"):
        current_pw = st.text_input("Mật khẩu hiện tại", type="password", key="current_pw")
        new_pw     = st.text_input("Mật khẩu mới", type="password", key="new_pw")
        confirm_pw = st.text_input("Xác nhận mật khẩu mới", type="password", key="confirm_pw")

        if st.button("💾 Lưu mật khẩu mới", type="primary"):
            from pages.login import check_password, hash_password
            if not check_password(current_pw):
                st.markdown('<div class="alert-box error">❌ Mật khẩu hiện tại không đúng.</div>', unsafe_allow_html=True)
            elif len(new_pw) < 6:
                st.markdown('<div class="alert-box warning">⚠️ Mật khẩu mới phải có ít nhất 6 ký tự.</div>', unsafe_allow_html=True)
            elif new_pw != confirm_pw:
                st.markdown('<div class="alert-box warning">⚠️ Mật khẩu xác nhận không khớp.</div>', unsafe_allow_html=True)
            else:
                config.setdefault("auth", {})
                config["auth"]["password_hash"] = hash_password(new_pw)
                save_config(config)
                append_log("CONFIG_UPDATE", "Đổi mật khẩu đăng nhập", "warning")
                st.toast("Đã đổi mật khẩu thành công", icon="✅")