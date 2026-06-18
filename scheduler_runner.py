"""
scheduler_runner.py
Chạy riêng: python scheduler_runner.py
- Tự động đọc lại config mỗi lần chạy job → sếp đổi giờ trên app, có hiệu lực ngay
- Chỉ gửi báo cáo nếu report_date hiện tại CHƯA từng được gửi thành công
- Cảnh báo Admin nếu quét email thất bại liên tiếp (App Password hết hạn...)

Thay đổi so với bản cũ:
  - Fix Bug #2  : parse_soc_email() thiếu body_html → bỏ sót chỉ số đỏ trong HTML
  - Fix Logic #1: append_history() chưa được gọi → Lịch sử BC trống khi auto-send
  - Fix Logic #4: reminder_m - 30 âm → dùng timedelta thay vì tính trực tiếp
  - Fix Logic #5: gating check dựa trên last_scan_date không đáng tin cậy →
                  đổi sang so sánh report_date với last_sent_report_date
  - Fix DRY #1  : load_state / save_state / _backup_state → dùng state_manager
  - Fix DRY #3  : append_log duplicate → dùng state_manager
  - Fix DRY #4  : CONFIG_FILE / STATE_FILE / LOG_FILE → dùng constants
  - Fix DRY #6  : load_config() định nghĩa riêng (đọc thô, không fallback đầy
                  đủ) → dùng state_manager.load_config() (1 nguồn duy nhất,
                  cùng bản dùng cho app.py/settings_page.py)
  - Fix DRY #7  : "Asia/Ho_Chi_Minh" lặp lại 4 lần → SCHEDULER_TIMEZONE constant
  - Mới: cảnh báo Admin nếu quét email IMAP thất bại liên tiếp quá ngưỡng
         MAX_CONSECUTIVE_SCAN_FAILURES (xem job_scan_email + _handle_scan_failure)
"""
import logging
from datetime import datetime, date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("soc_scheduler.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ── Import từ utils thay vì định nghĩa lại (Fix DRY #3, #4, #6, #7) ──────────
from utils.constants     import (
    DEFAULT_BRANCH, DEFAULT_SOC_SENDER,
    DEFAULT_IMAP_SERVER, DEFAULT_SMTP_SERVER,
    DEFAULT_SCAN_INTERVAL, DEFAULT_REPLY_HOUR, DEFAULT_REPLY_MINUTE,
    SCHEDULER_TIMEZONE, MAX_CONSECUTIVE_SCAN_FAILURES,
)
from utils.state_manager import (
    load_state, save_state, append_log, append_history,
    load_config,
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _calc_reminder_time(reply_h: int, reply_m: int, minutes_before: int = 30) -> tuple:
    """
    Tính giờ nhắc nhở trước deadline bằng timedelta.
    Fix Logic #4: tránh edge case hour = -1 khi reply_h = 0 và reply_m < 30.

    Ví dụ: deadline 00:15 → reminder 23:45 (ngày hôm trước)
    """
    deadline_dt = datetime(2000, 1, 1, reply_h, reply_m)
    reminder_dt = deadline_dt - timedelta(minutes=minutes_before)
    return reminder_dt.hour, reminder_dt.minute


def get_schedule_config() -> tuple:
    """Đọc cấu hình lịch từ settings.json. Trả về (scan_interval, reply_h, reply_m)."""
    config    = load_config()
    sched_cfg = config.get("scheduler", {})
    return (
        sched_cfg.get("scan_interval_minutes",  DEFAULT_SCAN_INTERVAL),
        sched_cfg.get("reply_deadline_hour",    DEFAULT_REPLY_HOUR),
        sched_cfg.get("reply_deadline_minute",  DEFAULT_REPLY_MINUTE),
    )


# ─────────────────────────────────────────────────────────────────────────────
# JOBS
# ─────────────────────────────────────────────────────────────────────────────

def job_scan_email():
    """
    JOB 1: Quét email SOC, lưu state. Tự đọc config mới nhất mỗi lần chạy.
    Nếu IMAP login/kết nối thất bại liên tiếp quá MAX_CONSECUTIVE_SCAN_FAILURES
    lần, gửi cảnh báo cho Admin (chỉ 1 lần, không spam mỗi 30 phút).
    """
    log.info("=== JOB: SCAN EMAIL ===")
    config    = load_config()
    email_cfg = config.get("email", {})

    if not email_cfg.get("address") or not email_cfg.get("password"):
        log.warning("Email chưa được cấu hình. Bỏ qua.")
        return

    try:
        from utils.email_utils import connect_imap, search_soc_emails, parse_soc_email

        mail = connect_imap(
            email_cfg["address"],
            email_cfg["password"],
            email_cfg.get("imap_server", DEFAULT_IMAP_SERVER),
        )
        emails = search_soc_emails(
            mail,
            config.get("soc_sender_name", DEFAULT_SOC_SENDER),
            limit=5,
        )
        mail.logout()

        # Kết nối + đăng nhập IMAP thành công (dù có email hay không)
        # → đây là lúc reset bộ đếm lỗi, KHÔNG đợi đến khi tìm thấy email
        _reset_scan_failure_counter()

        if not emails:
            log.info("Không tìm thấy email SOC.")
            append_log("SCAN_EMAIL", "Không tìm thấy email SOC", "warning")
            return

        latest = emails[0]

        # ── Fix Bug #2: truyền body_html để parse chính xác ──────────────────
        # Bản cũ chỉ truyền 2 tham số → luôn dùng plain text → bỏ sót chỉ số đỏ
        parsed = parse_soc_email(
            latest["body"],
            latest.get("date", ""),
            latest.get("body_html", ""),   # ← FIX: thêm tham số này
        )

        log.info(f"Email: {latest['subject']} | Chỉ số đỏ: {parsed['red_indicators']}")

        state = load_state()
        state.update({
            "last_scan":            datetime.now().strftime("%d/%m/%Y %H:%M"),
            "last_scan_date":       date.today().strftime("%d/%m/%Y"),
            "total_scans":          state.get("total_scans", 0) + 1,
            "red_indicators":       parsed["red_indicators"],
            "report_date":          parsed["report_date"],
            "deadline":             parsed["deadline"],
            "status":               "active",
            "latest_email_sender":  latest["sender"],
            "latest_email_subject": latest["subject"],
            "latest_email_date":    latest.get("date", ""),
        })
        save_state(state)

        append_log(
            "SCAN_EMAIL",
            f"Tìm thấy {len(emails)} email · "
            f"{len(parsed['red_indicators'])} chỉ số đỏ: "
            f"{', '.join(parsed['red_indicators'])}",
            "success",
        )

    except Exception as e:
        log.error(f"Lỗi scan email: {e}")
        append_log("SCAN_EMAIL", f"Lỗi: {str(e)}", "error")
        _handle_scan_failure(config, email_cfg, str(e))


def job_send_report():
    """
    JOB 2: Gửi báo cáo tự động.
    - Chỉ gửi nếu report_date hiện tại CHƯA từng được gửi thành công trước đó
      (tránh gửi lại nội dung CŨ khi SOC không gửi cảnh báo mới trong ngày)
    - Retry 3 lần nếu thất bại, mỗi lần cách 2 phút
    - Lưu history.json sau mỗi lần gửi (kể cả thất bại)
    """
    log.info("=== JOB: SEND REPORT ===")
    config     = load_config()
    state      = load_state()
    email_cfg  = config.get("email", {})
    sheets_cfg = config.get("google_sheets", {})
    branch     = config.get("branch", DEFAULT_BRANCH)

    # ── Kiểm tra: report_date hiện tại ĐÃ từng gửi thành công chưa? ──────────
    # FIX QUAN TRỌNG: bản cũ so sánh "last_scan_date" với "hôm nay", nhưng vì
    # search_soc_emails() không lọc theo ngày trong IMAP, mỗi lần quét luôn
    # tìm thấy email GẦN NHẤT có sẵn (có thể CŨ) và (sai) gán last_scan_date =
    # ngày job quét CHẠY — không phải ngày email THỰC SỰ được gửi.
    # → Check cũ luôn "pass" ngay cả khi SOC không gửi gì mới trong nhiều ngày
    #   → có nguy cơ GỬI LẠI nội dung cũ cho SOC mỗi ngày.
    # Check mới: so sánh report_date (trích từ NỘI DUNG/NGÀY THỰC của email)
    # với report_date đã gửi thành công gần nhất. Giống nhau → chưa có báo cáo
    # mới → KHÔNG gửi lại.
    report_date           = state.get("report_date", "")
    last_sent_report_date = state.get("last_sent_report_date", "")

    if not report_date:
        msg = "Chưa quét được báo cáo nào (report_date trống). Bỏ qua."
        log.info(msg)
        append_log("AUTO_REPLY", msg, "warning")
        return

    if report_date == last_sent_report_date:
        msg = (
            f"Báo cáo ngày {report_date} đã được gửi thành công trước đó. "
            f"SOC chưa gửi cảnh báo mới — KHÔNG gửi lại nội dung cũ."
        )
        log.info(msg)
        append_log("AUTO_REPLY", msg, "warning")
        return

    red_indicators = state.get("red_indicators", [])
    if not red_indicators:
        log.info("Không có chỉ số đỏ hôm nay. Bỏ qua.")
        append_log("AUTO_REPLY", "Không có chỉ số đỏ hôm nay", "warning")
        return

    if not email_cfg.get("address") or not email_cfg.get("password"):
        log.warning("Email chưa cấu hình. Bỏ qua.")
        return

    to_address = state.get("latest_email_sender", "")
    if not to_address:
        log.warning("Không có địa chỉ nhận. Bỏ qua.")
        return

    subject = (
        f"Re: {state.get('latest_email_subject', DEFAULT_SOC_SENDER)} "
        f"– Giải trình {state.get('report_date', '')}"
    )

    try:
        # ── Lấy dữ liệu giải trình từ Google Sheets ──────────────────────────
        if sheets_cfg.get("credentials_path"):
            from utils.sheets_utils import collect_all_explanations
            explanations = collect_all_explanations(
                sheets_cfg["credentials_path"],
                sheets_cfg.get("spreadsheet_id", ""),
                red_indicators,
                state.get("report_date", ""),
            )
        else:
            explanations = [
                {"indicator": ind, "sheet_name": ind, "rows": [], "count": 0, "error": None}
                for ind in red_indicators
            ]

        from utils.sheets_utils import build_email_html
        html_body = build_email_html(
            state.get("report_date", "N/A"),
            branch,
            explanations,
        )

        from utils.email_utils import send_reply_email

        # ── Retry 3 lần, mỗi lần cách 2 phút ────────────────────────────────
        MAX_RETRY   = 3
        RETRY_DELAY = 120  # giây
        last_error  = None

        for attempt in range(1, MAX_RETRY + 1):
            try:
                send_reply_email(
                    smtp_server = email_cfg.get("smtp_server", DEFAULT_SMTP_SERVER),
                    address     = email_cfg["address"],
                    password    = email_cfg["password"],
                    to_address  = to_address,
                    subject     = subject,
                    body_html   = html_body,
                )

                # ── Gửi thành công ────────────────────────────────────────────
                state["last_email_sent"]       = datetime.now().strftime("%d/%m/%Y %H:%M")
                state["total_emails_sent"]     = state.get("total_emails_sent", 0) + 1
                state["last_sent_report_date"] = report_date  # đánh dấu đã gửi báo cáo này
                save_state(state)

                append_log(
                    "AUTO_REPLY",
                    f"Gửi thành công → {to_address} (lần thử {attempt}/{MAX_RETRY})",
                    "success",
                )

                # ── Fix Logic #1: Lưu history sau auto-send ───────────────────
                # Bản cũ bỏ qua bước này → Lịch sử BC không có dữ liệu tự động
                append_history(
                    report_date    = state.get("report_date", ""),
                    branch         = branch,
                    to_address     = to_address,
                    subject        = subject,
                    red_indicators = red_indicators,
                    explanations   = explanations,
                    status         = "success",
                )
                log.info(f"✅ Gửi báo cáo thành công (lần {attempt})")
                return  # Xong → thoát ngay

            except Exception as e:
                last_error = str(e)
                log.warning(f"Lần {attempt}/{MAX_RETRY} thất bại: {e}")
                if attempt < MAX_RETRY:
                    import time
                    time.sleep(RETRY_DELAY)

        # ── Thất bại sau tất cả các lần retry ────────────────────────────────
        err_msg = f"Gửi thất bại sau {MAX_RETRY} lần: {last_error}"
        log.error(err_msg)
        append_log("AUTO_REPLY", err_msg, "error")

        # Lưu history thất bại để admin có thể truy vết trên trang Lịch sử BC
        append_history(
            report_date    = state.get("report_date", ""),
            branch         = branch,
            to_address     = to_address,
            subject        = subject,
            red_indicators = red_indicators,
            explanations   = explanations,
            status         = "error",
        )

        # Gửi email cảnh báo cho Admin
        _send_failure_alert(email_cfg, red_indicators, last_error)

    except Exception as e:
        log.error(f"Lỗi nghiêm trọng trong job_send_report: {e}")
        append_log("AUTO_REPLY", f"Lỗi nghiêm trọng: {str(e)}", "error")


def job_send_reminder():
    """
    JOB 4: Gửi email nhắc nhở đến Admin 30 phút trước deadline.
    Chỉ gửi nếu hôm nay đã nhận email SOC và có chỉ số đỏ.
    """
    log.info("=== JOB: SEND REMINDER ===")
    config    = load_config()
    state     = load_state()
    email_cfg = config.get("email", {})
    branch    = config.get("branch", DEFAULT_BRANCH)

    # today_str: chỉ dùng để HIỂN THỊ trong nội dung email nhắc nhở,
    # không còn dùng để quyết định có nhắc hay không (xem logic report_date dưới đây)
    today_str = date.today().strftime("%d/%m/%Y")

    # Cùng logic với job_send_report(): chỉ nhắc nếu báo cáo CHƯA được gửi.
    # (Tránh nhắc nhở vô nghĩa cho báo cáo cũ đã xử lý xong từ trước.)
    report_date           = state.get("report_date", "")
    last_sent_report_date = state.get("last_sent_report_date", "")

    if not report_date or report_date == last_sent_report_date:
        log.info("Không có báo cáo mới cần nhắc nhở (đã gửi hoặc chưa quét được).")
        return

    red_indicators = state.get("red_indicators", [])
    if not red_indicators:
        log.info("Không có chỉ số đỏ. Bỏ qua nhắc nhở.")
        return

    if not email_cfg.get("address") or not email_cfg.get("password"):
        log.warning("Email chưa cấu hình.")
        return

    sched_cfg    = config.get("scheduler", {})
    deadline_h   = sched_cfg.get("reply_deadline_hour",   DEFAULT_REPLY_HOUR)
    deadline_m   = sched_cfg.get("reply_deadline_minute", DEFAULT_REPLY_MINUTE)
    deadline_str = f"{deadline_h:02d}:{deadline_m:02d}"

    indicators_html = "".join(
        f'<li style="margin:4px 0; color:#C62828; font-weight:600;">{ind}</li>'
        for ind in red_indicators
    )

    html_body = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#F4F6F9;font-family:'Segoe UI',Arial,sans-serif;">
<div style="max-width:560px;margin:24px auto;background:white;border-radius:12px;
    overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
  <div style="background:linear-gradient(135deg,#E65100 0%,#BF360C 100%);padding:24px 32px;">
    <h1 style="margin:0;color:white;font-size:18px;font-weight:700;">⚠️ Nhắc nhở Deadline SOC</h1>
    <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:13px;">
      Chi nhánh {branch} · Ngày {today_str}
    </p>
  </div>
  <div style="padding:28px 32px;">
    <p style="font-size:15px;color:#333;line-height:1.6;margin:0 0 20px;">
      ⚠️ Còn 30 phút đến deadline! Kiểm tra và gửi báo cáo trước <strong>{deadline_str}</strong>.
    </p>
    <div style="background:#FFF5F5;border-left:4px solid #C62828;border-radius:4px;
        padding:16px 20px;margin-bottom:20px;">
      <p style="margin:0 0 10px;font-size:13px;font-weight:700;color:#C62828;
          text-transform:uppercase;letter-spacing:1px;">
        Chỉ số đỏ cần giải trình hôm nay:
      </p>
      <ul style="margin:0;padding-left:20px;">{indicators_html}</ul>
    </div>
    <p style="font-size:13px;color:#888;margin:0;">
      Vào <strong>SOC Automation</strong> → <strong>Gửi Email</strong>
      → gửi trước {deadline_str}.
    </p>
  </div>
  <div style="background:#F9FAFB;padding:14px 32px;border-top:1px solid #EEE;text-align:center;">
    <p style="margin:0;font-size:11px;color:#AAA;">
      Email tự động · SOC Automation · {branch} · {datetime.now().strftime('%d/%m/%Y %H:%M')}
    </p>
  </div>
</div>
</body></html>"""

    try:
        from utils.email_utils import send_reply_email
        send_reply_email(
            smtp_server = email_cfg.get("smtp_server", DEFAULT_SMTP_SERVER),
            address     = email_cfg["address"],
            password    = email_cfg["password"],
            to_address  = email_cfg["address"],
            subject     = f"⚠️ [SOC-{branch}] Nhắc nhở: Còn 30 phút đến deadline {deadline_str} – {today_str}",
            body_html   = html_body,
        )
        log.info(f"✅ Đã gửi nhắc nhở đến {email_cfg['address']}")
        append_log("REMINDER", f"Nhắc nhở deadline {deadline_str} – {len(red_indicators)} chỉ số đỏ", "success")
    except Exception as e:
        log.error(f"Lỗi gửi nhắc nhở: {e}")
        append_log("REMINDER", f"Lỗi gửi nhắc nhở: {str(e)}", "error")


def job_check_and_reschedule(scheduler):
    """
    JOB 3: Kiểm tra mỗi 5 phút xem config đã đổi chưa → tự cập nhật lịch.
    Fix Logic #4: dùng _calc_reminder_time thay vì tính trực tiếp.
    """
    scan_interval, reply_h, reply_m = get_schedule_config()
    reminder_h, reminder_m = _calc_reminder_time(reply_h, reply_m, minutes_before=30)

    from apscheduler.triggers.cron     import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.reschedule_job(
        "send_report",
        trigger=CronTrigger(hour=reply_h, minute=reply_m, timezone=SCHEDULER_TIMEZONE),
    )
    scheduler.reschedule_job(
        "scan_email",
        trigger=IntervalTrigger(minutes=scan_interval),
    )
    scheduler.reschedule_job(
        "send_reminder",
        trigger=CronTrigger(hour=reminder_h, minute=reminder_m, timezone=SCHEDULER_TIMEZONE),
    )
    log.debug(
        f"Config reloaded: quét mỗi {scan_interval}p · "
        f"nhắc {reminder_h:02d}:{reminder_m:02d} · "
        f"gửi {reply_h:02d}:{reply_m:02d}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE
# ─────────────────────────────────────────────────────────────────────────────

def _handle_scan_failure(config: dict, email_cfg: dict, error_msg: str) -> None:
    """
    Theo dõi số lần quét email thất bại liên tiếp (lỗi kết nối/đăng nhập IMAP).
    Khi vượt ngưỡng MAX_CONSECUTIVE_SCAN_FAILURES, gửi cảnh báo cho Admin —
    CHỈ MỘT LẦN cho đến khi quét thành công trở lại (tránh spam mỗi 30 phút).
    """
    state    = load_state()
    failures = state.get("consecutive_scan_failures", 0) + 1
    state["consecutive_scan_failures"] = failures

    should_alert = (
        failures >= MAX_CONSECUTIVE_SCAN_FAILURES
        and not state.get("scan_failure_alert_sent", False)
    )
    if should_alert:
        state["scan_failure_alert_sent"] = True

    save_state(state)
    log.warning(f"Quét email thất bại liên tiếp lần {failures}/{MAX_CONSECUTIVE_SCAN_FAILURES}.")

    if should_alert:
        _send_scan_failure_alert(email_cfg, config.get("branch", DEFAULT_BRANCH), failures, error_msg)


def _reset_scan_failure_counter() -> None:
    """Reset bộ đếm lỗi quét khi kết nối IMAP thành công trở lại."""
    state = load_state()
    if state.get("consecutive_scan_failures", 0) > 0 or state.get("scan_failure_alert_sent", False):
        state["consecutive_scan_failures"] = 0
        state["scan_failure_alert_sent"]   = False
        save_state(state)


def _send_scan_failure_alert(email_cfg: dict, branch: str, failure_count: int, error_msg: str) -> None:
    """
    Gửi email cảnh báo cho Admin khi QUÉT email thất bại liên tiếp quá ngưỡng.

    LƯU Ý QUAN TRỌNG: nếu nguyên nhân gốc là App Password sai/hết hạn, SMTP
    (dùng để gửi cảnh báo này) thường dùng CHUNG thông tin đăng nhập với IMAP
    nên có thể CŨNG thất bại theo. Đây là giới hạn cố hữu khi hệ thống chỉ có
    1 kênh thông báo duy nhất là email. Nếu việc này xảy ra thường xuyên, nên
    bổ sung kênh cảnh báo thứ 2 (ví dụ Slack/Telegram webhook) trong tương lai.
    """
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif; padding:24px; background:#F4F6F9;">
<div style="max-width:560px; margin:0 auto; background:white; border-radius:12px;
    padding:28px; box-shadow:0 4px 20px rgba(0,0,0,0.08);">
  <h2 style="color:#C62828; margin:0 0 16px;">⚠️ Quét email SOC thất bại liên tiếp</h2>
  <p style="color:#555; line-height:1.6;">
    Hệ thống đã thử quét email <strong>{failure_count} lần liên tiếp</strong> nhưng
    đều thất bại. Nguyên nhân thường gặp: App Password Gmail đã hết hạn, bị đổi,
    hoặc tài khoản bị khoá/giới hạn đăng nhập.
  </p>
  <div style="background:#FFF5F5; border-left:4px solid #C62828; border-radius:4px;
      padding:14px 18px; margin:16px 0;">
    <p style="margin:0; font-family:monospace; font-size:12px; color:#555; word-break:break-all;">
        {error_msg}
    </p>
  </div>
  <p style="color:#C62828; font-weight:600;">
    ⚠️ Vui lòng vào Cấu hình → Email để kiểm tra và cập nhật lại App Password!
  </p>
  <hr style="border:none; border-top:1px solid #EEE; margin:20px 0;">
  <small style="color:#AAA;">SOC Automation · Chi nhánh {branch} · {datetime.now().strftime('%d/%m/%Y %H:%M')}</small>
</div>
</body></html>"""

    try:
        from utils.email_utils import send_reply_email
        send_reply_email(
            smtp_server = email_cfg.get("smtp_server", DEFAULT_SMTP_SERVER),
            address     = email_cfg["address"],
            password    = email_cfg["password"],
            to_address  = email_cfg["address"],
            subject     = f"⚠️ [SOC-{branch}] Quét email thất bại {failure_count} lần liên tiếp – Kiểm tra ngay!",
            body_html   = html,
        )
        log.info(f"✅ Đã gửi cảnh báo quét thất bại đến Admin: {email_cfg['address']}")
        append_log("FAILURE_ALERT", f"Cảnh báo quét email thất bại {failure_count} lần liên tiếp", "warning")
    except Exception as e:
        # Nếu nguyên nhân gốc là sai mật khẩu, SMTP cũng sẽ thất bại theo —
        # chỉ còn log lại, không có kênh nào khác để thông báo trong phạm vi
        # hệ thống hiện tại (xem ghi chú trong docstring).
        log.error(f"Không thể gửi cảnh báo quét thất bại (có thể do cùng nguyên nhân gốc): {e}")


def _send_failure_alert(email_cfg: dict, red_indicators: list, error_msg: str):
    """Gửi email cảnh báo cho Admin khi gửi báo cáo thất bại sau 3 lần retry."""
    indicators_html = "".join(
        f'<li style="color:#C62828; font-weight:600; margin:4px 0;">{ind}</li>'
        for ind in red_indicators
    )
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif; padding:24px; background:#F4F6F9;">
<div style="max-width:560px; margin:0 auto; background:white; border-radius:12px;
    padding:28px; box-shadow:0 4px 20px rgba(0,0,0,0.08);">
  <h2 style="color:#C62828; margin:0 0 16px;">❌ Gửi báo cáo SOC thất bại</h2>
  <p style="color:#555;">Hệ thống đã thử gửi báo cáo <strong>3 lần</strong> nhưng không thành công.</p>
  <p style="color:#555;"><strong>Lỗi:</strong> {error_msg}</p>
  <div style="background:#FFF5F5; border-left:4px solid #C62828; border-radius:4px;
      padding:14px 18px; margin:16px 0;">
    <p style="margin:0 0 8px; font-weight:700; color:#C62828;">Chỉ số đỏ cần báo cáo:</p>
    <ul style="margin:0; padding-left:20px;">{indicators_html}</ul>
  </div>
  <p style="color:#C62828; font-weight:600;">
    ⚠️ Vui lòng vào hệ thống SOC Automation và gửi thủ công ngay!
  </p>
  <hr style="border:none; border-top:1px solid #EEE; margin:20px 0;">
  <small style="color:#AAA;">SOC Automation · {datetime.now().strftime('%d/%m/%Y %H:%M')}</small>
</div>
</body></html>"""

    try:
        from utils.email_utils import send_reply_email
        send_reply_email(
            smtp_server = email_cfg.get("smtp_server", DEFAULT_SMTP_SERVER),
            address     = email_cfg["address"],
            password    = email_cfg["password"],
            to_address  = email_cfg["address"],
            subject     = f"❌ [SOC-HUE] Gửi báo cáo thất bại – Xử lý ngay! ({datetime.now().strftime('%d/%m/%Y %H:%M')})",
            body_html   = html,
        )
        log.info(f"✅ Đã gửi cảnh báo thất bại đến Admin: {email_cfg['address']}")
        append_log("FAILURE_ALERT", f"Cảnh báo → Admin {email_cfg['address']}", "warning")
    except Exception as e:
        log.error(f"Không thể gửi cảnh báo thất bại: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval   import IntervalTrigger
        from apscheduler.triggers.cron       import CronTrigger
    except ImportError:
        log.error("APScheduler chưa cài. Chạy: pip install apscheduler")
        return

    scan_interval, reply_h, reply_m = get_schedule_config()
    # Fix Logic #4: dùng hàm helper thay vì reply_m - 30 trực tiếp
    reminder_h, reminder_m = _calc_reminder_time(reply_h, reply_m, minutes_before=30)

    scheduler = BlockingScheduler(timezone=SCHEDULER_TIMEZONE)

    # Job 1: Quét email định kỳ
    scheduler.add_job(
        job_scan_email,
        trigger=IntervalTrigger(minutes=scan_interval),
        id="scan_email",
        name="Quét Email SOC",
        replace_existing=True,
    )

    # Job 2: Gửi báo cáo hàng ngày đúng deadline
    scheduler.add_job(
        job_send_report,
        trigger=CronTrigger(hour=reply_h, minute=reply_m, timezone=SCHEDULER_TIMEZONE),
        id="send_report",
        name="Gửi Báo cáo Tự động",
        replace_existing=True,
    )

    # Job 3: Kiểm tra config thay đổi mỗi 5 phút → tự cập nhật lịch
    scheduler.add_job(
        lambda: job_check_and_reschedule(scheduler),
        trigger=IntervalTrigger(minutes=5),
        id="check_config",
        name="Kiểm tra cấu hình",
        replace_existing=True,
    )

    # Job 4: Nhắc nhở Admin 30 phút trước deadline
    scheduler.add_job(
        job_send_reminder,
        trigger=CronTrigger(hour=reminder_h, minute=reminder_m, timezone=SCHEDULER_TIMEZONE),
        id="send_reminder",
        name="Nhắc nhở Deadline",
        replace_existing=True,
    )

    log.info("=" * 50)
    log.info("SOC Scheduler khởi động")
    log.info(f"  Quét email   : mỗi {scan_interval} phút")
    log.info(f"  Nhắc nhở     : {reminder_h:02d}:{reminder_m:02d} hàng ngày")
    log.info(f"  Gửi báo cáo  : {reply_h:02d}:{reply_m:02d} hàng ngày")
    log.info(f"  Reload config : mỗi 5 phút")
    log.info("=" * 50)

    job_scan_email()  # Quét ngay khi khởi động

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler đã dừng.")


if __name__ == "__main__":
    main()