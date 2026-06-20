"""
Lịch sử Báo cáo — xem lại các email giải trình đã gửi, lọc theo ngày

Thay đổi so với bản cũ:
  - Xóa HISTORY_FILE hardcode → dùng utils.constants.HISTORY_FILE
"""
import streamlit as st
import json
from datetime import datetime

import pandas as pd

from utils.constants import HISTORY_FILE


def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            content = HISTORY_FILE.read_text(encoding="utf-8").strip()
            return json.loads(content) if content else []
        except Exception:
            return []
    return []


def render(config: dict):
    st.markdown("""
    <div class="sys-header">
        <div>
            <h1>📈 Lịch sử Báo cáo</h1>
            <div class="subtitle">Xem lại các email giải trình đã gửi, lọc theo ngày</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    history = load_history()

    col_main, col_side = st.columns([3, 1])

    # ── Sidebar bộ lọc + thống kê ─────────────────────────────────────────────
    with col_side:
        st.markdown('<div class="section-label">BỘ LỌC</div>', unsafe_allow_html=True)

        filter_date   = st.date_input("Lọc theo ngày gửi", value=None, format="DD/MM/YYYY")
        filter_status = st.selectbox("Trạng thái", ["Tất cả", "success", "error"])

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Xóa bộ lọc", use_container_width=True):
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        total        = len(history)
        success_cnt  = sum(1 for h in history if h.get("status") == "success")
        total_rec    = sum(h.get("total_records", 0) for h in history)

        st.markdown(f"""
        <div class="metric-card blue"   style="padding:14px; margin-bottom:8px;">
            <div class="label">Tổng báo cáo</div>
            <div class="value">{total}</div>
        </div>
        <div class="metric-card green"  style="padding:14px; margin-bottom:8px;">
            <div class="label">Gửi thành công</div>
            <div class="value">{success_cnt}</div>
        </div>
        <div class="metric-card orange" style="padding:14px; margin-bottom:8px;">
            <div class="label">Tổng bản ghi</div>
            <div class="value">{total_rec}</div>
        </div>
        """, unsafe_allow_html=True)

    # ── Danh sách báo cáo ─────────────────────────────────────────────────────
    with col_main:
        st.markdown('<div class="section-label">DANH SÁCH BÁO CÁO ĐÃ GỬI</div>', unsafe_allow_html=True)

        # Áp dụng bộ lọc
        filtered = history
        if filter_date:
            date_str = filter_date.strftime("%d/%m/%Y")
            filtered = [
                h for h in filtered
                if date_str in h.get("sent_at", "") or date_str == h.get("report_date", "")
            ]
        if filter_status != "Tất cả":
            filtered = [h for h in filtered if h.get("status") == filter_status]

        if not filtered:
            st.markdown("""
            <div class="alert-box info">
                Không có báo cáo nào phù hợp. Email giải trình sẽ được lưu tự động sau khi gửi thành công.
            </div>
            """, unsafe_allow_html=True)
            return

        for entry in filtered:
            status       = entry.get("status", "success")
            icon         = "✅" if status == "success" else "❌"
            indicators   = entry.get("red_indicators", [])
            explanations = entry.get("explanations", [])
            total_rec_e  = entry.get("total_records", 0)
            filled       = sum(1 for e in explanations if e.get("count", 0) > 0)

            label = (
                f"{icon}  {entry.get('sent_at', '')}  ·  "
                f"Ngày BC: {entry.get('report_date') or '—'}  ·  "
                f"{len(indicators)} chỉ số đỏ  ·  {total_rec_e} bản ghi"
            )
            with st.expander(label):
                c1, c2 = st.columns([3, 2])

                with c1:
                    st.markdown(f"""
                    <div class="config-section" style="padding:14px;">
                        <h4>THÔNG TIN GỬI</h4>
                        <div style="font-size:13px; line-height:2.2;">
                            <div>📅 Ngày báo cáo : <strong>{entry.get('report_date') or '—'}</strong></div>
                            <div>🕐 Gửi lúc      : <strong>{entry.get('sent_at','—')}</strong></div>
                            <div>📤 Gửi đến      : <strong>{entry.get('to_address','—')}</strong></div>
                            <div>🏢 Chi nhánh    : <strong>{entry.get('branch','—')}</strong></div>
                            <div style="margin-top:4px; font-size:12px; color:var(--text-muted);">
                                {entry.get('subject','—')}
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with c2:
                    st.markdown(f"""
                    <div class="metric-card red"    style="padding:14px; margin-bottom:8px;">
                        <div class="label">Chỉ số đỏ</div>
                        <div class="value">{len(indicators)}</div>
                    </div>
                    <div class="metric-card green"  style="padding:14px; margin-bottom:8px;">
                        <div class="label">Đã giải trình</div>
                        <div class="value">{filled}</div>
                    </div>
                    <div class="metric-card blue"   style="padding:14px;">
                        <div class="label">Tổng bản ghi</div>
                        <div class="value">{total_rec_e}</div>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown('<div class="section-label" style="margin-top:12px;">CHI TIẾT CHỈ SỐ</div>', unsafe_allow_html=True)
                for exp in explanations:
                    has_data = exp.get("count", 0) > 0
                    dot      = "green" if has_data else "orange"
                    st.markdown(f"""
                    <div class="status-row">
                        <div class="dot {dot}"></div>
                        <span style="font-size:13px; font-weight:500;">{exp.get('indicator','')}</span>
                        <span style="color:var(--text-muted); font-size:12px; margin-left:8px;">
                            → <code style="font-size:11px;">{exp.get('sheet_name','')}</code>
                        </span>
                        <span style="margin-left:auto; font-family:var(--mono); font-size:11px;
                            color:{'var(--green)' if has_data else 'var(--orange)'};">
                            {exp.get('count', 0)} dòng
                        </span>
                    </div>
                    """, unsafe_allow_html=True)

        # ── Export CSV ────────────────────────────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        flat = [
            {
                "Ngày gửi":   entry.get("sent_at", ""),
                "Ngày BC":    entry.get("report_date", ""),
                "Chi nhánh":  entry.get("branch", ""),
                "Gửi đến":    entry.get("to_address", ""),
                "Chỉ số":     exp.get("indicator", ""),
                "Tab Sheet":  exp.get("sheet_name", ""),
                "Số dòng":    exp.get("count", 0),
                "Trạng thái": entry.get("status", ""),
            }
            for entry in filtered
            for exp in entry.get("explanations", [])
        ]
        if flat:
            csv = pd.DataFrame(flat).to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇️ Xuất CSV",
                data=csv,
                file_name=f"history_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )