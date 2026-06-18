"""
Google Sheets utilities
"""
from pathlib import Path

from utils.constants import DEFAULT_SPREADSHEET_ID

try:
    import gspread
    from gspread.exceptions import WorksheetNotFound, SpreadsheetNotFound
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    class WorksheetNotFound(Exception): pass
    class SpreadsheetNotFound(Exception): pass


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Mapping chỉ số đỏ → tên tab CHÍNH XÁC trong Google Sheets
# Phải đồng bộ với KPI_INDICATORS trong email_utils.py
# Tab thực tế đã kiểm tra ngày 15/06/2026: 8 tabs
INDICATOR_TO_SHEET = {
    # ── 5 chỉ số cốt lõi ─────────────────────────────────────────────────────
    "CSAT 1":               "CSAT 1",
    "Checklist lặp ≥ 3":   "Checklist lặp ≥ 3",
    "PTC ≥ 72h":            "PTC ≥ 72h",
    "Checklist ≥24h":       "Checklist ≥24h",
    "Yêu Cầu RM":           "Suy hao cao yêu cầu huỷ",

    # ── 2 chỉ số bổ sung — đã có tab trong Sheets ────────────────────────────
    "Nguyên nhân tồn TKM":  "Nguyên nhân tồn TKM",
    "Rời mạng CLDV":        "Rời mạng CLDV",

    # ── 2 chỉ số chưa có tab — bỏ comment khi đã tạo tab trong Sheets ────────
    # "Yêu cầu khiếu nại":  "???",   # ← điền tên tab sau khi tạo
    # "Yêu cầu ≥48h":       "???",   # ← điền tên tab sau khi tạo
}


def _check_gspread():
    if not GSPREAD_AVAILABLE:
        raise ImportError(
            "Thư viện gspread chưa cài trong môi trường hiện tại.\n"
            "Chạy: pip install gspread google-auth"
        )


def get_gspread_client(credentials_path: str = None):
    _check_gspread()

    try:
        import streamlit as st
        if hasattr(st, "secrets") and "google_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(
                dict(st.secrets["google_service_account"]), scopes=SCOPES
            )
            return gspread.authorize(creds)
    except Exception:
        pass

    if credentials_path:
        p = Path(credentials_path)
        if not p.exists():
            raise FileNotFoundError(
                f"Không tìm thấy file Service Account: '{credentials_path}'"
            )
        creds = Credentials.from_service_account_file(str(p), scopes=SCOPES)
        return gspread.authorize(creds)

    raise ValueError(
        "Chưa cấu hình Service Account JSON.\n"
        "Vào Cấu hình → Google Sheets → điền đường dẫn file service-account.json"
    )


def get_sheet_data(credentials_path: str, spreadsheet_id: str, sheet_name: str) -> dict:
    client = get_gspread_client(credentials_path)
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(sheet_name)
    data = ws.get_all_values()

    if not data:
        return {"headers": [], "rows": []}

    raw_headers = data[0]
    headers = []
    seen = {}
    for i, h in enumerate(raw_headers):
        h = h.strip() if h.strip() else f"Col_{i}"
        if h in seen:
            seen[h] += 1
            h = f"{h}_{seen[h]}"
        else:
            seen[h] = 0
        headers.append(h)

    rows = []
    for row in data[1:]:
        padded = row + [""] * (len(headers) - len(row))
        if any(cell.strip() for cell in padded):
            rows.append(dict(zip(headers, padded)))

    return {"headers": headers, "rows": rows}


def get_all_sheets_info(credentials_path: str, spreadsheet_id: str) -> list:
    client = get_gspread_client(credentials_path)
    sh = client.open_by_key(spreadsheet_id)
    return [ws.title for ws in sh.worksheets()]


def diagnose_sheets(credentials_path: str, spreadsheet_id: str) -> dict:
    try:
        actual_tabs = get_all_sheets_info(credentials_path, spreadsheet_id)
        mapped_tabs = list(INDICATOR_TO_SHEET.values())
        missing     = [t for t in mapped_tabs if t not in actual_tabs]
        ok          = [t for t in mapped_tabs if t in actual_tabs]
        return {
            "actual_tabs":  actual_tabs,
            "mapped_tabs":  mapped_tabs,
            "missing_tabs": missing,
            "ok_tabs":      ok,
            "error":        None,
        }
    except Exception as e:
        return {
            "actual_tabs": [], "mapped_tabs": [], "missing_tabs": [], "ok_tabs": [],
            "error": str(e),
        }


