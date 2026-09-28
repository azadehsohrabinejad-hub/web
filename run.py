# run.py
import os
import sys
import webbrowser
import threading
import time
from app import create_app

# تابعی برای پیدا کردن مسیر اصلی برنامه (چه به صورت اسکریپت و چه به صورت exe)
def get_application_path():
    """مسیر پوشه‌ای که فایل اجرایی در آن قرار دارد را برمی‌گرداند."""
    if getattr(sys, 'frozen', False):
        # اگر برنامه به صورت فایل exe بسته‌بندی شده است
        return os.path.dirname(sys.executable)
    else:
        # اگر برنامه به صورت اسکریپت پایتون اجرا می‌شود
        return os.path.dirname(os.path.abspath(__file__))

def open_browser():
    """باز کردن مرورگر پس از کمی تأخیر"""
    time.sleep(1.5)
    try:
        webbrowser.open('http://127.0.0.1:5000')
    except Exception as e:
        print(f"Could not open browser: {e}")

def main():
    try:
        # پیدا کردن مسیر اصلی برنامه
        app_root_path = get_application_path()
        
        # ساخت مسیر مطلق برای پوشه instance
        instance_path = os.path.join(app_root_path, 'instance')
        if not os.path.exists(instance_path):
            os.makedirs(instance_path)
        
        # ایجاد اپلیکیشن Flask با ارسال مسیر instance
        app = create_app(instance_path=instance_path)
        
        # اجرای مرورگر در یک ترد جداگانه
        threading.Thread(target=open_browser, daemon=True).start()
        
        # اجرای اپلیکیشن Flask
        app.run(debug=False, host='127.0.0.1', port=5000, use_reloader=False)

    except Exception as e:
        error_message = f"خطا در راه‌اندازی برنامه:\n\n{str(e)}"
        print(error_message)
        try:
            from tkinter import messagebox
            messagebox.showerror("خطا در اجرای برنامه", error_message)
        except ImportError:
            pass
        sys.exit(1)

if __name__ == '__main__':
    main()