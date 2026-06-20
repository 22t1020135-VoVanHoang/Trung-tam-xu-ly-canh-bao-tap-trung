"""
SOC Alert Automation System
Hệ thống tự động hóa cảnh báo SOC - Chi nhánh Huế

Thay đổi so với bản cũ (Bước 7 — dọn dẹp cuối cùng):
  - Xóa import 'os' không dùng đến trong toàn file
  - Xóa 3 session_state khởi tạo nhưng không nơi nào dùng: config_saved,
    logs, last_email_data (rà soát toàn bộ pages/ xác nhận không tham chiếu)
  - Xóa load_config()/save_config()/CONFIG_FILE định nghĩa riêng → dùng
    utils.state_manager (đồng thời fix: save_config() cũ ghi file KHÔNG
    atomic, KHÔNG lock — là file JSON duy nhất trong hệ thống chưa được
    bảo vệ trước race condition)
  - Xóa get_logo_b64() duplicate với login.py → dùng utils.ui_helpers
  - settings_page.render() không cần nhận save_config làm tham số nữa —
    trang tự import từ state_manager, nhất quán với mọi trang khác
  - Thêm CSS .dot.blue (phòng hờ, dù hiện không trang nào dùng đến)
"""
import streamlit as st
from datetime import datetime

from utils.constants     import DEFAULT_BRANCH
from utils.state_manager import load_config
from utils.ui_helpers    import get_logo_b64

# ─── Khởi tạo session state TRƯỚC mọi thứ ───────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "last_active" not in st.session_state:
    st.session_state.last_active = None
if "page" not in st.session_state:
    st.session_state.page = "dashboard"

# ─── Kiểm tra đăng nhập sớm để biết trạng thái ─────────────────
from pages.login import is_logged_in, render_login
_logged_in = is_logged_in()

# Page config — sidebar collapsed khi chưa đăng nhập, expanded khi đã đăng nhập
st.set_page_config(
    page_title="SOC Alert Automation - HUE",
    page_icon="🔴",
    layout="wide",
    initial_sidebar_state="expanded" if _logged_in else "collapsed"
)

