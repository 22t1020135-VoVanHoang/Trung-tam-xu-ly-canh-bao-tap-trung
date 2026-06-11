"""Login page"""
import streamlit as st
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta

CONFIG_FILE = Path(__file__).parent.parent / "config" / "settings.json"

DEFAULT_PASSWORD = "soc2026"


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def load_auth_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg.get("auth", {})
        except Exception:
            pass
    return {}


def check_password(input_password: str) -> bool:
    auth = load_auth_config()
    stored_hash = auth.get("password_hash", "")
    if not stored_hash:
        return input_password == DEFAULT_PASSWORD
    return hash_password(input_password) == stored_hash


def is_logged_in() -> bool:
    if not st.session_state.get("authenticated"):
        return False
    last_active = st.session_state.get("last_active")
    if last_active:
        elapsed = datetime.now() - last_active
        if elapsed > timedelta(hours=8):
            st.session_state.authenticated = False
            return False
    st.session_state.last_active = datetime.now()
    return True


def logout():
    st.session_state.authenticated = False
    st.session_state.last_active = None
    st.rerun()


def render_login():
    """
    Hiển thị màn hình đăng nhập.
    Lưu ý: CSS ẩn sidebar đã được xử lý trong app.py (load_css(logged_in=False))
    Hàm này CHỈ render form login, không cần inject CSS sidebar nữa.
    """
    st.markdown("""
    <style>
    .block-container { max-width: 100% !important; padding: 2rem !important; }
    .login-container {
        max-width: 400px;
        margin: 80px auto 0;
        padding: 40px;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 6px;
    }
    .login-logo { text-align: center; margin-bottom: 32px; }
    .login-logo .badge {
        display: inline-block;
        background: var(--red);
        color: white;
        font-family: var(--mono);
        font-size: 10px;
        padding: 4px 10px;
        border-radius: 2px;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-bottom: 12px;
        animation: pulse-badge 2s infinite;
    }
    .login-logo h2 { font-size: 1.4rem; font-weight: 700; color: var(--text); margin: 0 0 4px; }
    .login-logo .sub { font-family: var(--mono); font-size: 11px; color: var(--text-muted); }
    </style>

    <div class="login-container">
        <div class="login-logo">
            <div class="badge">SOC SYSTEM</div>
            <h2>HUÊ AUTOMATION</h2>
            <div class="sub">Chi nhánh Huế · Xác thực để tiếp tục</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        password = st.text_input(
            "Mật khẩu",
            type="password",
            placeholder="Nhập mật khẩu...",
            key="login_password"
        )

        if st.button("🔐 Đăng nhập", type="primary", use_container_width=True):
            if check_password(password):
                st.session_state.authenticated  = True
                st.session_state.last_active    = datetime.now()
                st.session_state.just_logged_in = True
                st.session_state.dash_ready     = False
                st.rerun()
            else:
                st.markdown(
                    '<div class="alert-box error">❌ Mật khẩu không đúng.</div>',
                    unsafe_allow_html=True
                )