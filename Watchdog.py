"""
watchdog.py
Giám sát scheduler_runner.py, tự động khởi động lại nếu bị crash.

Chạy: python watchdog.py
"""
import subprocess
import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(message)s",
    handlers=[
        logging.FileHandler("soc_watchdog.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

LOG_FILE     = Path("config/logs.json")
MAX_RESTARTS = 10       # Tối đa restart trong 1 ngày
RESTART_DELAY = 30      # Giây chờ trước khi restart


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


def run():
    scheduler_script = Path(__file__).parent / "scheduler_runner.py"
    python_exe       = sys.executable  # Dùng đúng Python của venv hiện tại

    restart_count = 0
    restart_date  = datetime.now().date()

    log.info("=" * 50)
    log.info("SOC Watchdog khởi động")
    log.info(f"  Giám sát: {scheduler_script}")
    log.info(f"  Python  : {python_exe}")
    log.info(f"  Max restart/ngày: {MAX_RESTARTS}")
    log.info("=" * 50)

    while True:
        # Reset đếm restart mỗi ngày mới
        today = datetime.now().date()
        if today != restart_date:
            restart_date  = today
            restart_count = 0
            log.info("Ngày mới – reset đếm restart.")

        # Kiểm tra giới hạn restart
        if restart_count >= MAX_RESTARTS:
            msg = f"Đã restart {MAX_RESTARTS} lần trong ngày. Dừng watchdog để tránh vòng lặp vô hạn."
            log.error(msg)
            append_log("WATCHDOG", msg, "error")
            break

        log.info(f"▶ Khởi động scheduler (lần {restart_count + 1} hôm nay)...")
        append_log(
            "WATCHDOG",
            f"Khởi động scheduler (restart #{restart_count + 1})" if restart_count > 0 else "Khởi động scheduler lần đầu",
            "success" if restart_count == 0 else "warning"
        )

        try:
            # Chạy scheduler_runner.py như subprocess
            process = subprocess.Popen(
                [python_exe, str(scheduler_script)],
                cwd=str(Path(__file__).parent),
            )
            exit_code = process.wait()  # Chờ đến khi process kết thúc

        except Exception as e:
            log.error(f"Không thể khởi động scheduler: {e}")
            append_log("WATCHDOG", f"Lỗi khởi động: {str(e)}", "error")
            exit_code = -1

        restart_count += 1

        if exit_code == 0:
            # Thoát bình thường (Ctrl+C) → dừng watchdog
            log.info("Scheduler thoát bình thường. Watchdog dừng.")
            append_log("WATCHDOG", "Scheduler thoát bình thường", "success")
            break
        else:
            # Crash → chờ rồi restart
            msg = f"Scheduler crash (exit code {exit_code}). Restart sau {RESTART_DELAY}s..."
            log.warning(msg)
            append_log("WATCHDOG", msg, "warning")
            time.sleep(RESTART_DELAY)


if __name__ == "__main__":
    run()