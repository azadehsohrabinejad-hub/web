# export_backup.py
import os
import pandas as pd
from datetime import datetime
from models import db, ShiftRecord
from config import Config

def export_all_records_to_excel(path):
    """
    خروجی کامل گزارش‌ها به فایل Excel
    """
    try:
        all_records = ShiftRecord.query.order_by(ShiftRecord.id.desc()).all()
        
        if not all_records:
            print("⚠️ هیچ گزارشی برای بک‌آپ وجود ندارد.")
            return False

        rows = []
        for r in all_records:
            rows.append({
                'ردیف': r.row_number,
                'تاریخ': r.date,
                'شیفت': r.shift,
                'لوکیشن': r.location or '-',
                'نام شبکه': r.network_name or '-',
                'فعالیت': r.activity or '-',
                'تحویل‌دهنده': r.deliverer or '-',
                'تحویل‌گیرنده': r.receiver or '-',
                'ساعت دریافت سیگنال': r.signal_time or '-',
                'ساعت شروع': r.start_time or '-',
                'ساعت پایان': r.end_time or '-',
                'مدت زمان': r.duration or '-',
                'از طریق': r.via_method or '-',
                'خط ارسالی': r.transmission_line or '-',
                'پرسنل شیفت': r.shift_staff or '-',
                'توضیحات': r.description or '-',
                'کامنت': r.comments or '-',
                'پاسخ ادمین': r.admin_reply or '-',
                'کاربر ثبت‌کننده': r.created_by
            })

        df = pd.DataFrame(rows)
        df.to_excel(path, index=False, engine='openpyxl')
        print(f"✅ فایل اکسل با موفقیت در مسیر {path} ذخیره شد.")
        return True
        
    except Exception as e:
        print(f"❌ خطا در ساخت فایل اکسل: {e}")
        import traceback
        traceback.print_exc()
        return False

def export_daily_records_to_excel(path):
    """
    خروجی گزارش‌های روزانه به فایل Excel
    """
    try:
        from jdatetime import date
        today = date.today().strftime("%Y/%m/%d")
        
        daily_records = ShiftRecord.query.filter_by(date=today).order_by(ShiftRecord.row_number).all()
        
        if not daily_records:
            print(f"⚠️ هیچ گزارشی برای تاریخ {today} وجود ندارد.")
            return False

        rows = []
        for r in daily_records:
            rows.append({
                'ردیف': r.row_number,
                'تاریخ': r.date,
                'شیفت': r.shift,
                'لوکیشن': r.location or '-',
                'نام شبکه': r.network_name or '-',
                'فعالیت': r.activity or '-',
                'تحویل‌دهنده': r.deliverer or '-',
                'تحویل‌گیرنده': r.receiver or '-',
                'ساعت دریافت سیگنال': r.signal_time or '-',
                'ساعت شروع': r.start_time or '-',
                'ساعت پایان': r.end_time or '-',
                'مدت زمان': r.duration or '-',
                'از طریق': r.via_method or '-',
                'خط ارسالی': r.transmission_line or '-',
                'پرسنل شیفت': r.shift_staff or '-',
                'توضیحات': r.description or '-',
                'کامنت': r.comments or '-',
                'پاسخ ادمین': r.admin_reply or '-',
                'کاربر ثبت‌کننده': r.created_by
            })

        df = pd.DataFrame(rows)
        df.to_excel(path, index=False, engine='openpyxl')
        print(f"✅ فایل اکسل روزانه با موفقیت در مسیر {path} ذخیره شد.")
        return True
        
    except Exception as e:
        print(f"❌ خطا در ساخت فایل اکسل روزانه: {e}")
        import traceback
        traceback.print_exc()
        return False

def export_weekly_records_to_excel(path):
    """
    خروجی گزارش‌های هفتگی به فایل Excel
    """
    try:
        from jdatetime import date, timedelta
        
        end_date = date.today()
        start_date = end_date - timedelta(days=6)
        
        start_str = start_date.strftime("%Y/%m/%d")
        end_str = end_date.strftime("%Y/%m/%d")
        
        weekly_records = ShiftRecord.query.filter(
            ShiftRecord.date >= start_str,
            ShiftRecord.date <= end_str
        ).order_by(ShiftRecord.row_number).all()
        
        if not weekly_records:
            print(f"⚠️ هیچ گزارشی برای بازه {start_str} تا {end_str} وجود ندارد.")
            return False

        rows = []
        for r in weekly_records:
            rows.append({
                'ردیف': r.row_number,
                'تاریخ': r.date,
                'شیفت': r.shift,
                'لوکیشن': r.location or '-',
                'نام شبکه': r.network_name or '-',
                'فعالیت': r.activity or '-',
                'تحویل‌دهنده': r.deliverer or '-',
                'تحویل‌گیرنده': r.receiver or '-',
                'ساعت دریافت سیگنال': r.signal_time or '-',
                'ساعت شروع': r.start_time or '-',
                'ساعت پایان': r.end_time or '-',
                'مدت زمان': r.duration or '-',
                'از طریق': r.via_method or '-',
                'خط ارسالی': r.transmission_line or '-',
                'پرسنل شیفت': r.shift_staff or '-',
                'توضیحات': r.description or '-',
                'کامنت': r.comments or '-',
                'پاسخ ادمین': r.admin_reply or '-',
                'کاربر ثبت‌کننده': r.created_by
            })

        df = pd.DataFrame(rows)
        df.to_excel(path, index=False, engine='openpyxl')
        print(f"✅ فایل اکسل هفتگی با موفقیت در مسیر {path} ذخیره شد.")
        return True
        
    except Exception as e:
        print(f"❌ خطا در ساخت فایل اکسل هفتگی: {e}")
        import traceback
        traceback.print_exc()
        return False