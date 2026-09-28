# bale_service.py - اصلاح شده (رفع مشکل قفل فایل لاگ)

import os
import queue
import json
import time
import socket
import threading
import requests
import logging
from logging.handlers import RotatingFileHandler

# ================================
# صف و پوشه
# ================================
MESSAGE_QUEUE = queue.Queue()
APP_ROOT = os.path.abspath(os.path.dirname(__file__))
FAILED_REPORTS_DIR = os.path.join(APP_ROOT, "failed_reports")
os.makedirs(FAILED_REPORTS_DIR, exist_ok=True)

# --- توابع کمکی ---

def has_internet():
    """چک اتصال واقعی به API بله"""
    try:
        requests.head("https://tapi.bale.ai", timeout=3)
        return True
    except:
        return False


def _send_to_bale(token, chat_id, text=None, file_path=None, caption=""):
    """تابع اصلی ارسال به بله با لاگ‌های کامل"""
    print("\n--- _send_to_bale START ---")
    try:
        if text:
            print(f"DEBUG: Sending TEXT message...")
            url = f"https://tapi.bale.ai/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": text}
            response = requests.post(url, json=payload, timeout=15)
            print(f"DEBUG: Response Status: {response.status_code}, Body: {response.text}")
            return response.status_code == 200 and response.json().get("ok")
        if file_path and os.path.exists(file_path):
            print(f"DEBUG: Sending DOCUMENT...")
            url = f"https://tapi.bale.ai/bot{token}/sendDocument"
            with open(file_path, "rb") as f:
                files = {"document": (os.path.basename(file_path), f)}
                data = {"chat_id": chat_id, "caption": caption}
                response = requests.post(url, data=data, files=files, timeout=30)
                print(f"DEBUG: Response Status: {response.status_code}, Body: {response.text}")
                return response.status_code == 200 and response.json().get("ok")
    except Exception as e:
        print(f"--- _send_to_bale CRASHED --- Exception: {e}")
        return False

def send_to_bale_async(type="message", text=None, file_path=None, filename=None, caption=""):
    """این تابع رو همه جا استفاده می‌کنی — با لاگ"""
    item = {"type": type, "text": text, "file_path": file_path, "filename": filename, "caption": caption}
    print(f"DEBUG: Adding item to queue: {item}")
    MESSAGE_QUEUE.put(item)

# ================================
# Worker با لاگ‌های دقیق
# ================================
def bale_worker():
    """این تابع Worker را در یک نخ جداگانه اجرا می‌کند."""
    worker_logger = logging.getLogger('bale_worker')
    
    # جلوگیری از اضافه شدن چندباره هندلرها
    if not worker_logger.handlers:
        if not os.path.exists('logs'):
            os.mkdir('logs')
            
        # --- تغییر مهم: نام فایل را از app.log به bale.log تغییر دادیم ---
        file_handler = RotatingFileHandler('logs/bale.log', maxBytes=10240, backupCount=10, encoding='utf-8')
        
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        worker_logger.addHandler(file_handler)
        worker_logger.setLevel(logging.INFO)

    worker_logger.info("=== Bale Worker Thread Started ===")
    while True:
        try:
            time.sleep(30)
            from config import Config
            token = Config.BALE_TOKEN
            chat_id = Config.BALE_CHAT_ID
            if not token or not chat_id:
                worker_logger.critical("CRITICAL: BALE_TOKEN or BALE_CHAT_ID is not set in Config!")
                time.sleep(60)
                continue
            
            worker_logger.info("DEBUG: Worker is active. Starting main loop.")
            while True:
                while True:
                    try:
                        item = MESSAGE_QUEUE.get_nowait()

                        # ✅ لاگ امن بدون حروف فارسی:
                        safe_type = item.get("type")
                        has_text = bool(item.get("text"))
                        has_file = bool(item.get("file_path"))
                        worker_logger.info(
                            f"DEBUG: Dequeued item (type={safe_type}, has_text={has_text}, has_file={has_file})"
                        )
                        
                        if has_internet():
                            worker_logger.info("DEBUG: Internet is available, attempting to send.")
                            success = False
                            if item.get("type") == "message":
                                success = _send_to_bale(token, chat_id, text=item.get("text"))
                            elif item.get("type") == "document":
                                success = _send_to_bale(
                                    token, chat_id,
                                    file_path=item.get("file_path"),
                                    caption=item.get("caption")
                                )
                            
                            if not success:
                                worker_logger.warning("DEBUG: Sending failed. Saving to failed reports.")
                                fn = f"failed_{int(time.time()*1000000)}.json"
                                with open(os.path.join(FAILED_REPORTS_DIR, fn), "w", encoding="utf-8") as f:
                                    json.dump(item, f, ensure_ascii=False)
                        else:
                            worker_logger.warning("DEBUG: No internet. Saving to failed reports.")
                            fn = f"offline_{int(time.time()*1000000)}.json"
                            with open(os.path.join(FAILED_REPORTS_DIR, fn), "w", encoding="utf-8") as f:
                                json.dump(item, f, ensure_ascii=False)
                        
                        MESSAGE_QUEUE.task_done()
                    except queue.Empty:
                        break
                
                time.sleep(30)
                # تلاش مجدد برای ارسال‌های ناموفق
                if has_internet() and os.path.exists(FAILED_REPORTS_DIR):
                    failed_files = [f for f in os.listdir(FAILED_REPORTS_DIR) if f.endswith(".json")]
                    for f in sorted(failed_files)[:5]:
                        path = os.path.join(FAILED_REPORTS_DIR, f)
                        try:
                            with open(path, "r", encoding="utf-8") as jf:
                                data = json.load(jf)
                            worker_logger.info(f"DEBUG: Retrying failed report: {f}")
                            success = False
                            if data.get("type") == "message":
                                success = _send_to_bale(token, chat_id, text=data.get("text"))
                            elif data.get("type") == "document":
                                success = _send_to_bale(
                                    token, chat_id,
                                    file_path=data.get("file_path"),
                                    caption=data.get("caption")
                                )
                            if success:
                                os.remove(path)
                                worker_logger.info(
                                    f"DEBUG: Successfully sent and removed failed report: {f}"
                                )
                        except Exception as e:
                            worker_logger.error(
                                f"ERROR: Could not process failed report {f}. Error: {e}"
                            )
        except Exception as e:
            worker_logger.critical(f"CRITICAL: Bale worker crashed! Error: {e}")
            import traceback
            worker_logger.critical(traceback.format_exc())
            time.sleep(60)

# ================================
# شروع خودکار Worker موقع ایمپورت ماژول (در صورت نیاز)
# ================================
# اگر می‌خواهید وورکر به محض اجرای برنامه شروع به کار کند، خطوط زیر را از حالت کامنت خارج کنید
# print("Bale Service لود شد — شروع Worker...")
# threading.Thread(target=bale_worker, daemon=True).start()
# print("Bale Worker با موفقیت در پس‌زمینه اجرا شد!")
