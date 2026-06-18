"""
pages/login.py
Trang đăng nhập — xác thực mật khẩu, quản lý phiên đăng nhập.

Thay đổi so với bản cũ:
  - Xóa CONFIG_FILE / DEFAULT_PASSWORD định nghĩa riêng → dùng utils.constants
  - Xóa _get_logo_b64() duplicate với app.py → dùng utils.ui_helpers.get_logo_b64()
  - Magic number "8 giờ" (timeout phiên) → SESSION_TIMEOUT_HOURS trong constants
"""
import streamlit as st
import hashlib
import json
from datetime import datetime, timedelta

from utils.constants  import CONFIG_FILE, DEFAULT_PASSWORD, SESSION_TIMEOUT_HOURS
from utils.ui_helpers import get_logo_b64


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
        if elapsed > timedelta(hours=SESSION_TIMEOUT_HOURS):
            st.session_state.authenticated = False
            return False
    st.session_state.last_active = datetime.now()
    return True


def logout():
    st.session_state.authenticated = False
    st.session_state.last_active = None
    st.rerun()


def render_login():
    """Màn hình đăng nhập — thiết kế lại gọn, cân đối."""
    st.markdown("""
    <style>
    .block-container { max-width: 100% !important; padding: 0 !important; }
    @keyframes pulse-badge {
        0%, 100% { opacity: 1; }
        50%       { opacity: 0.6; }
    }
    </style>
    """, unsafe_allow_html=True)

    # Căn giữa theo chiều ngang
    _, col, _ = st.columns([1, 1.1, 1])
    with col:
        st.markdown("<div style='height:48px'></div>", unsafe_allow_html=True)

        # ── Logo ──
        _b64 = get_logo_b64()
        if _b64:
            st.markdown(
                f'''<div style="text-align:center; margin-bottom:18px;">
                <img src="data:image/png;base64,{_b64}"
                     style="width:110px; border-radius:12px;
                            box-shadow:0 4px 24px rgba(0,0,0,0.55);">
                </div>''',
                unsafe_allow_html=True,
            )

        # ── Card tiêu đề ──
        st.markdown("""
        <div style="background:var(--surface); border:1px solid var(--border);
                    border-top:3px solid var(--red); border-radius:6px;
                    padding:28px 32px 20px; text-align:center; margin-bottom:14px;">
            <div style="display:inline-block; background:var(--red); color:white;
                        font-family:var(--mono); font-size:10px; padding:3px 12px;
                        border-radius:2px; letter-spacing:2px; text-transform:uppercase;
                        margin-bottom:14px; animation:pulse-badge 2s infinite;">
                SOC SYSTEM
            </div>
            <div style="font-size:1.25rem; font-weight:700; color:var(--text);
                        letter-spacing:-0.3px; margin-bottom:6px;">
                FPT Telecom AUTOMATION
            </div>
            <div style="font-family:var(--mono); font-size:11px; color:var(--text-muted);">
                Chi nhánh Huế &nbsp;·&nbsp; Xác thực để tiếp tục
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Form đăng nhập ──
        password = st.text_input(
            "🔑 Mật khẩu",
            type="password",
            placeholder="Nhập mật khẩu...",
            key="login_password",
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
                    '<div class="alert-box error" style="margin-top:8px;">' +
                    '❌ Mật khẩu không đúng.</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("""
        <div style="text-align:center; margin-top:20px;
                    font-family:var(--mono); font-size:10px; color:var(--text-muted);">
            FPT Telecom · Chi nhánh Huế · SOC Automation v1.0
        </div>
        """, unsafe_allow_html=True)