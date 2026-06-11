"""
scheduler_runner.py
Chạy riêng: python scheduler_runner.py
- Tự động đọc lại config mỗi lần chạy job → sếp đổi giờ trên app, có hiệu lực ngay lần gửi tiếp theo
- Chỉ gửi báo cáo nếu email SOC nhận được TRONG NGÀY HÔM ĐÓ
"""
import json
import logging
from pathlib import Path
from datetime import datetime, date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("soc_scheduler.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

CONFIG_FILE = Path("config/settings.json")
STATE_FILE  = Path("config/state.json")
LOG_FILE    = Path("config/logs.json")


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                content = f.read().strip()
            return json.loads(content) if content else {}
        except Exception:
            pass
    return {}


def save_state(state):
    STATE_FILE.parent.mkdir(exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    _backup_state()


def _backup_state(max_backups: int = 7):
    """Lưu backup state.json, giữ tối đa max_backups bản gần nhất."""
    if not STATE_FILE.exists():
        return
    try:
        backup_dir  = STATE_FILE.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"state_{timestamp}.json"
        backup_file.write_bytes(STATE_FILE.read_bytes())

        # Xoá bản cũ nếu vượt quá max_backups
        backups = sorted(backup_dir.glob("state_*.json"))
        for old_file in backups[:-max_backups]:
            old_file.unlink()
    except Exception as e:
        log.warning(f"Không thể backup state.json: {e}")


def append_log(action: str, detail: str, status: str = "success"):
    LOG_FILE.parent.mkdir(exist_ok=True)
    logs = []
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, encoding="utf-8") as f:
                content = f.read().strip()
            logs = json.loads(content) if content else []
        except Exception:
            logs = []
    logs.insert(0, {
        "time":   datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "action": action,
        "detail": detail,
        "status": status,
    })
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs[:200], f, ensure_ascii=False, indent=2)


def job_scan_email():
    """JOB 1: Quét email SOC, lưu state. Tự đọc config mới nhất mỗi lần chạy."""
    log.info("=== JOB: SCAN EMAIL ===")
    config    = load_config()  # đọc lại config mới nhất
    email_cfg = config.get("email", {})

    if not email_cfg.get("address") or not email_cfg.get("password"):
        log.warning("Email chưa được cấu hình. Bỏ qua.")
        return

    try:
        from utils.email_utils import connect_imap, search_soc_emails, parse_soc_email
        mail   = connect_imap(
            email_cfg["address"],
            email_cfg["password"],
            email_cfg.get("imap_server", "imap.gmail.com")
        )
        emails = search_soc_emails(mail, config.get("soc_sender_name", "SOC Canh bao"), limit=5)
        mail.logout()

        if not emails:
            log.info("Không tìm thấy email SOC.")
            append_log("SCAN_EMAIL", "Không tìm thấy email SOC", "warning")
            return

        latest = emails[0]
        parsed = parse_soc_email(latest["body"], latest.get("date", ""))
        log.info(f"Email mới nhất: {latest['subject']} | Chỉ số đỏ: {parsed['red_indicators']}")

        state = load_state()
        state["last_scan"]            = datetime.now().strftime("%d/%m/%Y %H:%M")
        state["last_scan_date"]       = date.today().strftime("%d/%m/%Y")  # lưu ngày quét
        state["total_scans"]          = state.get("total_scans", 0) + 1
        state["red_indicators"]       = parsed["red_indicators"]
        state["report_date"]          = parsed["report_date"]
        state["deadline"]             = parsed["deadline"]
        state["status"]               = "active"
        state["latest_email_sender"]  = latest["sender"]
        state["latest_email_subject"] = latest["subject"]
        state["latest_email_date"]    = latest.get("date", "")
        save_state(state)

        append_log(
            "SCAN_EMAIL",
            f"Tìm thấy {len(emails)} email. {len(parsed['red_indicators'])} chỉ số đỏ: {', '.join(parsed['red_indicators'])}",
            "success"
        )

    except Exception as e:
        log.error(f"Lỗi scan email: {e}")
        append_log("SCAN_EMAIL", f"Lỗi: {str(e)}", "error")


