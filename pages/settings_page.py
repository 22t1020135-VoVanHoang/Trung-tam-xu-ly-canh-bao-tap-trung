"""Settings page"""
import streamlit as st
import json
from pathlib import Path

def render(config: dict, save_config):
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
            imap_server = st.text_input("IMAP Server", value=email_cfg.get("imap_server", "imap.gmail.com"))
            smtp_server = st.text_input("SMTP Server", value=email_cfg.get("smtp_server", "smtp.gmail.com"))
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("""
        <div class="alert-box info" style="font-size:12px;">
            💡 <strong>Gmail:</strong> Dùng <strong>App Password</strong> (Tài khoản Google → Bảo mật → Xác minh 2 bước → Mật khẩu ứng dụng).
        </div>
        """, unsafe_allow_html=True)

        if st.button("💾 Lưu cấu hình Email", type="primary"):
            config["email"] = {"address": address, "password": password,
                               "imap_server": imap_server, "smtp_server": smtp_server}
            save_config(config)
            st.markdown('<div class="alert-box success">✅ Đã lưu cấu hình email!</div>', unsafe_allow_html=True)

    with tab2:
        st.markdown("<br>", unsafe_allow_html=True)
        sheets_cfg = config.get("google_sheets", {})

        st.markdown('<div class="config-section"><h4>GOOGLE SHEETS</h4>', unsafe_allow_html=True)
        spreadsheet_id = st.text_input(
            "Spreadsheet ID",
            value=sheets_cfg.get("spreadsheet_id", "11A4TuYjE3iLU92IvYK3UlOclB2baOd7Yawd4LyGrsW8"),
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
            st.markdown('<div class="alert-box success">✅ Đã lưu cấu hình Google Sheets!</div>', unsafe_allow_html=True)



    with tab3:
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<div class="config-section"><h4>THÔNG TIN HỆ THỐNG</h4>', unsafe_allow_html=True)
            branch     = st.text_input("Chi nhánh", value=config.get("branch", "HUE"))
            soc_sender = st.text_input("Tên người gửi SOC", value=config.get("soc_sender_name", "SOC Canh bao"))
            st.markdown("</div>", unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="config-section"><h4>LỊCH TRÌNH</h4>', unsafe_allow_html=True)
            sched   = config.get("scheduler", {})
            scan_min = st.number_input("Quét mỗi (phút)", 5, 120, sched.get("scan_interval_minutes", 30))
            reply_h  = st.number_input("Giờ gửi tự động", 0, 23, sched.get("reply_deadline_hour", 11))
            reply_m  = st.number_input("Phút gửi tự động", 0, 59, sched.get("reply_deadline_minute", 45))
            st.markdown("</div>", unsafe_allow_html=True)

        if st.button("💾 Lưu cài đặt hệ thống", type="primary"):
            config["branch"]           = branch
            config["soc_sender_name"]  = soc_sender
            config["scheduler"]        = {"scan_interval_minutes": scan_min,
                                           "reply_deadline_hour": reply_h,
                                           "reply_deadline_minute": reply_m}
            save_config(config)
            st.markdown('<div class="alert-box success">✅ Đã lưu cài đặt!</div>', unsafe_allow_html=True)

        render_password_section(config, save_config)
    with tab4:
        st.markdown("<br>", unsafe_allow_html=True)
        email_cfg  = config.get("email", {})
        sheets_cfg = config.get("google_sheets", {})

        st.markdown('<div class="section-label">KIỂM TRA KẾT NỐI</div>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔌 Test IMAP", use_container_width=True, disabled=not email_cfg.get("address")):
                with st.spinner("Đang kết nối IMAP..."):
                    from utils.email_utils import test_imap_connection
                    ok, msg = test_imap_connection(email_cfg["address"], email_cfg["password"],
                                                   email_cfg.get("imap_server", "imap.gmail.com"))
                    st.markdown(f'<div class="alert-box {"success" if ok else "error"}">{"✅" if ok else "❌"} {msg}</div>', unsafe_allow_html=True)
        with col2:
            if st.button("📤 Test SMTP", use_container_width=True, disabled=not email_cfg.get("address")):
                with st.spinner("Đang kết nối SMTP..."):
                    from utils.email_utils import test_smtp_connection
                    ok, msg = test_smtp_connection(email_cfg["address"], email_cfg["password"],
                                                   email_cfg.get("smtp_server", "smtp.gmail.com"))
                    st.markdown(f'<div class="alert-box {"success" if ok else "error"}">{"✅" if ok else "❌"} {msg}</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📊 Test Google Sheets + Liệt kê Tab", use_container_width=True,
                     disabled=not (sheets_cfg.get("credentials_path") or _has_streamlit_secrets())):
            with st.spinner("Đang kết nối Google Sheets..."):
                try:
                    from utils.sheets_utils import get_all_sheets_info
                    tabs = get_all_sheets_info(sheets_cfg.get("credentials_path",""),
                                               sheets_cfg.get("spreadsheet_id",""))
                    st.markdown(f'<div class="alert-box success">✅ Kết nối thành công! {len(tabs)} tab:</div>', unsafe_allow_html=True)
                    for t in tabs:
                        st.markdown(f'<div class="status-row"><div class="dot green"></div><code>{t}</code></div>', unsafe_allow_html=True)
                except Exception as e:
                    st.markdown(f'<div class="alert-box error">❌ Lỗi Sheets: {str(e)}</div>', unsafe_allow_html=True)


def _has_streamlit_secrets() -> bool:
    try:
        import streamlit as st
        return hasattr(st, "secrets") and "google_service_account" in st.secrets
    except Exception:
        return False


def render_password_section(config: dict, save_config):
    """Section đổi mật khẩu — gọi từ tab Hệ thống."""
    import hashlib
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">ĐỔI MẬT KHẨU ĐĂNG NHẬP</div>', unsafe_allow_html=True)

    with st.expander("🔑 Đổi mật khẩu"):
        current_pw = st.text_input("Mật khẩu hiện tại", type="password", key="current_pw")
        new_pw     = st.text_input("Mật khẩu mới", type="password", key="new_pw")
        confirm_pw = st.text_input("Xác nhận mật khẩu mới", type="password", key="confirm_pw")

        if st.button("💾 Lưu mật khẩu mới", type="primary"):
            from pages.login import check_password, hash_password, DEFAULT_PASSWORD
            if not check_password(current_pw):
                st.markdown('<div class="alert-box error">❌ Mật khẩu hiện tại không đúng.</div>', unsafe_allow_html=True)
            elif len(new_pw) < 6:
                st.markdown('<div class="alert-box warning">⚠️ Mật khẩu mới phải có ít nhất 6 ký tự.</div>', unsafe_allow_html=True)
            elif new_pw != confirm_pw:
                st.markdown('<div class="alert-box warning">⚠️ Mật khẩu xác nhận không khớp.</div>', unsafe_allow_html=True)
            else:
                if "auth" not in config:
                    config["auth"] = {}
                config["auth"]["password_hash"] = hash_password(new_pw)
                save_config(config)
                st.markdown('<div class="alert-box success">✅ Đã đổi mật khẩu thành công!</div>', unsafe_allow_html=True)