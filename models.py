# models.py

# --- Section 1: Imports ---
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import jdatetime
import json

# --- Section 2: Database Initialization ---
# ایجاد یک نمونه واحد از دیتابیس
db = SQLAlchemy()

# --- Section 3: Model Definitions ---

class User(UserMixin, db.Model):
    """مدل کاربر برای احراز هویت و مدیریت دسترسی"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='user')  # نقش کاربر: 'admin' یا 'user'
    
    # --- فیلدهای جدید برای سوال امنیتی ---
    security_question = db.Column(db.String(200), nullable=True)
    security_answer = db.Column(db.String(200), nullable=True)

    @property
    def is_admin(self):
        """تشخیص مدیر با پشتیبانی از دیتابیس‌های قدیمی پروژه."""
        role = (self.role or '').strip().lower()
        username = (self.username or '').strip().lower()
        # در نسخه‌های قدیمی، کاربر admin بدون مقدار role ساخته شده بود.
        return role == 'admin' or username == 'admin'

    def __repr__(self):
        return f'<User {self.username}>'

class ShiftRecord(db.Model):
    """مدل برای ذخیره گزارش‌های شیفت"""
    id = db.Column(db.Integer, primary_key=True)
    row_number = db.Column(db.Integer, nullable=False)
    date = db.Column(db.String(10), nullable=False)  # Format: YYYY/MM/DD
    shift = db.Column(db.String(10), nullable=False)
    
    # فیلدهای گزارش شیفت
    location = db.Column(db.String(100))
    network_name = db.Column(db.String(100))
    activity = db.Column(db.String(100), nullable=False)
    deliverer = db.Column(db.String(100))
    receiver = db.Column(db.String(100))
    
    # زمان‌ها
    signal_time = db.Column(db.String(8))  # Format: HH:MM:SS
    start_time = db.Column(db.String(8))   # Format: HH:MM:SS
    end_time = db.Column(db.String(8))     # Format: HH:MM:SS
    duration = db.Column(db.String(8))     # Format: HH:MM:SS
    
    # سایر جزئیات
    via_method = db.Column(db.String(100))
    transmission_line = db.Column(db.String(100))
    shift_staff = db.Column(db.String(500))
    description = db.Column(db.Text, default='')  
    
    # اطلاعات ثبت کننده
    created_by = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # فیلدهای جدید برای کامنت‌ها و پاسخ ادمین
    comments = db.Column(db.Text, nullable=True)
    admin_reply = db.Column(db.Text, nullable=True)
    
    def __repr__(self):
        return f'<ShiftRecord {self.id} - {self.activity}>'

class ShiftChecklist(db.Model):
    """One completed inspection per local Windows-server shift."""
    id = db.Column(db.Integer, primary_key=True)
    shift_start = db.Column(db.DateTime, nullable=False, unique=True, index=True)
    shift_name = db.Column(db.String(10), nullable=False)
    answers = db.Column(db.Text, nullable=False)  # Snapshot of item names and answers.
    temperature = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text, nullable=False, default='')
    created_by = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    @property
    def jalali_date(self):
        return jdatetime.date.fromgregorian(date=self.shift_start.date()).strftime('%Y/%m/%d')

class ShiftChecklistSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    items_json = db.Column(db.Text, nullable=False)

class ShiftChecklistAudit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    checklist_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20), nullable=False)
    snapshot = db.Column(db.Text, nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    actor = db.Column(db.String(80), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

class Network(db.Model):
    """مدل برای ذخیره لیست شبکه‌ها"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    
    def __repr__(self):
        return self.name