def job_send_report():
    """
    JOB 2: Gửi báo cáo.
    - Tự đọc config mới nhất → sếp đổi giờ trên app có hiệu lực ngay
    - Chỉ gửi nếu đã quét được email SOC TRONG NGÀY HÔM NAY
    """
    log.info("=== JOB: SEND REPORT ===")
    config     = load_config()  # đọc lại config mới nhất
    state      = load_state()
    email_cfg  = config.get("email", {})
    sheets_cfg = config.get("google_sheets", {})

    # ── Kiểm tra: chỉ gửi nếu email SOC nhận được HÔM NAY ──
    today_str      = date.today().strftime("%d/%m/%Y")
    last_scan_date = state.get("last_scan_date", "")

    if last_scan_date != today_str:
        msg = f"Hôm nay ({today_str}) chưa nhận email SOC (quét gần nhất: {last_scan_date or 'chưa có'}). Bỏ qua gửi báo cáo."
        log.info(msg)
        append_log("AUTO_REPLY", msg, "warning")
        return

    red_indicators = state.get("red_indicators", [])
    if not red_indicators:
        log.info("Không có chỉ số đỏ hôm nay. Bỏ qua.")
        append_log("AUTO_REPLY", "Không có chỉ số đỏ hôm nay", "warning")
        return

    if not email_cfg.get("address") or not email_cfg.get("password"):
        log.warning("Email chưa cấu hình.")
        return

    try:
        explanations = []
        if sheets_cfg.get("credentials_path"):
            from utils.sheets_utils import collect_all_explanations
            explanations = collect_all_explanations(
                sheets_cfg["credentials_path"],
                sheets_cfg.get("spreadsheet_id", ""),
                red_indicators,
                state.get("report_date", "")
            )
        else:
            explanations = [
                {"indicator": ind, "sheet_name": ind, "rows": [], "count": 0, "error": None}
                for ind in red_indicators
            ]

        from utils.sheets_utils import build_email_html
        html_body = build_email_html(
            state.get("report_date", "N/A"),
            config.get("branch", "HUE"),
            explanations
        )

        to_address = state.get("latest_email_sender", "")
        if not to_address:
            log.warning("Không có địa chỉ nhận. Bỏ qua.")
            return

        subject = f"Re: {state.get('latest_email_subject', 'SOC Canh bao')} – Giải trình {state.get('report_date', '')}"

        from utils.email_utils import send_reply_email

        # ── Retry 3 lần, mỗi lần cách 2 phút ──
        MAX_RETRY   = 3
        RETRY_DELAY = 120  # giây
        last_error  = None

        for attempt in range(1, MAX_RETRY + 1):
            try:
                send_reply_email(
                    smtp_server=email_cfg.get("smtp_server", "smtp.gmail.com"),
                    address=email_cfg["address"],
                    password=email_cfg["password"],
                    to_address=to_address,
                    subject=subject,
                    body_html=html_body,
                )
                # Gửi thành công
                state["last_email_sent"]   = datetime.now().strftime("%d/%m/%Y %H:%M")
                state["total_emails_sent"] = state.get("total_emails_sent", 0) + 1
                save_state(state)
                log.info(f"✅ Đã gửi báo cáo đến {to_address} (lần {attempt})")
                append_log(
                    "AUTO_REPLY",
                    f"Gửi đến {to_address} – {len(red_indicators)} chỉ số đỏ"
                    + (f" (thử lại lần {attempt})" if attempt > 1 else ""),
                    "success"
                )
                last_error = None
                break  # Thoát vòng retry

            except Exception as e:
                last_error = e
                log.warning(f"Lần {attempt}/{MAX_RETRY} thất bại: {e}")
                if attempt < MAX_RETRY:
                    log.info(f"Thử lại sau {RETRY_DELAY // 60} phút...")
                    import time
                    time.sleep(RETRY_DELAY)

        # Nếu vẫn thất bại sau tất cả các lần thử
        if last_error:
            log.error(f"❌ Gửi báo cáo thất bại sau {MAX_RETRY} lần: {last_error}")
            append_log("AUTO_REPLY", f"Thất bại sau {MAX_RETRY} lần thử: {str(last_error)}", "error")

            # Gửi email cảnh báo cho Admin
            _send_failure_alert(email_cfg, str(last_error), to_address, len(red_indicators))

    except Exception as e:
        log.error(f"Lỗi nghiêm trọng trong job_send_report: {e}")
        append_log("AUTO_REPLY", f"Lỗi nghiêm trọng: {str(e)}", "error")


def _send_failure_alert(email_cfg: dict, error_msg: str, to_address: str, indicator_count: int):
    """Gửi email cảnh báo cho Admin khi gửi báo cáo thất bại hoàn toàn."""
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#F4F6F9;margin:0;padding:0;">
<div style="max-width:520px;margin:24px auto;background:white;border-radius:10px;overflow:hidden;">
  <div style="background:#B71C1C;padding:20px 28px;">
    <h1 style="margin:0;color:white;font-size:17px;">❌ Gửi báo cáo SOC thất bại!</h1>
    <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:12px;">{now_str}</p>
  </div>
  <div style="padding:24px 28px;">
    <p style="color:#333;font-size:14px;margin:0 0 16px;">
      Hệ thống đã thử gửi báo cáo <strong>3 lần</strong> nhưng đều thất bại.
      Vui lòng vào app và gửi thủ công ngay!
    </p>
    <div style="background:#FFEBEE;border-left:4px solid #B71C1C;padding:12px 16px;border-radius:3px;margin-bottom:16px;">
      <p style="margin:0;font-size:12px;color:#B71C1C;font-weight:700;">Lỗi:</p>
      <p style="margin:6px 0 0;font-size:12px;color:#555;">{error_msg}</p>
    </div>
    <p style="font-size:13px;color:#555;margin:0;">
      📤 Gửi tới: <strong>{to_address}</strong><br>
      🔴 Số chỉ số đỏ: <strong>{indicator_count}</strong>
    </p>
    <div style="margin-top:20px;padding:14px;background:#FFF3E0;border-radius:4px;border-left:3px solid #FF6F00;">
      <p style="margin:0;font-size:13px;color:#E65100;">
        ⚡ <strong>Hành động:</strong> Vào SOC Automation → Gửi Email → Gửi Email Ngay
      </p>
    </div>
  </div>
