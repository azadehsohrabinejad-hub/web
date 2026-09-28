# background.py - نسخه نهایی و تمیز
from app import create_app
from routes import start_tcp_server, start_daily_scheduler
import threading

app = create_app()

with app.app_context():
    print("Background Services شروع شد")
    threading.Thread(target=start_tcp_server, daemon=True).start()
    threading.Thread(target=start_daily_scheduler, daemon=True).start()
    print("TCP Server و Scheduler با موفقیت راه‌اندازی شدند")

# نگه داشتن اسکریپت زنده
try:
    while True:
        pass
except KeyboardInterrupt:
    print("\nمتوقف شد")