def extract_explanation_from_sheet(
    credentials_path: str,
    spreadsheet_id: str,
    indicator: str,
    report_date: str = None,
) -> dict:
    sheet_name = INDICATOR_TO_SHEET.get(indicator, indicator)
    try:
        result   = get_sheet_data(credentials_path, spreadsheet_id, sheet_name)
        headers  = result["headers"]
        all_rows = result["rows"]

        filtered_rows = all_rows
        if report_date and all_rows:
            date_filtered = [
                row for row in all_rows
                if any(report_date in str(v) for v in row.values())
            ]
            if date_filtered:
                filtered_rows = date_filtered

        return {
            "sheet_name": sheet_name,
            "indicator":  indicator,
            "headers":    headers,
            "rows":       filtered_rows,
            "count":      len(filtered_rows),
            "error":      None,
        }

    except WorksheetNotFound:
        try:
            actual = get_all_sheets_info(credentials_path, spreadsheet_id)
            hint = f"Tab thực tế: {actual}"
        except Exception:
            hint = ""
        return {
            "sheet_name": sheet_name, "indicator": indicator,
            "headers": [], "rows": [], "count": 0,
            "error": f"Không tìm thấy tab '{sheet_name}'. {hint}",
        }
    except Exception as e:
        return {
            "sheet_name": sheet_name, "indicator": indicator,
            "headers": [], "rows": [], "count": 0,
            "error": str(e),
        }


def collect_all_explanations(
    credentials_path: str,
    spreadsheet_id: str,
    red_indicators: list,
    report_date: str = None,
) -> list:
    return [
        extract_explanation_from_sheet(credentials_path, spreadsheet_id, ind, report_date)
        for ind in red_indicators
    ]


