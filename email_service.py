# email_service.py
# صف و Worker برای ارسال ایمیل به صورت مقاوم در برابر قطع اینترنت

import os
import time
import traceback
from queue import Queue, Empty
from email.message import EmailMessage
import smtplib

from config import Config

# صف ایمیل‌ها
email_queue: Queue = Queue()


def enqueue_email(subject: str, body: str,
                  attachment_path: str = None,
                  attachment_filename: str = None):
    """
    این تابع را در بقیه کدها صدا می‌زنیم.
    فقط ایمیل را در صف می‌گذارد، ارسال در worker انجام می‌شود.
    """
    task = {
        "subject": subject,
        "body": body,
        "attachment_path": attachment_path,
        "attachment_filename": attachment_filename,
    }
    email_queue.put(task)
    print(f"📥 Email enqueued: {subject}")


def _send_email_via_smtp(subject: str, body: str,
                         attachment_path: str = None,
                         attachment_filename: str = None) -> bool:
    """
    ارسال واقعی ایمیل از طریق SMTP بر اساس تنظیمات Config.
    خروجی: True اگر موفق، False اگر ناموفق.
    """
    try:
        if not Config.MAIL_SERVER or not Config.MAIL_USERNAME or not Config.MAIL_PASSWORD:
            print("⚠️ ایمیل تنظیم نشده است (MAIL_SERVER / MAIL_USERNAME / MAIL_PASSWORD).")
            return False

        if not Config.ADMINS:
            print("⚠️ لیست ADMINS خالی است؛ ایمیلی برای کسی ارسال نشد.")
            return False

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = Config.MAIL_USERNAME
        msg["To"] = ", ".join(Config.ADMINS)
        msg.set_content(body)

        # اگر فایل پیوست داریم (مثلاً اکسل خلاصه روزانه)
        if attachment_path:
            try:
                with open(attachment_path, "rb") as f:
                    file_data = f.read()
                filename = attachment_filename or os.path.basename(attachment_path)
                msg.add_attachment(
                    file_data,
                    maintype="application",
                    subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    filename=filename,
                )
            except Exception as e:
                print(f"⚠️ خطا در خواندن فایل پیوست ایمیل: {e}")
                traceback.print_exc()
                # اگر پیوست خراب بود، حداقل ایمیل بدون فایل برود
                # پس اینجا return False نمی‌کنیم

        # اتصال به SMTP
        with smtplib.SMTP(Config.MAIL_SERVER, Config.MAIL_PORT) as server:
            if getattr(Config, "MAIL_USE_TLS", False):
                server.starttls()
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.send_message(msg)

        print("✅ ایمیل با موفقیت ارسال شد.")
        return True

    except Exception as e:
        print(f"❌ خطا در _send_email_via_smtp: {e}")
        traceback.print_exc()
        return False


def email_worker():
    """
    Worker اصلی ایمیل:
    - از صف می‌خواند
    - سعی می‌کند ایمیل را بفرستد
    - اگر خطا شد، بعد از کمی تأخیر دوباره در صف می‌گذارد
    """
    print("📧 Email worker started ...")

    while True:
        try:
            # منتظر ایمیل جدید در صف
            task = email_queue.get(timeout=5)
        except Empty:
            # اگر صف خالی بود کمی صبر کن
            time.sleep(1)
            continue

        try:
            subject = task.get("subject")
            body = task.get("body")
            attachment_path = task.get("attachment_path")
            attachment_filename = task.get("attachment_filename")

            ok = _send_email_via_smtp(
                subject=subject,
                body=body,
                attachment_path=attachment_path,
                attachment_filename=attachment_filename,
            )

            if ok:
                print(f"✅ Email sent and removed from queue: {subject}")
                email_queue.task_done()
            else:
                # اگر ارسال ناموفق بود، دوباره در صف می‌گذاریم
                print(f"⚠️ Email send failed, will retry later: {subject}")
                time.sleep(10)
                email_queue.put(task)

        except Exception as e:
            print(f"❌ Exception in email_worker: {e}")
            traceback.print_exc()
            # دوباره در صف بگذار با کمی تأخیر
            time.sleep(10)
            email_queue.put(task)
