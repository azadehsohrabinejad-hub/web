# app.py - نسخه اصلاح شده و پایدار

import os
import sys
import logging
import threading
import codecs
from logging.handlers import TimedRotatingFileHandler
from flask import Flask
from flask_login import LoginManager
from dotenv import load_dotenv
from sqlalchemy import inspect, text

# --- تنظیمات اولیه محیطی ---

# پیدا کردن مسیر ریشه پروژه
basedir = os.path.abspath(os.path.dirname(__file__))

# مسیر موقت Matplotlib نسبت به محل خود برنامه ساخته می‌شود.
# در C:\web مقدار آن C:\web\temp\matplotlib_config خواهد بود.
os.environ['MPLCONFIGDIR'] = os.path.join(basedir, 'temp', 'matplotlib_config')
os.makedirs(os.environ['MPLCONFIGDIR'], exist_ok=True)

# حل مشکل نمایش کاراکترهای فارسی در کنسول ویندوز
if sys.platform.startswith('win') and os.getenv('WSGI_HANDLER') is None:
    try:
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
    except Exception as e:
        print(f"Warning: Could not configure UTF-8 stdout/stderr: {e}")

# بارگذاری متغیرهای محیطی از فایل .env
load_dotenv()

# --- ایمپورت ماژول‌های داخلی ---
# نکته: ایمپورت‌ها بعد از load_dotenv و تنظیمات محیطی باشند
from models import db, User, Network, Staff, Activity
from routes import main_bp
from api_routes import api_bp  # اضافه کردن ایمپورت api_bp
from alarm_server import init_tcp_server
from scheduler import start_scheduler
from bale_service import bale_worker


def init_db_data(app):
    """پر کردن جداول با داده‌های اولیه در صورت خالی بودن"""
    with app.app_context():
        # داده‌های نمونه فقط در نصب اولیه ساخته می‌شوند. اگر هر کدام از
        # لیست‌ها قبلاً مقدار دارد، حذف‌های ادمین نباید در ری‌استارت برگردند.
        if Network.query.first() or Staff.query.first() or Activity.query.first():
            app.logger.info("Initial lists already exist; seed skipped.")
            return
        # 1. پر کردن جدول شبکه
        _NETWORK_NAMES_RAW = ["ایران", "آوا", "جوان", "پیام", "ورزش", "معارف", "قران", "فرهنگ", "سلامت", "اقتصاد", "گفتگو", "نمایش", "تهران", "صبا", "مناسبتی", "ترتیل", "زیارت", "تلاوت", "برون مرزی", "استان ها"]
        for name in _NETWORK_NAMES_RAW:
            if not Network.query.filter_by(name=name).first():
                db.session.add(Network(name=name))

        # 2. پر کردن جدول پرسنل
        _STAFF = ["انوری", "برزگر", "بهاردل", "بیاتلو", "حیدری", "حمیدی", "خلج", "دائمی", "سهرابی نژاد", "عزتی", "فکری", "فیضی", "قربانی", "محمدیان"]
        for name in _STAFF:
            if not Staff.query.filter_by(name=name).first():
                db.session.add(Staff(name=name))

        # 3. پر کردن جدول فعالیت‌ها
        activity_map = {
            "قطعی صدا": True,
            "سطح پایین صدا": True,
            "سطح بالای صدا": True,
            "قطعی تصویر": True,
            "دیفالت شبکه": False,
            "تغییرکنداکتور": False,
            "تغییر زیرنویس": False,
            "گزارش فعالیت‌های شیفت": False,
            "ارتباط با نودال نه دی": False,
            "آنتی ویروس": False,
            "متفرقه": False
        }
        for name, req_dur in activity_map.items():
            if not Activity.query.filter_by(name=name).first():
                db.session.add(Activity(name=name, requires_duration=req_dur))

        db.session.commit()
        app.logger.info("✅ دیتابیس با داده‌های اولیه (شبکه‌ها، پرسنل، فعالیت‌ها) پر شد.")


def ensure_activity_field_schema(app):
    """افزودن ستون‌های تنظیم فرم بدون نیاز به پاک‌کردن دیتابیس فعلی."""
    with app.app_context():
        columns = {c['name'] for c in inspect(db.engine).get_columns('activity')}
        if 'enabled_fields' not in columns:
            db.session.execute(text('ALTER TABLE activity ADD COLUMN enabled_fields TEXT'))
        if 'required_fields' not in columns:
            db.session.execute(text('ALTER TABLE activity ADD COLUMN required_fields TEXT'))
        db.session.commit()