def build_email_html(report_date: str, branch: str, explanations: list, original_body: str = "") -> str:
    rows_html = ""
    for exp in explanations:
        status_icon  = "✅" if exp["count"] > 0 else "⚠️"
        status_color = "#27AE60" if exp["count"] > 0 else "#E67E22"
        status_text  = "Đã có" if exp["count"] > 0 else "Chưa có"
        rows_html += f"""
        <tr>
            <td style="padding:12px 16px; border-bottom:1px solid #F0F0F0;">
                <span style="display:inline-block; width:8px; height:8px; background:#E53935;
                    border-radius:50%; margin-right:8px;"></span>
                <strong style="color:#C62828;">{exp['indicator']}</strong>
            </td>
            <td style="padding:12px 16px; border-bottom:1px solid #F0F0F0; color:#555;">{exp['sheet_name']}</td>
            <td style="padding:12px 16px; border-bottom:1px solid #F0F0F0; text-align:center;">
                <span style="background:#EEF2FF; color:#3949AB; padding:3px 10px;
                    border-radius:12px; font-size:12px; font-weight:600;">{exp['count']} dòng</span>
            </td>
            <td style="padding:12px 16px; border-bottom:1px solid #F0F0F0; text-align:center;
                color:{status_color}; font-weight:600;">{status_icon} {status_text}</td>
        </tr>"""

    detail_html = ""
    for exp in explanations:
        if exp.get("error"):
            detail_html += f"""
            <div style="margin-bottom:20px; padding:14px 18px; background:#FFEBEE;
                border-left:4px solid #C62828; border-radius:4px;">
                <strong style="color:#C62828;">❌ Lỗi – {exp['indicator']}</strong><br>
                <span style="color:#555; font-size:13px;">{exp['error']}</span>
            </div>"""
        elif exp.get("rows"):
            headers = exp.get("headers") or list(exp["rows"][0].keys())
            useful  = [h for h in headers if any(str(r.get(h,"")).strip() for r in exp["rows"])] or headers
            th_html = "".join(
                f'<th style="padding:10px 14px; text-align:left; background:#C62828; color:white; font-size:12px; font-weight:600; white-space:nowrap;">{h}</th>'
                for h in useful
            )
            td_rows = ""
            for i, row in enumerate(exp["rows"][:50]):
                bg  = "#FFF9F9" if i % 2 == 0 else "#FFFFFF"
                tds = "".join(
                    f'<td style="padding:10px 14px; border-bottom:1px solid #F5E6E6; font-size:12px; color:#333; max-width:250px; word-wrap:break-word;">{str(row.get(h,""))[:150]}</td>'
                    for h in useful
                )
                td_rows += f'<tr style="background:{bg};">{tds}</tr>'
            detail_html += f"""
            <div style="margin-bottom:28px;">
                <div style="display:flex; align-items:center; margin-bottom:12px;">
                    <div style="width:4px; height:20px; background:#C62828; border-radius:2px; margin-right:10px;"></div>
                    <h3 style="margin:0; font-size:15px; color:#C62828; font-weight:700;">{exp['indicator']}</h3>
                    <span style="margin-left:auto; background:#EEF2FF; color:#3949AB; padding:3px 10px;
                        border-radius:12px; font-size:11px; font-weight:600;">{exp['count']} bản ghi</span>
                </div>
                <div style="overflow-x:auto; border-radius:8px; border:1px solid #F5E6E6;">
                    <table style="border-collapse:collapse; width:100%; min-width:400px;">
                        <thead><tr>{th_html}</tr></thead>
                        <tbody>{td_rows}</tbody>
                    </table>
                </div>
            </div>"""
        else:
            detail_html += f"""
            <div style="margin-bottom:20px; padding:14px 18px; background:#FFF8E1;
                border-left:4px solid #FFC107; border-radius:4px;">
                <span style="color:#F57F17; font-size:13px;">
                    ⚠️ Chưa có dữ liệu giải trình cho: <strong>{exp['indicator']}</strong>
                </span>
            </div>"""

    total_records = sum(e["count"] for e in explanations)
    filled        = sum(1 for e in explanations if e["count"] > 0)

    import datetime as _dt
    now_str = _dt.datetime.now().strftime("%d/%m/%Y %H:%M")

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; background:#F4F6F9; font-family:'Segoe UI',Arial,sans-serif;">
<div style="max-width:720px; margin:24px auto; background:white; border-radius:12px;
    overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,0.08);">
  <div style="background:linear-gradient(135deg,#C62828 0%,#8B0000 100%); padding:28px 32px;">
    <div style="display:flex; align-items:center;">
      <div style="width:40px; height:40px; background:rgba(255,255,255,0.2); border-radius:8px;
          display:flex; align-items:center; justify-content:center; margin-right:14px; font-size:20px;">📊</div>
      <div>
        <h1 style="margin:0; color:white; font-size:20px; font-weight:700;">Báo cáo Giải trình Chỉ số Đỏ</h1>
        <p style="margin:4px 0 0; color:rgba(255,255,255,0.75); font-size:13px;">
            Chi nhánh {branch} &nbsp;·&nbsp; Ngày báo cáo: {report_date}</p>
      </div>
    </div>
  </div>
  <div style="background:#FFF5F5; padding:16px 32px; border-bottom:1px solid #F5E6E6; display:flex; gap:24px;">
    <div style="text-align:center;">
      <div style="font-size:22px; font-weight:700; color:#C62828;">{len(explanations)}</div>
      <div style="font-size:11px; color:#888; text-transform:uppercase;">Chỉ số đỏ</div>
    </div>
    <div style="width:1px; background:#F5E6E6;"></div>
    <div style="text-align:center;">
      <div style="font-size:22px; font-weight:700; color:#27AE60;">{filled}</div>
      <div style="font-size:11px; color:#888; text-transform:uppercase;">Đã giải trình</div>
    </div>
    <div style="width:1px; background:#F5E6E6;"></div>
    <div style="text-align:center;">
      <div style="font-size:22px; font-weight:700; color:#3949AB;">{total_records}</div>
      <div style="font-size:11px; color:#888; text-transform:uppercase;">Tổng bản ghi</div>
    </div>
  </div>
  <div style="padding:28px 32px;">
    <p style="margin:0 0 20px; color:#444; font-size:14px; line-height:1.6;">
      Kính gửi <strong>SOC Canh Bao</strong>,<br>
      Chi nhánh <strong>{branch}</strong> xin gửi giải trình về các chỉ số đỏ ngày <strong>{report_date}</strong>:
    </p>
    <div style="border-radius:10px; overflow:hidden; border:1px solid #F5E6E6; margin-bottom:28px;">
      <table style="border-collapse:collapse; width:100%;">
        <thead><tr style="background:#FFF5F5;">
          <th style="padding:12px 16px; text-align:left; font-size:12px; color:#888; font-weight:600; text-transform:uppercase; border-bottom:2px solid #F5E6E6;">Chỉ số</th>
          <th style="padding:12px 16px; text-align:left; font-size:12px; color:#888; font-weight:600; text-transform:uppercase; border-bottom:2px solid #F5E6E6;">Tab Sheet</th>
          <th style="padding:12px 16px; text-align:center; font-size:12px; color:#888; font-weight:600; text-transform:uppercase; border-bottom:2px solid #F5E6E6;">Số dòng</th>
          <th style="padding:12px 16px; text-align:center; font-size:12px; color:#888; font-weight:600; text-transform:uppercase; border-bottom:2px solid #F5E6E6;">Trạng thái</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    <div style="border-top:2px dashed #F5E6E6; margin:24px 0;"></div>
    <h2 style="margin:0 0 20px; font-size:16px; color:#333; font-weight:700;">📋 Chi tiết giải trình</h2>
    {detail_html}
  </div>
  <div style="background:#F9FAFB; padding:16px 32px; border-top:1px solid #EEEEEE; text-align:center;">
    <p style="margin:0; font-size:11px; color:#AAAAAA;">
      Email tự động · SOC Automation · Chi nhánh {branch} · {now_str}
    </p>
  </div>
</div>
</body></html>"""