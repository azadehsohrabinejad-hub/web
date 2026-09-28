import socket
import json
import threading
import requests  # برای ارسال درخواست به بله
import jdatetime
from datetime import datetime
from models import db, ShiftRecord

# --- تابع کمکی برای ارسال به بله ---
def send_to_bale(app, message):
    """ارسال پیام به بله در یک ترد جداگانه (تا وقفه ایجاد نشود)"""
    def _send():
        token = app.config.get('BALE_TOKEN')
        chat_id = app.config.get('BALE_CHAT_ID')
        
        if not token or not chat_id:
            app.logger.warning("⚠️ توکن یا چت‌آیدی بله تنظیم نشده است.")
            return

        url = f"https://tapi.bale.ai/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message
        }
        try:
            requests.post(url, json=payload, timeout=5)
            # اینجا لاگ نمی‌کنیم که دوباره فایل لاگ قفل نشود، یا از print استفاده می‌کنیم
            print("✅ پیام به بله ارسال شد.")
        except Exception as e:
            print(f"❌ خطا در ارسال به بله: {e}")

    # اجرای ارسال در ترد جدید
    threading.Thread(target=_send).start()

# --- توابع اصلی سرور ---
def calculate_shift():
    hour = datetime.now().hour
    if 7 <= hour < 15: return "صبح"
    elif 15 <= hour < 23: return "عصر"
    else: return "شب"

# --- تابع جایگزین شده ---
def handle_client_connection(client_socket, client_address, app):
    client_ip = client_address[0]
    app.logger.info(f"🔌 اتصال از: {client_ip}")

    try:
        request = client_socket.recv(4096)
        if not request: return
        
        data_str = request.decode('utf-8')
        payload = json.loads(data_str)
        
        # بررسی رمز
        if payload.get("secret_key") != app.config.get('ALARM_SECRET_KEY'):
            app.logger.warning(f"⛔ رمز اشتباه از {client_ip}")
            return

        with app.app_context():
            # استخراج داده‌ها
            net_name = payload.get("network_name", "نامشخص")
            act_name = payload.get("activity", "قطعی صدا")
            duration = payload.get("duration", "00:00:00")
            s_time = payload.get("start_time", "--:--:--") # دریافت ساعت شروع
            e_time = payload.get("end_time", "--:--:--")   # دریافت ساعت پایان
            
            # محاسبات برای دیتابیس
            last_record = ShiftRecord.query.order_by(ShiftRecord.id.desc()).first()
            new_row_num = (last_record.row_number + 1) if last_record else 1
            today_date = jdatetime.date.today().strftime("%Y/%m/%d")

            # ثبت رکورد
            new_record = ShiftRecord(
                row_number=new_row_num,
                date=today_date,
                shift=calculate_shift(),
                network_name=net_name,
                activity=act_name,
                start_time=s_time,  # ذخیره در دیتابیس
                end_time=e_time,    # ذخیره در دیتابیس
                duration=duration,
                description=f"ثبت خودکار آلارم",
                created_by=f"Alarm ({client_ip})",
                
                # فیلدهای خالی
                location="", deliverer="", receiver="", signal_time="", 
                via_method="", transmission_line="", shift_staff=""
            )

            db.session.add(new_record)
            db.session.commit()
            
            app.logger.info(f"✅ آلارم ثبت شد: {net_name} - {act_name}")

            # --- ارسال پیام اصلاح شده به بله ---
            bale_message = (
                f"🚨 **هشدار جدید سیستم مانیتورینگ**\n\n"
                f"📺 شبکه: {net_name}\n"
                f"⚠️ رویداد: {act_name}\n"
                f"⏰ **ساعت شروع:** {s_time}\n"  # <--- اضافه شد
                f"🏁 ساعت پایان: {e_time}\n"    # <--- اضافه شد
                f"⏱ مدت: {duration}\n"
                f"📅 تاریخ: {today_date}\n"
                f"💾 وضعیت: ثبت شده در سیستم"
            )
            send_to_bale(app, bale_message)
            # -----------------------------------

    except Exception as e:
        app.logger.error(f"❌ خطا: {e}")
        with app.app_context():
            db.session.rollback()
    finally:
        client_socket.close()

def init_tcp_server(app):
    server_ip = '0.0.0.0'
    server_port = 9999
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((server_ip, server_port))
        server.listen(5)
        app.logger.info(f"📡 TCP Server listening on {server_port}")

        while True:
            client, addr = server.accept()
            t = threading.Thread(target=handle_client_connection, args=(client, addr, app))
            t.daemon = True
            t.start()
    except Exception as e:
        app.logger.error(f"❌ TCP Server Failed: {e}")