</div>
</body></html>"""
    try:
        from utils.email_utils import send_reply_email
        send_reply_email(
            smtp_server=email_cfg.get("smtp_server", "smtp.gmail.com"),
            address=email_cfg["address"],
            password=email_cfg["password"],
            to_address=email_cfg["address"],
            subject=f"❌ [SOC-HUE] Gửi báo cáo thất bại – Xử lý ngay! ({datetime.now().strftime('%d/%m/%Y %H:%M')})",
            body_html=html,
        )
        log.info(f"✅ Đã gửi cảnh báo thất bại đến Admin: {email_cfg['address']}")
        append_log("FAILURE_ALERT", f"Cảnh báo gửi thất bại → Admin {email_cfg['address']}", "warning")
    except Exception as e:
        log.error(f"Không thể gửi cảnh báo thất bại: {e}")


def job_send_reminder():
    """
    JOB 4: Gửi email nhắc nhở đến Admin lúc 11:15 (30 phút trước deadline).
    Chỉ gửi nếu hôm nay đã nhận email SOC và có chỉ số đỏ.
    """
    log.info("=== JOB: SEND REMINDER ===")
    config    = load_config()
    state     = load_state()
    email_cfg = config.get("email", {})

    # Chỉ nhắc nếu hôm nay có email SOC
    today_str      = date.today().strftime("%d/%m/%Y")
    last_scan_date = state.get("last_scan_date", "")
    if last_scan_date != today_str:
        log.info("Hôm nay chưa có email SOC. Bỏ qua nhắc nhở.")
        return

    red_indicators = state.get("red_indicators", [])
    if not red_indicators:
        log.info("Không có chỉ số đỏ. Bỏ qua nhắc nhở.")
        return

    if not email_cfg.get("address") or not email_cfg.get("password"):
        log.warning("Email chưa cấu hình.")
        return

    # Lấy giờ deadline từ config
    sched_cfg = config.get("scheduler", {})
    deadline_h = sched_cfg.get("reply_deadline_hour", 11)
    deadline_m = sched_cfg.get("reply_deadline_minute", 45)
    deadline_str = f"{deadline_h:02d}:{deadline_m:02d}"

    # Danh sách chỉ số đỏ dạng HTML
    indicators_html = "".join(
        f'<li style="margin:4px 0; color:#C62828; font-weight:600;">{ind}</li>'
        for ind in red_indicators
    )

    html_body = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#F4F6F9;font-family:'Segoe UI',Arial,sans-serif;">
<div style="max-width:560px;margin:24px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
  <div style="background:linear-gradient(135deg,#E65100 0%,#BF360C 100%);padding:24px 32px;">
    <h1 style="margin:0;color:white;font-size:18px;font-weight:700;">⚠️ Nhắc nhở Deadline SOC</h1>
    <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:13px;">
      Chi nhánh HUE · Ngày {today_str}
    </p>
  </div>
  <div style="padding:28px 32px;">
    <p style="font-size:15px;color:#333;line-height:1.6;margin:0 0 20px;">
      ⚠️ Còn 30 phút đến deadline! Hãy kiểm tra Email trên hệ thống SOC trước <strong>{deadline_str}</strong>.
    </p>
    <div style="background:#FFF5F5;border-left:4px solid #C62828;border-radius:4px;padding:16px 20px;margin-bottom:20px;">
      <p style="margin:0 0 10px;font-size:13px;font-weight:700;color:#C62828;text-transform:uppercase;letter-spacing:1px;">
        Chỉ số đỏ cần giải trình hôm nay:
      </p>
      <ul style="margin:0;padding-left:20px;">
        {indicators_html}
      </ul>
    </div>
    <p style="font-size:13px;color:#888;margin:0;">
      Vui lòng vào <strong>SOC Automation</strong> → <strong>Gửi Email</strong> → kiểm tra nội dung và gửi đi trước {deadline_str}.
    </p>
  </div>
  <div style="background:#F9FAFB;padding:14px 32px;border-top:1px solid #EEE;text-align:center;">
    <p style="margin:0;font-size:11px;color:#AAA;">
      Email tự động · SOC Automation · Chi nhánh HUE · {datetime.now().strftime('%d/%m/%Y %H:%M')}
    </p>
  </div>
</div>
</body></html>"""

    try:
        from utils.email_utils import send_reply_email
        send_reply_email(
            smtp_server=email_cfg.get("smtp_server", "smtp.gmail.com"),
            address=email_cfg["address"],
            password=email_cfg["password"],
            to_address=email_cfg["address"],  # Gửi cho chính Admin
            subject=f"⚠️ [SOC-HUE] Nhắc nhở: Còn 30 phút đến deadline {deadline_str} – {today_str}",
            body_html=html_body,
        )
        log.info(f"✅ Đã gửi nhắc nhở đến {email_cfg['address']}")
        append_log("REMINDER", f"Nhắc nhở deadline {deadline_str} – {len(red_indicators)} chỉ số đỏ", "success")
    except Exception as e:
        log.error(f"Lỗi gửi nhắc nhở: {e}")
        append_log("REMINDER", f"Lỗi gửi nhắc nhở: {str(e)}", "error")


