"""
Google Sheets viewer — Smart auto-refresh (không dùng time.sleep)
"""
import streamlit as st
import json
from pathlib import Path
from datetime import datetime

STATE_FILE = Path(__file__).parent.parent / "config" / "state.json"

DEFAULT_STATE = {"red_indicators": [], "report_date": None}

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


def _load_sheets_data(credentials_path, spreadsheet_id, indicators):
    from utils.sheets_utils import collect_all_explanations
    data = collect_all_explanations(credentials_path, spreadsheet_id, indicators, "")
    st.session_state["sheets_cache"] = data
    st.session_state["sheets_loaded_at"] = datetime.now().strftime("%H:%M:%S")
    st.session_state["sheets_indicators_loaded"] = indicators[:]


def render(config: dict):
    sheets_cfg     = config.get("google_sheets", {})
    spreadsheet_id = sheets_cfg.get("spreadsheet_id", "")
    creds_path     = sheets_cfg.get("credentials_path", "")
    sheet_url      = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

    state          = load_state()
    red_indicators = state.get("red_indicators", [])

    st.markdown("""
    <div class="sys-header">
      <div>
        <h1>📋 Google Sheets – Giải trình</h1>
        <div class="subtitle">Dữ liệu tự động cập nhật theo Google Sheets</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    col_info, col_open = st.columns([5, 1])
    with col_info:
        last_load = st.session_state.get("sheets_loaded_at", "—")
        st.markdown(f"""
        <div class="alert-box info" style="display:flex; align-items:center;
          justify-content:space-between; padding:10px 16px;">
          <span>📊 Spreadsheet ID:
            <code style="font-family:var(--mono); font-size:11px;">{spreadsheet_id}</code>
          </span>
          <span style="font-family:var(--mono); font-size:11px; color:var(--text-muted);">
            Cập nhật lúc: {last_load}
          </span>
        </div>
        """, unsafe_allow_html=True)
    with col_open:
        st.markdown(
            f'<a href="{sheet_url}" target="_blank" style="display:block; text-align:center; '
            f'padding:10px; background:var(--surface2); border:1px solid var(--border); '
            f'border-radius:3px; color:var(--text); font-family:var(--mono); font-size:12px; '
            f'text-decoration:none;">Mở Sheet ↗</a>',
            unsafe_allow_html=True,
        )

    col_main, col_side = st.columns([3, 1])

    with col_side:
        st.markdown('<div class="section-label">TÙY CHỌN</div>', unsafe_allow_html=True)

        from utils.sheets_utils import INDICATOR_TO_SHEET
        all_indicators = list(INDICATOR_TO_SHEET.keys())
        selected = st.multiselect(
            "Chọn chỉ số cần xem",
            all_indicators,
            default=red_indicators if red_indicators else [],
        )

        st.markdown("<br>", unsafe_allow_html=True)

        auto_refresh = st.toggle("🔄 Tự động cập nhật", value=False)
        refresh_sec  = st.selectbox(
            "Kiểm tra mỗi",
            [30, 60, 120, 300],
            index=1,
            format_func=lambda x: f"{x} giây",
        )

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Tải lại ngay", type="primary", use_container_width=True):
            _load_sheets_data(creds_path, spreadsheet_id, selected or red_indicators)
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("👁️ Xem trước Email", use_container_width=True):
            st.session_state["preview_from_sheets"] = True
            st.session_state.page = "send_email"
            st.session_state.preview_email = True
            st.rerun()

        if auto_refresh:
            from streamlit_autorefresh import st_autorefresh
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(
                f'<div class="alert-box info" style="font-size:12px; text-align:center;">'
                f'🔄 Tự động tải lại mỗi <strong>{refresh_sec}s</strong></div>',
                unsafe_allow_html=True,
            )
            # st_autorefresh: không block UI, không tốn tài nguyên
            refresh_count = st_autorefresh(interval=refresh_sec * 1000, key="sheets_autorefresh")
            last_count = st.session_state.get("sheets_last_refresh_count", -1)
            if refresh_count > last_count:
                st.session_state["sheets_last_refresh_count"] = refresh_count
                try:
                    _load_sheets_data(creds_path, spreadsheet_id, selected or red_indicators)
                except Exception:
                    pass

    with col_main:
        st.markdown('<div class="section-label">NỘI DUNG GIẢI TRÌNH</div>', unsafe_allow_html=True)

        indicators_to_show = selected or red_indicators

        if not indicators_to_show:
            st.markdown(
                '<div class="alert-box info">Chọn chỉ số bên phải hoặc quét email '
                'trước để xác định chỉ số đỏ.</div>',
                unsafe_allow_html=True,
            )
            return

        has_creds = bool(creds_path) or _has_streamlit_secrets()
        if not has_creds:
            st.markdown(
                '<div class="alert-box warning">⚠️ Chưa cấu hình Google Service Account. '
                'Vào <strong>Cấu hình → Google Sheets</strong> để thiết lập.</div>',
                unsafe_allow_html=True,
            )
            return

        cached_indicators = st.session_state.get("sheets_indicators_loaded", [])
        needs_reload = (
            "sheets_cache" not in st.session_state
            or sorted(cached_indicators) != sorted(indicators_to_show)
        )

        if needs_reload:
            with st.spinner("Đang tải dữ liệu từ Google Sheets..."):
                try:
                    _load_sheets_data(creds_path, spreadsheet_id, indicators_to_show)
                except Exception as e:
                    st.markdown(
                        f'<div class="alert-box error">❌ Lỗi kết nối Sheets: {str(e)}</div>',
                        unsafe_allow_html=True,
                    )
                    return

        data = st.session_state.get("sheets_cache", [])
        _render_sheets_data(data)


def _has_streamlit_secrets() -> bool:
    try:
        import streamlit as st
        return hasattr(st, 'secrets') and 'google_service_account' in st.secrets
    except Exception:
        return False


def _render_sheets_data(data: list):
    import pandas as pd

    if not data:
        st.markdown(
            '<div class="alert-box info">Không có dữ liệu để hiển thị.</div>',
            unsafe_allow_html=True,
        )
        return

    for item in data:
        has_data  = item["count"] > 0
        has_error = bool(item.get("error"))
        dot_color = "green" if has_data else ("red" if has_error else "orange")
        row_label = f"{item['count']} dòng" if has_data else ("Lỗi" if has_error else "Chưa có dữ liệu")

        st.markdown(f"""
        <div class="status-row" style="margin-bottom:6px;">
          <div class="dot {dot_color}"></div>
          <strong style="font-size:14px; color:var(--text);">{item['indicator']}</strong>
          <span style="color:var(--text-muted); font-size:12px; margin-left:8px;">
            → tab: <code style="font-size:11px;">{item['sheet_name']}</code>
          </span>
          <span style="margin-left:auto; font-family:var(--mono); font-size:11px;
            color:{'#48BB78' if has_data else ('#E53E3E' if has_error else '#ED8936')};">
            {row_label}
          </span>
        </div>
        """, unsafe_allow_html=True)

        if has_error:
            st.markdown(
                f'<div class="alert-box error" style="margin-bottom:16px;">❌ {item["error"]}</div>',
                unsafe_allow_html=True,
            )
            continue

        if not item.get("rows"):
            st.markdown(
                f'<div class="alert-box warning" style="margin-bottom:16px;">'
                f'⚠️ Tab "<strong>{item["sheet_name"]}</strong>" chưa có dữ liệu. '
                f'Nhân viên chưa điền hoặc tên tab không khớp.</div>',
                unsafe_allow_html=True,
            )
            continue

        rows    = item["rows"]
        headers = item.get("headers") or list(rows[0].keys())
        useful = [
            h for h in headers
            if any(str(r.get(h, "")).strip() for r in rows)
        ]
        if not useful:
            useful = headers

        df = pd.DataFrame(rows)[useful]
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.markdown("<br>", unsafe_allow_html=True)