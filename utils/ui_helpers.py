"""
utils/ui_helpers.py
Hàm tiện ích UI dùng chung — tách ra để tránh copy-paste giữa app.py và login.py.
"""
import base64

from utils.constants import ROOT_DIR


def get_logo_b64() -> str:
    """
    Đọc logo.png từ thư mục gốc dự án, trả về chuỗi base64 để nhúng vào HTML.
    Trả về "" nếu không tìm thấy file (UI sẽ tự ẩn logo, không lỗi).
    """
    for p in [
        ROOT_DIR / "logo.png",
        ROOT_DIR / "assets" / "logo.png",
    ]:
        if p.exists():
            return base64.b64encode(p.read_bytes()).decode()
    return ""