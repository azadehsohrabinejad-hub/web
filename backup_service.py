"""پشتیبان‌گیری خودکار، مستقل از مسیر نصب برنامه."""
import csv
import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from models import ShiftRecord
from bale_service import send_to_bale_async


BACKUP_COLUMNS = [
    ('row_number', 'ردیف'), ('date', 'تاریخ'), ('shift', 'شیفت'),
    ('location', 'لوکیشن'), ('network_name', 'نام شبکه'),
    ('activity', 'فعالیت'), ('deliverer', 'تحویل‌دهنده'),
    ('receiver', 'تحویل‌گیرنده'), ('signal_time', 'ساعت دریافت سیگنال'),
    ('start_time', 'ساعت شروع'), ('end_time', 'ساعت پایان'),
    ('duration', 'مدت زمان'), ('via_method', 'از طریق'),
    ('transmission_line', 'خط ارسالی'), ('shift_staff', 'پرسنل شیفت'),
    ('description', 'توضیحات'), ('comments', 'کامنت'),
    ('admin_reply', 'پاسخ ادمین'), ('created_by', 'کاربر ثبت‌کننده'),
    ('created_at', 'زمان ثبت')
]


def _backup_root(app_obj):
    path = Path(app_obj.root_path) / 'backups'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cleanup_old_files(folder, days):
    cutoff = datetime.now() - timedelta(days=days)
    for path in Path(folder).glob('*'):
        if path.is_file() and datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
            try:
                path.unlink()
            except OSError:
                pass


def create_daily_csv_and_send(app_obj):
    """هر روز خروجی کامل رکوردها را با UTF-8 مناسب Excel به بله می‌فرستد."""
    with app_obj.app_context():
        daily_dir = _backup_root(app_obj) / 'daily_csv'
        daily_dir.mkdir(parents=True, exist_ok=True)
        filename = f"reports_full_backup_{datetime.now():%Y-%m-%d_%H-%M-%S}.csv"
        output_path = daily_dir / filename

        records = ShiftRecord.query.order_by(ShiftRecord.id).all()
        with output_path.open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.writer(stream)
            writer.writerow([label for _, label in BACKUP_COLUMNS])
            for record in records:
                writer.writerow([
                    getattr(record, key, '') if getattr(record, key, None) is not None else ''
                    for key, _ in BACKUP_COLUMNS
                ])

        send_to_bale_async(
            type='document',
            file_path=str(output_path),
            filename=filename,
            caption=f"پشتیبان روزانه کامل سامانه - {datetime.now():%Y-%m-%d} - تعداد رکورد: {len(records)}"
        )
        _cleanup_old_files(daily_dir, days=14)
        app_obj.logger.info(f"Daily CSV backup queued for Bale: {output_path}")


def create_weekly_database_backup(app_obj):
    """نسخه سازگار SQLite را هفته‌ای یک بار در ویندوز نگه می‌دارد."""
    with app_obj.app_context():
        weekly_dir = _backup_root(app_obj) / 'weekly_database'
        weekly_dir.mkdir(parents=True, exist_ok=True)
        output_path = weekly_dir / f"shifts_database_{datetime.now():%Y-%m-%d_%H-%M-%S}.db"

        database_path = app_obj.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '', 1)
        database_path = os.path.abspath(database_path)
        source = sqlite3.connect(database_path)
        destination = sqlite3.connect(str(output_path))
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()

        _cleanup_old_files(weekly_dir, days=180)
        app_obj.logger.info(f"Weekly SQLite backup created: {output_path}")

