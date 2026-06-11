"""
Email utilities: IMAP reading + SMTP sending
Parse HTML email từ SOC để nhận diện chỉ số đỏ chính xác.
"""
import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, date, timezone
import re
import html as html_module
from typing import Optional

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


def decode_str(s):
    if s is None:
        return ""
    decoded_parts = decode_header(s)
    result = ""
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result += part.decode(charset or "utf-8", errors="replace")
        else:
            result += str(part)
    return result


def connect_imap(address: str, password: str, server: str = "imap.gmail.com") -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(server)
    mail.login(address, password)
    return mail


def parse_email_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def search_soc_emails(
    mail: imaplib.IMAP4_SSL,
    sender_name: str = "SOC Canh bao",
    limit: int = 10
) -> list:
    mail.select("INBOX")
    _, data = mail.search(None, f'(FROM "{sender_name}")')
    email_ids = data[0].split()
    if not email_ids:
        return []

    fetch_ids = email_ids[-(limit * 2):]
    raw_emails = []

    for eid in fetch_ids:
        _, msg_data = mail.fetch(eid, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        date_str  = msg.get("Date", "")
        parsed_dt = parse_email_date(date_str)
        subject   = decode_str(msg.get("Subject", ""))
        sender    = decode_str(msg.get("From", ""))
        body_plain, body_html = extract_body_both(msg)

        raw_emails.append({
            "id":         eid.decode(),
            "subject":    subject,
            "sender":     sender,
            "date":       date_str,
            "parsed_dt":  parsed_dt,
            "body":       body_plain,   # plain text để hiển thị
            "body_html":  body_html,    # HTML gốc để parse chỉ số đỏ
            "raw":        msg,
        })

    raw_emails.sort(
        key=lambda e: e["parsed_dt"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True
    )
    return raw_emails[:limit]


def get_latest_soc_email(
    mail: imaplib.IMAP4_SSL,
    sender_name: str = "SOC Canh bao"
) -> Optional[dict]:
    emails = search_soc_emails(mail, sender_name, limit=1)
    return emails[0] if emails else None


def extract_body_both(msg) -> tuple:
    """Trả về (plain_text, html_content)."""
    plain = ""
    html_content = ""

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" and not plain:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                plain = payload.decode(charset, errors="replace")
            elif ctype == "text/html" and not html_content:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                html_content = payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        content = payload.decode(charset, errors="replace")
        if "<html" in content.lower():
            html_content = content
        else:
            plain = content

    # Nếu không có plain text thì strip HTML
    if not plain and html_content:
        plain = html_module.unescape(re.sub(r"<[^>]+>", " ", html_content))

    return plain, html_content


def extract_body(msg) -> str:
    plain, _ = extract_body_both(msg)
    return plain


# ── KPI indicators mapping ─────────────────────────────────────────────────
# Tên hiển thị → các từ khóa tìm trong email
KPI_INDICATORS = {
    "CSAT 1":              ["CSAT 1", "CSAT1"],
    "Checklist lặp ≥ 3":  ["Checklist lặp", "CLL3", "Checklist lặp ≥ 3"],
    "PTC ≥ 72h":           ["PTC ≥ 72h", "PTC >= 72h", "PTC≥72h"],
    "Checklist ≥24h":      ["Checklist ≥24h", "Checklist>=24h", "Checklist ≥ 24h"],
    "Yêu Cầu RM":          ["Yêu cầu RM", "YC RM", "YCRM"],
    "Yêu cầu khiếu nại":   ["Yêu cầu Khiếu nại", "khiếu nại", "khieu nai"],
    "Yêu cầu ≥48h":        ["Yêu cầu ≥48h", "yêu cầu 48h", "YC 48h"],
}


def parse_soc_email_html(html_content: str, email_date: str = "") -> dict:
    """
    Parse HTML email SOC dùng BeautifulSoup.
    Tìm chỉ số đỏ từ phần bullet list color:red đầu email (nguồn chính xác nhất).
    """
    result = {
        "report_date":     None,
        "report_date_obj": None,
        "deadline":        None,
        "red_indicators":  [],
        "raw_body":        "",
        "email_received":  email_date,
    }

    if email_date:
        dt = parse_email_date(email_date)
        if dt:
            result["report_date_obj"] = dt
            result["report_date"]     = dt.strftime("%d/%m/%Y")

    if not html_content:
        return result

    soup = BeautifulSoup(html_content, "html.parser")
    result["raw_body"] = soup.get_text(separator="\n")

    # ── 1. Tìm deadline từ text ──
    full_text = result["raw_body"]
    deadline_m = re.search(
        r"trước\s+12h\s+ngày\s+(\d{1,2}/\d{1,2}(?:/\d{4})?)",
        full_text, re.IGNORECASE
    )
    if deadline_m:
        result["deadline"] = f"12h ngày {deadline_m.group(1)}"

    # ── 2. Fallback report_date từ body ──
    if not result["report_date"]:
        date_m = re.search(r"(\d{2}/\d{2}/\d{4})", full_text)
        if date_m:
            result["report_date"] = date_m.group(1)

    # ── 3. CHIẾN LƯỢC CHÍNH: Tìm span/p có color:red trong phần bullet ──
    # SOC liệt kê chỉ số đỏ dưới dạng:
    # <span style='color:red'>• CSAT 1</span>
    # <span style='color:red'>• PTC ≥ 72h</span>
    red_from_bullets = _extract_red_bullets(soup)
    if red_from_bullets:
        result["red_indicators"] = red_from_bullets
        return result

    # ── 4. FALLBACK: tìm trong bảng nếu bullet không có ──
    red_from_table = _extract_red_from_table(soup)
    result["red_indicators"] = red_from_table

    return result


def _extract_red_bullets(soup) -> list:
    """
    Tìm các chỉ số đỏ từ phần bullet list đầu email.
    SOC dùng: <span style='...color:red'>• Tên chỉ số</span>
    """
    red_indicators = []
    RED_COLORS = {"red", "#ff0000", "#e53e3e", "#c62828", "#c00000", "rgb(255,0,0)"}

    # Tìm tất cả element có style color:red
    for tag in soup.find_all(style=True):
        style = tag.get("style", "").lower()
        # Kiểm tra có phải màu đỏ không
        is_red = False
        if "color:red" in style.replace(" ", "") or "color: red" in style:
            is_red = True
        else:
            # Kiểm tra hex đỏ
            color_m = re.search(r'color\s*:\s*([^;]+)', style)
            if color_m:
                color_val = color_m.group(1).strip().lower().replace(" ", "")
                if color_val in RED_COLORS:
                    is_red = True

        if not is_red:
            continue

        text = tag.get_text(strip=True)
        # Bỏ bullet point và khoảng trắng
        text = text.replace("•", "").replace("·", "").strip()
        if not text:
            continue

        # Match với KPI indicators
        matched = _match_indicator(text)
        if matched and matched not in red_indicators:
            red_indicators.append(matched)

    return red_indicators


def _extract_red_from_table(soup) -> list:
    """
    Fallback: tìm chỉ số đỏ từ bảng KPI.
    Tìm tên chỉ số trong cột 2 của hàng mà cột 4 (giá trị) có màu đỏ/cam và > 0.
    """
    red_indicators = []
    RED_ORANGE = {"red", "orange", "#ff0000", "#e53e3e", "#c62828", "#ffa500", "#dd6b20"}

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            # Kiểm tra xem có ô nào màu đỏ/cam không
            has_red_cell = False
            for cell in cells:
                for tag in cell.find_all(style=True):
                    style = tag.get("style", "").lower()
                    color_m = re.search(r'color\s*:\s*([^;]+)', style)
                    if color_m:
                        cv = color_m.group(1).strip().lower().replace(" ", "")
                        if cv in RED_ORANGE:
                            # Kiểm tra giá trị > 0
                            val_text = tag.get_text(strip=True)
                            nums = re.findall(r'\d+', val_text)
                            if nums and any(int(n) > 0 for n in nums):
                                has_red_cell = True
                                break
                if has_red_cell:
                    break

            if not has_red_cell:
                continue

            # Lấy tên chỉ số từ cột 2 (index 1)
            indicator_text = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            matched = _match_indicator(indicator_text)
            if matched and matched not in red_indicators:
                red_indicators.append(matched)

    return red_indicators


def _match_indicator(text: str) -> Optional[str]:
    """Match text với danh sách KPI indicators."""
    text_lower = text.lower()
    for indicator, keywords in KPI_INDICATORS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return indicator
    return None


def parse_soc_email(body: str, email_date: str = "", body_html: str = "") -> dict:
    """
    Hàm parse chính — dùng HTML nếu có, fallback về plain text.
    Tương thích ngược với code cũ.
    """
    # Ưu tiên parse HTML
    if body_html and BS4_AVAILABLE:
        result = parse_soc_email_html(body_html, email_date)
        if result["red_indicators"]:
            return result

    # Fallback: parse plain text (logic cũ)
    result = {
        "report_date":     None,
        "report_date_obj": None,
        "deadline":        None,
        "red_indicators":  [],
        "raw_body":        body,
        "email_received":  email_date,
    }

    if email_date:
        dt = parse_email_date(email_date)
        if dt:
            result["report_date_obj"] = dt
            result["report_date"]     = dt.strftime("%d/%m/%Y")

    if not result["report_date"]:
        m = re.search(r"(\d{2}/\d{2}/\d{4})", body)
        if m:
            result["report_date"] = m.group(1)

    deadline_m = re.search(
        r"trước\s+(\d{1,2}h\d{0,2})\s+ngày\s+(\d{1,2}/\d{1,2})",
        body, re.IGNORECASE
    )
    if deadline_m:
        result["deadline"] = f"{deadline_m.group(1)} ngày {deadline_m.group(2)}"

    lines = body.split("\n")
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        for indicator, keywords in KPI_INDICATORS.items():
            for kw in keywords:
                if kw.lower() in line_clean.lower():
                    nums = re.findall(r"\d+", line_clean)
                    if nums and any(int(n) > 0 for n in nums):
                        if indicator not in result["red_indicators"]:
                            result["red_indicators"].append(indicator)
                    break

    return result


def send_reply_email(
    smtp_server: str,
    address: str,
    password: str,
    to_address: str,
    subject: str,
    body_html: str,
    cc_list: list = None,
    reply_to_msg_id: str = None,
    excel_attachment: bytes = None,
    excel_filename: str = "giai_trinh.xlsx",
):
    from email.mime.base import MIMEBase
    from email import encoders

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = address
    msg["To"]      = to_address
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to_msg_id:
        msg["In-Reply-To"] = reply_to_msg_id
        msg["References"]  = reply_to_msg_id

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body_html, "html", "utf-8"))
    msg.attach(alt)

    if excel_attachment:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(excel_attachment)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{excel_filename}"')
        msg.attach(part)

    recipients = [to_address] + (cc_list or [])
    with smtplib.SMTP_SSL(smtp_server, 465) as server:
        server.login(address, password)
        server.sendmail(address, recipients, msg.as_bytes())
    return True


def test_imap_connection(address: str, password: str, server: str) -> tuple:
    try:
        mail = connect_imap(address, password, server)
        mail.logout()
        return True, "Kết nối IMAP thành công!"
    except Exception as e:
        return False, f"Lỗi IMAP: {str(e)}"


def test_smtp_connection(address: str, password: str, server: str) -> tuple:
    try:
        with smtplib.SMTP_SSL(server, 465) as s:
            s.login(address, password)
        return True, "Kết nối SMTP thành công!"
    except Exception as e:
        return False, f"Lỗi SMTP: {str(e)}"