def get_schedule_config():
    """Đọc cấu hình lịch từ file — dùng khi reschedule."""
    config     = load_config()
    sched_cfg  = config.get("scheduler", {})
    return (
        sched_cfg.get("scan_interval_minutes", 30),
        sched_cfg.get("reply_deadline_hour", 11),
        sched_cfg.get("reply_deadline_minute", 45),
    )


def job_check_and_reschedule(scheduler):
    """
    JOB 3: Kiểm tra mỗi 5 phút xem sếp có đổi giờ gửi trên app không.
    Nếu có → tự động cập nhật lịch mà không cần restart.
    """
    scan_interval, reply_h, reply_m = get_schedule_config()

    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    # Cập nhật giờ gửi báo cáo
    scheduler.reschedule_job(
        "send_report",
        trigger=CronTrigger(hour=reply_h, minute=reply_m, timezone="Asia/Ho_Chi_Minh")
    )
    # Cập nhật interval quét email
    scheduler.reschedule_job(
        "scan_email",
        trigger=IntervalTrigger(minutes=scan_interval)
    )
    # Cập nhật giờ nhắc nhở (30 phút trước deadline)
    reminder_h = reply_h
    reminder_m = reply_m - 30
    if reminder_m < 0:
        reminder_h -= 1
        reminder_m += 60
    scheduler.reschedule_job(
        "send_reminder",
        trigger=CronTrigger(hour=reminder_h, minute=reminder_m, timezone="Asia/Ho_Chi_Minh")
    )
    log.debug(f"Config reloaded: quét mỗi {scan_interval}p, nhắc {reminder_h:02d}:{reminder_m:02d}, gửi lúc {reply_h:02d}:{reply_m:02d}")


def main():
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.error("APScheduler chưa cài. Chạy: pip install apscheduler")
        return

    scan_interval, reply_h, reply_m = get_schedule_config()

    scheduler = BlockingScheduler(timezone="Asia/Ho_Chi_Minh")

    # Job 1: Quét email định kỳ
    scheduler.add_job(
        job_scan_email,
        trigger=IntervalTrigger(minutes=scan_interval),
        id="scan_email",
        name="Quét Email SOC",
        replace_existing=True,
    )

    # Job 2: Gửi báo cáo hàng ngày
    scheduler.add_job(
        job_send_report,
        trigger=CronTrigger(hour=reply_h, minute=reply_m, timezone="Asia/Ho_Chi_Minh"),
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

    # Job 4: Nhắc nhở Admin 30 phút trước deadline (mặc định 11:15)
    reminder_h = reply_h
    reminder_m = reply_m - 30
    if reminder_m < 0:
        reminder_h -= 1
        reminder_m += 60
    scheduler.add_job(
        job_send_reminder,
        trigger=CronTrigger(hour=reminder_h, minute=reminder_m, timezone="Asia/Ho_Chi_Minh"),
        id="send_reminder",
        name="Nhắc nhở Deadline",
        replace_existing=True,
    )

    log.info("=" * 50)
    log.info("SOC Scheduler khởi động")
    log.info(f"  Quét email  : mỗi {scan_interval} phút")
    log.info(f"  Nhắc nhở    : {reminder_h:02d}:{reminder_m:02d} hàng ngày (30p trước deadline)")
    log.info(f"  Gửi báo cáo : {reply_h:02d}:{reply_m:02d} hàng ngày")
    log.info(f"  Reload config: mỗi 5 phút")
    log.info("=" * 50)

    # Quét ngay khi khởi động
    job_scan_email()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler đã dừng.")


if __name__ == "__main__":
    main()