def create_app(instance_path=None):
    """
    تابع سازنده اپلیکیشن Flask (Factory Pattern)
    """
    app = Flask(__name__, template_folder='templates', static_folder='static')

    # --- تنظیمات کانفیگ ---
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key_change_me')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "shifts.db")}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # تنظیمات بله و آلارم
    app.config['BALE_TOKEN'] = os.getenv('BALE_TOKEN')
    app.config['BALE_CHAT_ID'] = os.getenv('BALE_CHAT_ID')
    app.config['ALARM_SECRET_KEY'] = os.getenv('ALARM_SECRET_KEY')

    # پوشه آپلود
    app.config['UPLOAD_FOLDER'] = 'uploads'
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # --- سیستم لاگ‌گیری (اصلاح شده برای ویندوز) ---
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # استفاده از TimedRotatingFileHandler برای جلوگیری از قفل شدن فایل در ویندوز
    # چرخش لاگ: هر شب ساعت 00:00 (Midnight)
    file_handler = TimedRotatingFileHandler(
        'logs/app.log',
        when='midnight',
        interval=1,
        backupCount=30,  # نگهداری لاگ تا ۳۰ روز
        encoding='utf-8'
    )

    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)

    # پاکسازی هندلرهای پیش‌فرض و افزودن هندلر جدید
    app.logger.handlers.clear()
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Flask application startup')

    # --- راه‌اندازی دیتابیس و لاگین ---
    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = 'main.login'  # نام تابع لاگین در routes.py
    login_manager.login_message = 'لطفاً ابتدا وارد شوید'
    login_manager.login_category = 'warning'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        # db.session.get در SQLAlchemy 2.0+ معادل User.query.get است
        return db.session.get(User, int(user_id))

    # --- کانتکست برنامه و سرویس‌های پس‌زمینه ---
    with app.app_context():
        # ساخت جداول دیتابیس
        try:
            db.create_all()
            ensure_activity_field_schema(app)
            init_db_data(app)  # اضافه کردن تابع مقداردهی اولیه دیتابیس
        except Exception as e:
            app.logger.error(f"Error creating/verifying database tables: {e}")

    # ثبت Blueprint مسیرها
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)  # اضافه کردن api_bp
    app.logger.info("اپلیکیشن Flask با موفقیت ساخته شد.")

    # --- راه‌اندازی تردها (با محافظت Try/Except) ---

    # 1. سرور آلارم TCP
    try:
        tcp_thread = threading.Thread(target=init_tcp_server, args=(app,), daemon=True)
        tcp_thread.start()
        app.logger.info("Service Started: TCP Alarm Server (Port 9999)")
    except Exception as e:
        app.logger.error(f"CRITICAL ERROR: Failed to start TCP Server: {e}")

    # 2. زمان‌بند (Scheduler)
    try:
        # تابع start_scheduler خودش کارهای لازم را انجام می‌دهد
        start_scheduler(app)
        app.logger.info("Service Started: APScheduler (Daily/Weekly Reports & Cleanup)")
    except Exception as e:
        app.logger.error(f"CRITICAL ERROR: Failed to start Scheduler: {e}")

    # 3. ورکر پیام‌رسان بله
    try:
        bale_thread = threading.Thread(target=bale_worker, daemon=True)
        bale_thread.start()
        app.logger.info("Service Started: Bale Messenger Worker")
    except Exception as e:
        app.logger.error(f"CRITICAL ERROR: Failed to start Bale Worker: {e}")

    # --- Context Processors ---
    @app.context_processor
    def inject_now():
        from datetime import datetime
        return {'now': datetime.now()}

    return app


# --- نقطه شروع اجرا ---
if __name__ == "__main__":
    app = create_app()
    print(">>> Starting Flask Server...")
    print(">>> Access at http://localhost:5000")

    # تنظیمات حیاتی برای محیط ویندوز:
    # debug=False برای محیط تولید، debug=True برای محیط توسعه
    # use_reloader=False برای جلوگیری از اجرای دوبار تردها (بسیار مهم)
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,  # در محیط توسعه به True تغییر دهید
        use_reloader=False,
        threaded=True
    )
