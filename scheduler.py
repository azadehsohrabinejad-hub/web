# scheduler.py - نسخه نهایی با قابلیت حذف خودکار آلارم‌های ۲۴ ساعته
import time
import os
import atexit
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app

# ایمپورت دیتابیس و مدل رکوردها
from models import db, ShiftRecord

def cleanup_failed_reports(app_obj):
    """
    فایل‌های قدیمی موجود در پوشه failed_reports را پاک می‌کند.
    فایل‌های قدیمی‌تر از ۷ روز حذف می‌شوند.
    """
    with app_obj.app_context():
        folder = 'failed_reports'
        if not os.path.exists(folder):
            return

        current_time = time.time()
        days_limit = 7 * 86400  # 7 روز به ثانیه

        # app_obj.logger.info("--- Starting Cleanup Task for Failed Reports ---") # لاگ غیرضروری حذف شد تا شلوغ نشود
        deleted_count = 0
        
        try:
            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)
                if os.path.isfile(file_path):
                    file_age = current_time - os.path.getmtime(file_path)
                    if file_age > days_limit:
                        os.remove(file_path)
                        deleted_count += 1
                        app_obj.logger.info(f"Deleted old report file: {filename}")
            
            if deleted_count > 0:
                app_obj.logger.info(f"Cleanup finished. Deleted {deleted_count} files.")
        except Exception as e:
            app_obj.logger.error(f"Error during file cleanup: {e}")

def delete_old_alarms_from_db(app_obj):
    """
    حذف رکوردهای آلارم که بیش از ۲۴ ساعت از عمرشان گذشته است.
    شرط حذف:
    1. در توضیحات عبارت 'ثبت خودکار آلارم' باشد.
    2. زمان ایجاد (created_at) قبل از ۲۴ ساعت پیش باشد.
    """
    with app_obj.app_context():
        try:
            # محاسبه زمان ۲۴ ساعت قبل
            # نکته: چون در models.py معمولا از utcnow استفاده می‌شود، اینجا هم utcnow می‌زنیم
            expiration_time = datetime.utcnow() - timedelta(hours=24)
            
            # کوئری برای حذف
            deleted_count = ShiftRecord.query.filter(
                ShiftRecord.description.contains("ثبت خودکار آلارم"), # شرط توضیحات
                ShiftRecord.created_at < expiration_time              # شرط زمان
            ).delete(synchronize_session=False)
            
            if deleted_count > 0:
                db.session.commit()
                app_obj.logger.info(f"🧹 پاکسازی خودکار دیتابیس: {deleted_count} رکورد آلارم قدیمی (۲۴ ساعت گذشته) حذف شد.")
            
            # اگر چیزی حذف نشد، لاگ نمی‌زنیم تا فایل لاگ شلوغ نشود

        except Exception as e:
            app_obj.logger.error(f"❌ خطا در حذف آلارم‌های قدیمی دیتابیس: {e}")
            db.session.rollback()

def scheduled_daily_report(app_obj):
    """
    وظیفه ارسال گزارش روزانه
    """
    with app_obj.app_context():
        try:
            from routes import send_daily_summary_to_bale # ایمپورت تابع اصلی گزارش
            app_obj.logger.info("Starting Daily Report Job...")
            send_daily_summary_to_bale() # اجرای تابع گزارش
            app_obj.logger.info("Daily Report Job Finished.")
        except Exception as e:
            app_obj.logger.error(f"Daily Report Job Failed: {e}")

def scheduled_daily_csv_backup(app_obj):
    try:
        from backup_service import create_daily_csv_and_send
        create_daily_csv_and_send(app_obj)
    except Exception as e:
        app_obj.logger.error(f"Daily CSV backup failed: {e}")

def scheduled_weekly_database_backup(app_obj):
    try:
        from backup_service import create_weekly_database_backup
        create_weekly_database_backup(app_obj)
    except Exception as e:
        app_obj.logger.error(f"Weekly database backup failed: {e}")

def start_scheduler(app):
    """
    راه‌اندازی زمان‌بند و افزودن جاب‌ها
    """
    try:
        # بررسی برای جلوگیری از اجرای تکراری در حالت Debug
        if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            # ساعت همه کارها بر اساس زمان رسمی ایران است، مستقل از تنظیم ویندوز.
            scheduler = BackgroundScheduler(timezone='Asia/Tehran')
            
            # 1. جاب گزارش روزانه (هر شب ساعت ۲۳:۵۹)
            scheduler.add_job(
                func=scheduled_daily_report, 
                args=[app], 
                trigger="cron", 
                hour=23, 
                minute=59,
                id='daily_report_job'
            )

            # 2. جاب پاک‌سازی فایل‌های قدیمی (جمعه‌ها ساعت ۳ صبح)
            scheduler.add_job(
                func=cleanup_failed_reports,
                args=[app],
                trigger="cron",
                day_of_week='fri',
                hour=3,
                minute=0,
                id='cleanup_files_job'
            )

            # 3. جاب جدید: پاک‌سازی آلارم‌های دیتابیس (هر 1 ساعت یک‌بار اجرا می‌شود)
            scheduler.add_job(
                func=delete_old_alarms_from_db,
                args=[app],
                trigger="interval",
                hours=1,  # هر یک ساعت چک می‌کند
                id='db_alarm_cleanup_job'
            )

            # 4. بکاپ کامل CSV و ارسال به بله، هر شب ساعت 23:45
            scheduler.add_job(
                func=scheduled_daily_csv_backup,
                args=[app],
                trigger='cron',
                hour=23,
                minute=45,
                id='daily_csv_backup_job',
                replace_existing=True
            )

            # 5. بکاپ محلی دیتابیس، جمعه‌ها ساعت 02:30
            scheduler.add_job(
                func=scheduled_weekly_database_backup,
                args=[app],
                trigger='cron',
                day_of_week='fri',
                hour=2,
                minute=30,
                id='weekly_database_backup_job',
                replace_existing=True
            )

            scheduler.start()
            app.logger.info("✅ APScheduler Started (Daily Report + File Cleanup + DB Alarm Cleanup)")
            
            # خاموش کردن زمان‌بند هنگام بستن برنامه
            atexit.register(lambda: scheduler.shutdown())
        
    except Exception as e:
        app.logger.error(f"Failed to start scheduler: {e}")
