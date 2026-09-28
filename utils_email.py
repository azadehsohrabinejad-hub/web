# utils_email.py
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from config import Config


def send_email_to_admins(subject: str, body: str, attachment_path: str | None = None) -> bool:
    """
    ارسال ایمیل به همه‌ی ADMINS (لیست صحیح از config.py)
    اگر attachment وجود داشته باشد، ضمیمه می‌شود.
    """

    # بررسی اطلاعات SMTP
    if not Config.MAIL_USERNAME or not Config.MAIL_PASSWORD:
        print("⚠️ اطلاعات SMTP تنظیم نشده‌اند. ایمیل ارسال نشد.")
        return False

    admins_list = Config.ADMINS
    if not admins_list:
        print("⚠️ ADMINS در فایل .env خالی است.")
        return False

    try:
        # ساخت پیام ایمیل
        msg = MIMEMultipart()
        msg["From"] = Config.MAIL_USERNAME
        msg["To"] = ", ".join(admins_list)
        msg["Subject"] = subject

        # متن ایمیل
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # اضافه کردن ضمیمه (اختیاری)
        if attachment_path:
            try:
                filename = os.path.basename(attachment_path)
                with open(attachment_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                msg.attach(part)
            except Exception as e:
                print(f"⚠️ خطا در ضمیمه: {e}")

        # ارسال ایمیل
        with smtplib.SMTP(Config.MAIL_SERVER, Config.MAIL_PORT) as server:
            if Config.MAIL_USE_TLS:
                server.starttls()
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.sendmail(Config.MAIL_USERNAME, admins_list, msg.as_string())

        print("✅ ایمیل برای تمام مدیران ارسال شد.")
        return True

    except Exception as e:
        print(f"❌ خطا در ارسال ایمیل: {e}")
        return False
