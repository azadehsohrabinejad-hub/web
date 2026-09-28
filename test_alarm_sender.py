# test_alarm_sender.py
import socket
import json

# اطلاعات آلارم ساختگی که می‌خواهیم ارسال کنیم
# **تغییر اصلی در این بخش است**
alarm_data = {
    "secret_key": "c7abc1ca6fd59e55847176877f772787",  # کلید مخفی اضافه شد
    "network_name": "ایران",
    "start_time": "14:30:00",  # مقادیر زمانی را هم مطابق مثال جدید آپدیت کردم
    "end_time": "14:45:00",
    "duration": "00:15:00"
}

# تبدیل داده به رشته JSON
json_data = json.dumps(alarm_data)

# اتصال به سرور TCP که روی کامپیوتر خودتان اجرا کرده‌اید
host = '127.0.0.1'  # این آدرس یعنی "همین کامپیوتر"
port = 9999         # همان پورتی که در سرور خود تنظیم کرده‌اید

print(f"در حال ارسال آلارم به {host}:{port}...")
print(f"محتوای پیام: {json_data}")

try:
    # ایجاد سوکت و اتصال به سرور
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        # ارسال داده‌ها به صورت بایت (bytes)
        s.sendall(json_data.encode('utf-8'))
        print("✅ پیام آلارم ساختگی با موفقیت ارسال شد.")
except Exception as e:
    print(f"❌ خطا در ارسال پیام: {e}")