# Load custom CSS
def load_css(logged_in: bool = False):
    # CSS base luôn load
    sidebar_css = """
    /* Force sidebar luôn hiển thị – kể cả khi browser lưu trạng thái collapsed */
    [data-testid="stSidebar"],
    [data-testid="stSidebar"][aria-expanded="false"] {
        transform: translateX(0px) !important;
        min-width: 244px !important;
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        background-color: var(--surface) !important;
        border-right: 1px solid var(--border) !important;
    }
    section[data-testid="stSidebarContent"] {
        display: flex !important;
        visibility: visible !important;
        width: 100% !important;
    }
    [data-testid="stSidebar"] .stMarkdown h1,
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown h3 {
        color: var(--text) !important;
    }
    /* Ẩn nút đóng/mở sidebar – điều hướng luôn cố định */
    [data-testid="stSidebarCollapseButton"] { display: none !important; }
    [data-testid="collapsedControl"]        { display: none !important; }
    """ if logged_in else """
    /* Ẩn sidebar khi chưa đăng nhập */
    [data-testid="stSidebar"]        { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    """

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Thai:wght@300;400;500;600;700&display=swap');

    :root {{
        /* ── Màu semantic — mỗi màu có 2 sắc độ: bản "-dark" dùng cho viền/
           border (độ tương phản thấp, dịu mắt), bản chính dùng cho text/value
           (độ tương phản cao, dùng để truyền đạt thông tin).
           FIX B3: trước đây chỉ có bản dark được đặt tên biến; bản sáng hơn
           (vibrant) bị hardcode rải rác 10+ lần mỗi màu trên toàn dự án, và
           --blue hoàn toàn không tồn tại dù dùng 8+ lần. */
        --red: #E53E3E;
        --red-light: #FEB2B2;
        --red-dark: #9B2335;

        --orange-dark: #DD6B20;
        --orange: #ED8936;

        --green-dark: #276749;
        --green: #48BB78;
        --green-light: #9AE6B4;

        --blue-dark: #2B6CB0;
        --blue: #63B3ED;
        --blue-light: #90CDF4;

        /* ── Elevation: nền sáng dần theo độ "nổi" của lớp UI (đúng nguyên
           tắc dark-mode 2026 — KHÔNG dùng shadow đậm hơn để thể hiện độ nổi,
           dùng nền sáng hơn). 3 cấp: card → input/hover → dropdown/popover. */
        --bg: #0A0A0B;
        --surface: #111113;
        --surface2: #1A1A1E;
        --surface3: #232329;

        /* ── Bo góc thống nhất — trước đây lẫn lộn 2px/3px/4px không có quy
           tắc rõ ràng trên 12+ component khác nhau. */
        --radius: 6px;
        --radius-pill: 999px;
        --border: #2A2A30;
        --text: #E8E8EC;
        --text-muted: #6B6B78;
        --mono: 'IBM Plex Mono', monospace;
        --sans: 'IBM Plex Sans Thai', sans-serif;
    }}

    html, body, [class*="css"] {{
        font-family: var(--sans) !important;
        background-color: var(--bg) !important;
        color: var(--text) !important;
    }}

    .stApp {{
        background-color: var(--bg) !important;
    }}

    {sidebar_css}

    /* Main content */
    .main .block-container {{
        padding: 2rem 2.5rem !important;
        max-width: 1400px !important;
    }}

    /* Header */
    .sys-header {{
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 20px 24px;
        background: linear-gradient(135deg, var(--red-dark) 0%, #1a0505 100%);
        border: 1px solid var(--red-dark);
        border-radius: var(--radius);
        margin-bottom: 28px;
        position: relative;
        overflow: hidden;
    }}
    .sys-header::before {{
        content: '';
        position: absolute;
        top: 0; right: 0;
        width: 200px; height: 100%;
        background: repeating-linear-gradient(
            45deg,
            transparent,
            transparent 10px,
            rgba(229,62,62,0.05) 10px,
            rgba(229,62,62,0.05) 20px
        );
    }}
    .sys-header .badge {{
        background: var(--red);
        color: white;
        font-family: var(--mono);
        font-size: 10px;
        padding: 3px 8px;
        border-radius: var(--radius-pill);
        text-transform: uppercase;
        letter-spacing: 1px;
        animation: pulse-badge 2s infinite;
    }}
    @keyframes pulse-badge {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0.6; }}
    }}
    .sys-header h1 {{
        font-size: 1.4rem !important;
        font-weight: 700 !important;
        margin: 0 !important;
        color: white !important;
        letter-spacing: -0.5px;
    }}
    .sys-header .subtitle {{
        font-family: var(--mono);
        font-size: 11px;
        color: rgba(255,255,255,0.5);
        margin-top: 2px;
    }}

    /* Metric cards */
    .metric-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 24px;
    }}
    .metric-card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 16px 20px;
        position: relative;
    }}
    .metric-card.red {{ border-left: 3px solid var(--red); }}
    .metric-card.green {{ border-left: 3px solid var(--green-dark); }}
    .metric-card.orange {{ border-left: 3px solid var(--orange-dark); }}
    .metric-card.blue {{ border-left: 3px solid var(--blue-dark); }}

    .metric-card .label {{
        font-family: var(--mono);
        font-size: 10px;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 8px;
    }}
    .metric-card .value {{
        font-size: 2rem;
        font-weight: 700;
        line-height: 1;
    }}
    .metric-card.red .value {{ color: var(--red); }}
    .metric-card.green .value {{ color: var(--green); }}
    .metric-card.orange .value {{ color: var(--orange); }}
    .metric-card.blue .value {{ color: var(--blue); }}

    .metric-card .sub {{
        font-size: 11px;
        color: var(--text-muted);
        margin-top: 4px;
    }}

    /* Status indicators */
    .status-row {{
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px 16px;
        background: var(--surface2);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        margin-bottom: 6px;
        font-size: 13px;
    }}
    .dot {{
        width: 8px; height: 8px;
        border-radius: 50%;
        flex-shrink: 0;
    }}
    .dot.red {{ background: var(--red); box-shadow: 0 0 6px var(--red); }}
    .dot.green {{ background: var(--green); box-shadow: 0 0 6px var(--green); }}
    .dot.orange {{ background: var(--orange); box-shadow: 0 0 6px var(--orange); }}
    .dot.blue {{ background: var(--blue); box-shadow: 0 0 6px var(--blue); }}
    .dot.gray {{ background: var(--text-muted); }}

    /* Section headers */
    .section-label {{
        font-family: var(--mono);
        font-size: 11px;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 2px;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--border);
        margin-bottom: 16px;
    }}

    /* Buttons */
    .stButton > button {{
        background: var(--surface2) !important;
        color: var(--text) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important;
        font-family: var(--mono) !important;
        font-size: 12px !important;
        padding: 8px 18px !important;
        transition: all 0.15s !important;
    }}
    .stButton > button:hover {{
        border-color: var(--red) !important;
        color: var(--red) !important;
        background: rgba(229,62,62,0.05) !important;
    }}

    /* Primary button */
    .stButton > button[kind="primary"] {{
        background: var(--red) !important;
        color: white !important;
        border-color: var(--red) !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        background: var(--red-dark) !important;
        border-color: var(--red-dark) !important;
        color: white !important;
    }}

    /* Input fields — dark theme toàn diện */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    [data-baseweb="input"] input,
    [data-baseweb="base-input"] input,
    [data-baseweb="textarea"] textarea {{
        background: var(--surface2) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important;
        color: var(--text) !important;
        font-family: var(--sans) !important;
    }}
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus,
    [data-baseweb="input"] input:focus {{
        border-color: var(--red) !important;
        box-shadow: 0 0 0 1px var(--red) !important;
    }}
    /* Selectbox, date input, number input */
    [data-testid="stSelectbox"]   [data-baseweb="select"] > div,
    [data-testid="stDateInput"]   [data-baseweb="input"]  > div,
    [data-testid="stNumberInput"] [data-baseweb="input"]  > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div {{
        background: var(--surface2) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important;
        color: var(--text) !important;
    }}
    [data-testid="stDateInput"] input,
    [data-testid="stNumberInput"] input {{
        color: var(--text) !important;
        background: var(--surface2) !important;
    }}
    /* Dropdown popup menu — elevation cấp 3 (cao hơn input/surface2 1 bậc,
       đúng nguyên tắc dark-mode: độ nổi = nền sáng hơn, không phải shadow nặng) */
    [data-baseweb="popover"] ul,
    [data-baseweb="menu"] {{
        background: var(--surface3) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important;
    }}
    [data-baseweb="menu"] li {{
        color: var(--text) !important;
    }}
    [data-baseweb="menu"] li:hover {{
        background: rgba(229,62,62,0.1) !important;
        color: var(--red) !important;
    }}
    /* Multiselect tags */
    [data-testid="stMultiSelect"] [data-baseweb="tag"] {{
        background: rgba(229,62,62,0.15) !important;
        color: var(--red-light) !important;
        border: 1px solid rgba(229,62,62,0.3) !important;
        border-radius: var(--radius) !important;
    }}

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {{
        background: transparent !important;
        border-bottom: 1px solid var(--border) !important;
        gap: 0 !important;
    }}
    .stTabs [data-baseweb="tab"] {{
        background: transparent !important;
        color: var(--text-muted) !important;
        font-family: var(--mono) !important;
        font-size: 12px !important;
        padding: 10px 20px !important;
        border-bottom: 2px solid transparent !important;
        border-radius: 0 !important;
    }}
    .stTabs [aria-selected="true"] {{
        color: var(--red) !important;
        border-bottom-color: var(--red) !important;
        background: transparent !important;
    }}

    /* Expander */
    .streamlit-expanderHeader {{
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important;
        font-family: var(--mono) !important;
        font-size: 12px !important;
        color: var(--text) !important;
    }}

    /* Dataframe */
    .stDataFrame {{
        border: 1px solid var(--border) !important;
        border-radius: var(--radius) !important;
    }}

    /* Alert boxes */
    .alert-box {{
        padding: 14px 18px;
        border-radius: var(--radius);
        margin-bottom: 12px;
        font-size: 13px;
        border-left: 3px solid;
    }}
    .alert-box.error {{
        background: rgba(229,62,62,0.08);
        border-color: var(--red);
        color: var(--red-light);
    }}
    .alert-box.success {{
        background: rgba(39,103,73,0.15);
        border-color: var(--green-dark);
        color: var(--green-light);
    }}
    .alert-box.warning {{
        background: rgba(221,107,32,0.1);
        border-color: var(--orange-dark);
        color: #FBBF24;
    }}
    .alert-box.info {{
        background: rgba(43,108,176,0.1);
        border-color: var(--blue-dark);
        color: var(--blue-light);
    }}

    /* Timeline */
    .timeline-item {{
        display: flex;
        gap: 16px;
        padding: 12px 0;
        border-bottom: 1px solid var(--border);
    }}
    .timeline-time {{
        font-family: var(--mono);
        font-size: 11px;
        color: var(--text-muted);
        min-width: 80px;
        padding-top: 2px;
    }}
    .timeline-content {{ flex: 1; }}
    .timeline-title {{
        font-size: 13px;
        font-weight: 600;
        color: var(--text);
        margin-bottom: 3px;
    }}
    .timeline-desc {{
        font-size: 12px;
        color: var(--text-muted);
    }}

    /* Code blocks */
    .stCode {{
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
    }}

    /* ── Sidebar Navigation Items (B2 fix) ─────────────────────────────────
       FIX BUG NGHIÊM TRỌNG: bản cũ định nghĩa .nav-item / .nav-item.active
       nhưng sidebar render bằng st.button() → DOM thực tế là <button>, không
       có class "nav-item" nào tồn tại → CSS cũ KHÔNG BAO GIỜ match, người
       dùng không biết đang ở trang nào.
       Fix: style trực tiếp lên <button> thật trong sidebar. Trang đang active
       được Python gán type="primary" (xem app.py phần render sidebar) →
       button[kind="primary"] là selector THẬT mà Streamlit render ra DOM.
       Dùng border-left accent bar (pattern phổ biến ở Linear/Vercel sidebar)
       thay vì fill đặc để trông "premium" hơn theo nghiên cứu dark-mode 2026. */
    [data-testid="stSidebar"] .stButton > button {{
        width: 100% !important;
        display: flex !important;
        justify-content: flex-start !important;
        text-align: left !important;
        background: transparent !important;
        border: 1px solid transparent !important;
        border-left: 3px solid transparent !important;
        border-radius: var(--radius) !important;
        color: var(--text-muted) !important;
        font-family: var(--sans) !important;
        font-size: 13.5px !important;
        font-weight: 500 !important;
        padding: 10px 14px !important;
        margin-bottom: 2px !important;
        transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease !important;
    }}
    [data-testid="stSidebar"] .stButton > button p {{
        text-align: left !important;
    }}
    [data-testid="stSidebar"] .stButton > button:hover {{
        background: rgba(229,62,62,0.08) !important;
        color: var(--text) !important;
        border-left-color: rgba(229,62,62,0.35) !important;
    }}
    /* Trang đang active — type="primary" được gán động trong Python */
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {{
        background: rgba(229,62,62,0.12) !important;
        color: var(--red) !important;
        border-left: 3px solid var(--red) !important;
        font-weight: 700 !important;
    }}
    [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {{
        background: rgba(229,62,62,0.18) !important;
        color: var(--red) !important;
        border-left-color: var(--red) !important;
    }}

    /* Ẩn Deploy button, toolbar, header gap & Streamlit auto-nav */
    header[data-testid="stHeader"] {{
        background-color: var(--bg) !important;
        border-bottom: none !important;
        height: 0 !important;
        min-height: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
    }}
    /* Bù lại khoảng trống do header bị ẩn */
    .main .block-container {{ padding-top: 1.5rem !important; }}
    [data-testid="stToolbar"]    {{ display: none !important; }}
    [data-testid="stDecoration"] {{ display: none !important; }}
    .stDeployButton              {{ display: none !important; }}
    /* Ẩn Streamlit auto-detected page navigation */
    [data-testid="stSidebarNav"],
    [data-testid="stSidebarNavItems"],
    [data-testid="stSidebarNavSeparator"] {{ display: none !important; }}
    /* Ẩn nút đóng sidebar */
    [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
    [data-testid="collapsedControl"]        {{ display: none !important; }}
    #MainMenu {{ visibility: hidden !important; }}
    footer    {{ visibility: hidden !important; }}

    /* Config form */
    .config-section {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 20px;
        margin-bottom: 16px;
    }}
    .config-section h4 {{
        font-family: var(--mono);
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 2px;
        color: var(--text-muted);
        margin-bottom: 16px;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--border);
    }}

    /* Progress bar */
    .stProgress > div > div {{
        background-color: var(--red) !important;
    }}
    </style>
    """, unsafe_allow_html=True)

load_css(logged_in=_logged_in)

# ─── Nếu chưa đăng nhập: hiện form login rồi dừng ──────────────
if not _logged_in:
    render_login()
    st.stop()

# ─── Đã đăng nhập: load config và hiện app ──────────────────────

config = load_config()
_logo_b64 = get_logo_b64()

# ─── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    # ── Logo FPT Telecom ──
    if _logo_b64:
        st.markdown(f"""
        <div style="text-align:center; padding:16px 8px 12px;">
            <img src="data:image/png;base64,{_logo_b64}"
                 style="width:90px; border-radius:var(--radius);
                        box-shadow:0 2px 8px rgba(0,0,0,0.4);">
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div style="padding: 8px 0 20px; border-bottom: 1px solid var(--border); margin-bottom: 16px; text-align:center;">
        <div style="font-family: var(--mono); font-size: 10px; color: var(--text-muted); letter-spacing: 2px; text-transform: uppercase;">SOC SYSTEM</div>
        <div style="font-size: 1.1rem; font-weight: 700; color: var(--text); margin-top: 4px;">FPT Telecom AUTOMATION</div>
        <div style="font-family: var(--mono); font-size: 10px; color: var(--red); margin-top: 2px;">● ACTIVE</div>
    </div>
    """, unsafe_allow_html=True)

    pages = [
        ("📊", "Dashboard",      "dashboard"),
        ("📧", "Quét Email",     "email_scan"),
        ("📋", "Google Sheets",  "sheets"),
        ("📤", "Gửi Email",      "send_email"),
        ("📈", "Lịch sử BC",     "history"),
        ("⏱️", "Lịch trình",     "scheduler"),
        ("⚙️", "Cấu hình",       "settings"),
        ("📜", "Nhật ký",        "logs"),
    ]

    # FIX B2: biến `active` trước đây được tính nhưng KHÔNG BAO GIỜ dùng tới
    # (dead code) — CSS .nav-item.active cũng không match được DOM thật của
    # st.button(). Giờ dùng is_active để gán type="primary", và CSS mới ở
    # trên style trực tiếp lên button[kind="primary"] → active state hoạt
    # động thật trên giao diện.
    for icon, label, key in pages:
        is_active = st.session_state.page == key
        if st.button(
            f"{icon}  {label}",
            key=f"nav_{key}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            if not is_active:  # tránh rerun thừa khi bấm lại đúng trang hiện tại
                st.session_state.page = key
                st.rerun()

    st.markdown("---")
    if st.button("🚪 Đăng xuất", use_container_width=True):
        from pages.login import logout
        logout()
    st.markdown(f"""
    <div style="font-family: var(--mono); font-size: 10px; color: var(--text-muted); padding: 8px 0;">
        <div>BRANCH: {config.get('branch', DEFAULT_BRANCH)}</div>
        <div style="margin-top:4px;">BUILD: v1.0.0</div>
        <div style="margin-top:4px;">{datetime.now().strftime('%d/%m/%Y %H:%M')}</div>
    </div>
    """, unsafe_allow_html=True)

# ─── Import pages ───────────────────────────────────────────────
from pages import dashboard, email_scan, sheets_view, send_email, scheduler_page, settings_page, logs_page, history_page

page = st.session_state.page

if page == "dashboard":
    dashboard.render(config)
elif page == "email_scan":
    email_scan.render(config)
elif page == "sheets":
    sheets_view.render(config)
elif page == "send_email":
    send_email.render(config)
elif page == "scheduler":
    scheduler_page.render(config)
elif page == "settings":
    settings_page.render(config)
elif page == "history":
    history_page.render(config)
elif page == "logs":
    logs_page.render()