class Staff(db.Model):
    """مدل برای ذخیره لیست پرسنل"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    
    def __repr__(self):
        return self.name

class Activity(db.Model):
    """مدل برای ذخیره لیست فعالیت‌ها"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    # فیلد جدید: آیا این فعالیت نیاز به زمان شروع و پایان (duration) دارد؟
    requires_duration = db.Column(db.Boolean, default=False) 
    enabled_fields = db.Column(db.Text, nullable=True)
    required_fields = db.Column(db.Text, nullable=True)

    FORM_FIELDS = [
        'network_name', 'location', 'deliverer', 'receiver', 'via_method',
        'transmission_line', 'signal_time', 'start_time', 'end_time'
    ]

    def get_enabled_fields(self):
        if self.enabled_fields:
            try:
                return [f for f in json.loads(self.enabled_fields) if f in self.FORM_FIELDS]
            except (TypeError, ValueError):
                pass
        # سازگاری با فعالیت‌های قدیمی
        if self.requires_duration:
            return ['network_name', 'start_time', 'end_time']
        if self.name in ['دیفالت شبکه', 'تغییرکنداکتور', 'تغییر زیرنویس']:
            return ['network_name', 'signal_time']
        return list(self.FORM_FIELDS)

    def get_required_fields(self):
        if self.required_fields:
            try:
                enabled = set(self.get_enabled_fields())
                return [f for f in json.loads(self.required_fields) if f in enabled]
            except (TypeError, ValueError):
                pass
        if self.requires_duration:
            return ['network_name', 'start_time', 'end_time']
        if self.name in ['دیفالت شبکه', 'تغییرکنداکتور', 'تغییر زیرنویس']:
            return ['network_name', 'signal_time']
        if self.name == 'ارتباط با نودال نه دی':
            return ['receiver']
        return []

    def set_field_config(self, enabled, required):
        enabled = [f for f in self.FORM_FIELDS if f in enabled]
        required = [f for f in self.FORM_FIELDS if f in required and f in enabled]
        self.enabled_fields = json.dumps(enabled, ensure_ascii=False)
        self.required_fields = json.dumps(required, ensure_ascii=False)
        self.requires_duration = 'start_time' in required and 'end_time' in required
    
    def __repr__(self):
        return self.name

class ConfigItem(db.Model):
    """جدول تنظیمات داینامیک سیستم (مثلاً برای مدیریت لیست‌ها)"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False) # کلید تنظیمات
    value = db.Column(db.Text, nullable=False) # مقدار تنظیمات

    def __repr__(self):
        return f'<ConfigItem {self.key}: {self.value}>'

# --- Section 4: Database Initialization Function ---

def init_db_data(app):
    """پر کردن جداول با داده‌های اولیه در صورت خالی بودن"""
    with app.app_context():
        # بررسی اینکه آیا داده‌ها قبلاً وارد شده‌اند
        if Network.query.first() or Staff.query.first() or Activity.query.first():
            app.logger.info("دیتابیس قبلاً با داده‌های اولیه پر شده است.")
            return  # داده‌ها قبلاً وارد شده‌اند
        
        # پر کردن جدول شبکه‌ها
        networks = [
            "ایران", "آوا", "جوان", "پیام", "ورزش", "معارف", "قران", 
            "فرهنگ", "سلامت", "اقتصاد", "گفتگو", "نمایش", "تهران", 
            "صبا", "مناسبتی", "ترتیل", "زیارت", "تلاوت", "برون مرزی", "استان ها"
        ]
        for name in networks:
            db.session.add(Network(name=name))
        
        # پر کردن جدول پرسنل
        staff = [
            "انوری", "برزگر", "بهاردل", "بیاتلو", "حیدری", "حمیدی", 
            "خلج", "دائمی", "سهرابی نژاد", "عزتی", "فکری", "فیضی", 
            "توکلی", "محمدیان"
        ]
        for name in staff:
            db.session.add(Staff(name=name))
        
        # پر کردن جدول فعالیت‌ها
        activities = [
            ("قطعی صدا", True), 
            ("سطح پایین صدا", True), 
            ("سطح بالای صدا", True), 
            ("گزارش فعالیت‌های شیفت", False),
            ("ارتباط با نودال نه دی", False), 
            ("قطعی تصویر", True), 
            ("دیفالت شبکه", False), 
            ("آنتی ویروس", False), 
            ("تغییرکنداکتور", False), 
            ("تغییر زیرنویس", False), 
            ("متفرقه", False)
        ]
        for name, requires_duration in activities:
            db.session.add(Activity(name=name, requires_duration=requires_duration))
        
        db.session.commit()
        app.logger.info("✅ دیتابیس با داده‌های اولیه (شبکه‌ها، پرسنل، فعالیت‌ها) پر شد.")
