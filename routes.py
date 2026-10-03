# routes.py - نسخه بهینه و تمیز شده

# --- Section 1: Imports ---
import socket
import threading
import json
import traceback
import os
import io
import base64
import glob
import sys
import time
import secrets
import hashlib
from datetime import datetime, timedelta
import math
from sqlalchemy.exc import IntegrityError
from urllib.parse import urlparse  # <--- این برای روت login اضافه شد
import jdatetime
import pandas as pd
import numpy as np
import requests
import arabic_reshaper
from bidi.algorithm import get_display
import smtplib
from flask import render_template, Blueprint
from flask import make_response
from flask_login import login_required, current_user
from email.message import EmailMessage
from config import Config
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.font_manager import FontProperties
from flask import current_app, Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from models import db, User, ShiftRecord, ShiftChecklist, ShiftChecklistSettings, ShiftChecklistAudit, ConfigItem, Network, Staff, Activity
from checklist_config import CHECKLIST_ITEMS, ANSWER_LABELS
from bale_service import send_to_bale_async
from functools import wraps
from flask import abort
from utils_email import send_email_to_admins
from email_service import enqueue_email

# --- Section 1.5: Blueprint Definition & Cache Control ---
# 1. اول بلوپرینت تعریف می‌شود
main_bp = Blueprint('main', __name__)

# محافظ تکمیلی در برابر ارسال هم‌زمان/تکراری یک فرم در همین پردازش برنامه.
_submission_lock = threading.Lock()
_used_submission_tokens = {}
_SUBMISSION_TOKEN_TTL = 30 * 60


def _claim_submission_token(token):
    """توکن فرم را فقط یک بار مصرف می‌کند و درخواست‌های تکراری را رد می‌کند."""
    if not token:
        return False

    now = time.time()
    with _submission_lock:
        expired = [key for key, used_at in _used_submission_tokens.items()
                   if now - used_at > _SUBMISSION_TOKEN_TTL]
        for key in expired:
            _used_submission_tokens.pop(key, None)

        if token in _used_submission_tokens:
            return False

        _used_submission_tokens[token] = now
        return True

# 2. حالا تابع after_request به آن متصل می‌شود
@main_bp.after_request
def add_no_cache_headers(response):
    # فقط برای صفحات HTML (تا فایل‌های استاتیک مثل CSS و JS کش شوند تا آفلاین بمانید)
    if 'text/html' in response.headers.get('Content-Type', ''):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# 3. سپس دکوراتورها و سایر توابع تعریف می‌شوند
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function 

from utils_charts import (
    duration_to_seconds, get_persian_text, 
    create_pie_chart_activity, create_timeline_chart, 
    create_network_chart, create_audio_outage_scatter_chart, 
    create_pgm_chart, create_easycaster_chart
)

# تنظیمات Matplotlib مستقل از نام درایو و مسیر نصب
APP_ROOT = os.path.abspath(os.path.dirname(__file__))
os.environ['MPLCONFIGDIR'] = os.path.join(APP_ROOT, 'temp', 'matplotlib_config')
os.makedirs(os.environ['MPLCONFIGDIR'], exist_ok=True)

# --- Section 2: Constants ---
# تابع کمکی برای ایجاد کلید مرتب‌سازی صحیح بر اساس الفبای فارسی
def persian_sort_key(text):
    alphabet_order = "ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی"
    char_map = {char: i for i, char in enumerate(alphabet_order)}
    return tuple(char_map.get(char, len(alphabet_order)) for char in text if isinstance(text, str))

# ثابت‌هایی که پویا نیستند
SHIFTS = ["صبح", "ظهر", "شب"]
VIA_METHODS = ["PGM", "Easy Caster1", "Easy Caster2", "Easy Caster3", "Easy Caster4", "Easy Caster5", "Easy Caster6", "Easy Caster7", "Easy Caster8", "Easy Caster9", "Easy Caster10", "Easy Caster11", "Easy Caster12", "Easy Caster13", "Easy Caster14", "DEMB1-1","DEMB1-2","DEMB1-3","DEMB1-4","DEMB1-5","DEMB1-6","DEMB1-7","DEMB1-8","Stream"]
TRANSMISSION_LINES = ["EMB1-1", "EMB1-2", "EMB1-3", "EMB1-4", "EMB1-5", "EMB1-6", "EMB1-7", "EMB1-8", "EMB2-1", "EMB2-2", "EMB2-3", "EMB2-4", "EMB2-5", "EMB2-6", "EMB2-7", "EMB2-8", "EXT 1", "EXT 2", "EXT 3"]

# --- Section 3: Helper Functions ---
def calculate_duration(start_time, end_time):
    """محاسبه مدت زمان"""
    try:
        if not start_time or not end_time or start_time == "HH:MM:SS" or end_time == "HH:MM:SS":
            return "00:00:00"
        if len(start_time.split(":")) == 2: start_time = f"{start_time}:00"
        if len(end_time.split(":")) == 2: end_time = f"{end_time}:00"
        start = datetime.strptime(start_time, "%H:%M:%S")
        end = datetime.strptime(end_time, "%H:%M:%S")
        if end < start:
            total_seconds = (datetime.strptime("23:59:59", "%H:%M:%S") - start).seconds + (end - datetime.strptime("00:00:00", "%H:%M:%S")).seconds + 1
        else:
            total_seconds = (end - start).seconds
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except:
        return "00:00:00"

def get_jalali_date_range(range_type):
    today = jdatetime.date.today()
    start_date = None
    end_date = today.strftime("%Y/%m/%d")
    if range_type == 'daily': start_date = end_date
    elif range_type == 'weekly': start_date = (today - jdatetime.timedelta(days=6)).strftime("%Y/%m/%d")
    elif range_type == 'monthly': start_date = (today - jdatetime.timedelta(days=29)).strftime("%Y/%m/%d")
    elif range_type == 'yearly': start_date = jdatetime.date(today.year, 1, 1).strftime("%Y/%m/%d")
    return start_date, end_date

def get_current_shift():
    """تعیین شیفت فعلی بر اساس ساعت"""
    current_hour = datetime.now().hour
    if 6 <= current_hour < 14:
        return "صبح"
    elif 14 <= current_hour < 22:
        return "ظهر"
    else:
        return "شب"

def current_checklist_shift(now=None):
    """Use the web server's local clock; 00:00–05:59 belongs to yesterday."""
    now = now or datetime.now()
    if 6 <= now.hour < 14:
        return now.replace(hour=6, minute=0, second=0, microsecond=0), 'صبح'
    if 14 <= now.hour < 22:
        return now.replace(hour=14, minute=0, second=0, microsecond=0), 'ظهر'
    if now.hour >= 22:
        return now.replace(hour=22, minute=0, second=0, microsecond=0), 'شب'
    yesterday = now - timedelta(days=1)
    return yesterday.replace(hour=22, minute=0, second=0, microsecond=0), 'شب'

def checklist_payload(record):
    answers = json.loads(record.answers)
    counts = {key: sum(a['status'] == key for a in answers) for key in ANSWER_LABELS}
    return {
        'id': record.id, 'temperature': record.temperature,
        'created_by': record.created_by, 'created_at': record.created_at.strftime('%H:%M'),
        'answers': answers, 'counts': counts, 'notes': record.notes,
        'revision': checklist_revision(record),
    }

def checklist_revision(record):
    content = f'{record.answers}|{record.temperature}|{record.notes}'
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def checklist_message(record, heading='بازدید شیفت', reason=None):
    answers = json.loads(record.answers)
    counts = checklist_payload(record)['counts']
    date_label = jdatetime.date.fromgregorian(date=record.shift_start.date()).strftime('%Y/%m/%d')
    lines = [f'{heading} {record.shift_name} | {date_label}',
             f'ثبت: {record.created_at:%H:%M} | {record.created_by}',
             f'دمای سرور: {record.temperature:g} °C',
             ' | '.join(f"{next((a.get('status_label', ANSWER_LABELS[key]) for a in answers if a['status'] == key), _assigned_response_labels(0)[key])}: {counts[key]}" for key in ANSWER_LABELS),
             'جزئیات موارد:']
    lines.extend(f"{ {'ok': '✅', 'issue': '❌', 'unknown': '🟡'}.get(a['status'], '🟡') } {a['label']}: {a.get('status_label', ANSWER_LABELS.get(a['status'], a['status']))}" +
                 (f" — {a['note']}" if a.get('note') else '') for a in answers)
    if record.notes:
        lines.append('توضیحات: ' + record.notes)
    if reason:
        lines.append('علت تغییر: ' + reason)
    return '\n'.join(lines)

@main_bp.route('/shift-checklist/<int:record_id>/admin', methods=['POST'])
@login_required
def admin_shift_checklist(record_id):
    if not session.get('checklist_token') or not secrets.compare_digest(request.form.get('token', ''), session['checklist_token']):
        abort(403)
    record = db.session.get(ShiftChecklist, record_id)
    if record is None:
        abort(404)
    if not (current_user.is_admin or record.created_by == current_user.username):
        abort(403)
    if not secrets.compare_digest(request.form.get('revision', ''), checklist_revision(record)):
        flash('بازدید تغییر کرده است؛ صفحه را تازه‌سازی کنید.', 'danger')
        return redirect(url_for('main.records', checklist_page=request.form.get('checklist_page', 1)) + '#shift-inspections')
    action = request.form.get('action')
    reason = request.form.get('reason', '').strip()
    if not 3 <= len(reason) <= 500 or action not in ('edit', 'reset', 'delete'):
        flash('نوع تغییر یا علت آن نامعتبر است.', 'danger')
        return redirect(url_for('main.records') + '#shift-inspections')
    if action == 'reset' and record.shift_start != current_checklist_shift()[0]:
        flash('بازنشانی فقط برای شیفت جاری ممکن است؛ بازدیدهای گذشته را ویرایش کنید.', 'danger')
        return redirect(url_for('main.records') + '#shift-inspections')
    before = {'shift_start': record.shift_start.isoformat(), 'shift_name': record.shift_name,
              'answers': json.loads(record.answers), 'temperature': record.temperature,
              'notes': record.notes, 'created_by': record.created_by, 'created_at': record.created_at.isoformat()}
    db.session.add(ShiftChecklistAudit(checklist_id=record.id, action=action,
        snapshot=json.dumps(before, ensure_ascii=False), reason=reason, actor=current_user.username))
    if action == 'edit':
        answers = json.loads(record.answers)
        for item in answers:
            status = request.form.get('status_' + str(item['id']))
            note = request.form.get('note_' + str(item['id']), '').strip()
            if status not in ANSWER_LABELS or len(note) > 500 or (status == 'issue' and not note):
                db.session.rollback()
                flash('وضعیت یا توضیح یکی از موارد نامعتبر است.', 'danger')
                return redirect(url_for('main.records') + '#shift-inspections')
            item['status'], item['note'] = status, note
            item['status_label'] = _assigned_response_labels(0)[status]
        try:
            temperature = float(request.form.get('temperature', '').replace('٫', '.'))
        except ValueError:
            temperature = float('nan')
        notes = request.form.get('notes', '').strip()
        if not math.isfinite(temperature) or not -100 <= temperature <= 150 or len(notes) > 1000:
            db.session.rollback()
            flash('دما یا توضیحات نامعتبر است.', 'danger')
            return redirect(url_for('main.records') + '#shift-inspections')
        record.answers = json.dumps(answers, ensure_ascii=False)
        record.temperature, record.notes = temperature, notes
        message = checklist_message(record, 'اصلاح بازدید شیفت', reason)
    else:
        heading = 'بازنشانی بازدید شیفت' if action == 'reset' else 'حذف بازدید شیفت'
        message = checklist_message(record, heading, reason)
        db.session.delete(record)
    db.session.commit()
    try:
        send_to_bale_async(type='message', text=message + f'\nتغییردهنده: {current_user.username}')
    except Exception:
        current_app.logger.exception('Checklist change saved but Bale enqueue failed: %s', record_id)
    flash('تغییر بازدید ثبت شد.', 'success')
    if request.form.get('source') == 'form':
        return redirect(url_for('main.form'))
    return redirect(url_for('main.records') + '#shift-inspections')

def active_checklist_items():
    settings = db.session.get(ShiftChecklistSettings, 1)
    return json.loads(settings.items_json) if settings else CHECKLIST_ITEMS

@main_bp.route('/api/shift-checklist/items', methods=['POST'])
@login_required
@admin_required
def manage_shift_checklist():
    data = request.get_json(silent=True) or {}
    if not session.get('checklist_token') or not secrets.compare_digest(str(data.get('token', '')), session['checklist_token']):
        return jsonify(error='نشست نامعتبر است؛ صفحه را تازه‌سازی کنید.'), 403
    labels = data.get('labels')
    if not isinstance(labels, list) or not 1 <= len(labels) <= 40 or any(not isinstance(label, str) or not 1 <= len(label.strip()) <= 200 for label in labels):
        return jsonify(error='بین ۱ تا ۴۰ مورد با عنوان‌های حداکثر ۲۰۰ نویسه وارد کنید.'), 400
    old_items = active_checklist_items()
    existing = data.get('items')
    if not isinstance(existing, list) or len(existing) != len(labels):
        return jsonify(error='فهرست موارد نامعتبر است.'), 400
    valid_ids = {item['id'] for item in old_items}
    kept = [entry.get('id') for entry in existing if isinstance(entry, dict) and entry.get('id')]
    if len(kept) != len(set(kept)) or any(item_id not in valid_ids for item_id in kept):
        return jsonify(error='شناسهٔ موارد نامعتبر است؛ صفحه را تازه‌سازی کنید.'), 409
    new_items = [{'id': entry['id'] if entry.get('id') else secrets.token_hex(8), 'label': label.strip()}
                 for entry, label in zip(existing, labels)]
    settings = db.session.get(ShiftChecklistSettings, 1)
    if settings is None:
        settings = ShiftChecklistSettings(id=1, items_json='[]')
        db.session.add(settings)
    settings.items_json = json.dumps(new_items, ensure_ascii=False)
    db.session.commit()
    return jsonify(items=new_items)

@main_bp.route('/api/shift-checklist', methods=['GET'])
@login_required
def shift_checklist_status():
    server_now = datetime.now()
    shift_start, shift_name = current_checklist_shift(server_now)
    record = ShiftChecklist.query.filter_by(shift_start=shift_start).first()
    return jsonify(shift_start=shift_start.isoformat(), shift_name=shift_name,
                   seconds_remaining=max(0, ((shift_start + timedelta(hours=8)) - server_now).total_seconds()),
                   shift_date=jdatetime.date.fromgregorian(date=shift_start.date()).strftime('%Y/%m/%d'),
                   answer_labels=_assigned_response_labels(0), items=active_checklist_items(), can_manage=bool(record and (current_user.is_admin or record.created_by == current_user.username)),
                   completed=checklist_payload(record) if record else None)

@main_bp.route('/api/shift-checklist', methods=['POST'])
@login_required
def save_shift_checklist():
    data = request.get_json(silent=True) or {}
    if not session.get('checklist_token') or not secrets.compare_digest(str(data.get('token', '')), session['checklist_token']):
        return jsonify(error='نشست نامعتبر است؛ صفحه را تازه‌سازی کنید.'), 403
    shift_start, shift_name = current_checklist_shift()
    if data.get('shift_start') != shift_start.isoformat():
        return jsonify(error='شیفت تغییر کرده است؛ وضعیت جدید را بارگذاری کنید.'), 409
    if ShiftChecklist.query.filter_by(shift_start=shift_start).first():
        return jsonify(error='چک‌لیست این شیفت قبلاً ثبت شده است.'), 409
    if data.get('answer_labels') is not None and data['answer_labels'] != _assigned_response_labels(0):
        return jsonify(error='پاسخ‌ها تغییر کرده‌اند؛ صفحه را تازه‌سازی کنید.'), 409
    submitted = data.get('answers')
    expected = {item['id']: item for item in active_checklist_items()}
    if not isinstance(submitted, dict) or set(submitted) != set(expected):
        return jsonify(error='وضعیت همه موارد را مشخص کنید.'), 400
    answers = []
    for item_id, item in expected.items():
        answer = submitted[item_id]
        if not isinstance(answer, dict) or answer.get('status') not in ANSWER_LABELS:
            return jsonify(error='پاسخ چک‌لیست نامعتبر است.'), 400
        note = str(answer.get('note', '')).strip()
        if len(note) > 500 or (answer['status'] == 'issue' and not note):
            return jsonify(error='برای هر مورد مشکل‌دار، توضیح کوتاه لازم است.'), 400
        answers.append({'id': item_id, 'label': item['label'], 'status': answer['status'], 'status_label': _assigned_response_labels(0)[answer['status']], 'note': note})
    try:
        temperature = float(str(data.get('temperature', '')).replace('٫', '.'))
    except (ValueError, TypeError):
        return jsonify(error='دمای سرور را به صورت عددی وارد کنید.'), 400
    if not math.isfinite(temperature) or not -100 <= temperature <= 150:
        return jsonify(error='دمای واردشده معتبر نیست.'), 400
    notes = str(data.get('notes', '')).strip()
    if len(notes) > 1000:
        return jsonify(error='توضیحات بیش از حد طولانی است.'), 400
    record = ShiftChecklist(shift_start=shift_start, shift_name=shift_name,
        answers=json.dumps(answers, ensure_ascii=False), temperature=temperature,
        notes=notes, created_by=current_user.username)
    try:
        db.session.add(record)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error='چک‌لیست این شیفت قبلاً ثبت شده است.'), 409
    message = checklist_message(record)
    try:
        send_to_bale_async(type='message', text=message)
    except Exception:
        current_app.logger.exception('Checklist saved but Bale enqueue failed: %s', record.id)
    return jsonify(completed=checklist_payload(record)), 201





def send_message_to_bale(message_text):
    """ارسال پیام متنی به بله"""
    try:
        url = f"https://tapi.bale.ai/bot{current_app.config['BALE_TOKEN']}/sendMessage"
        data = {"chat_id": current_app.config['BALE_CHAT_ID'], "text": message_text, "parse_mode": "HTML"}
        response = requests.post(url, data=data, timeout=15)
        result = response.json()
        if response.status_code == 200 and result.get('ok'):
            print("✅ پیام با موفقیت به گروه بله ارسال شد")
            return True
        else:
            error_msg = result.get('description', 'خطای نامشخص')
            print(f"❌ خطا در ارسال پیام به بله: {error_msg}")
            return False
    except Exception as e:
        print(f"❌ خطا در ارسال پیام به بله: {e}")
        return False

def send_document_to_bale(file_to_send, filename, caption):
    """ارسال فایل (از مسیر یا BytesIO) به بله. در صورت موفقیت True و در غیر این صورت False برمی‌گرداند."""
    try:
        print(f"INFO: شروع ارسال فایل '{filename}' به بله...")
        url = f"https://tapi.bale.ai/bot{current_app.config['BALE_TOKEN']}/sendDocument"
        
        # --- تغییر کلیدی: اضافه شدن buffer.seek(0) قبل از ارسال فایل‌ها ---
        if isinstance(file_to_send, str):
            print("DEBUG: ارسال از روی دیسک.")
            with open(file_to_send, 'rb') as f:
                files = {'document': (filename, f)}
                data = {'chat_id': current_app.config['BALE_CHAT_ID'], 'caption': caption}
                response = requests.post(url, files=files, data=data, timeout=30)
        else:
            print("DEBUG: ارسال از روی بافر (BytesIO).")
            # اضافه کردن seek(0) برای بازگرداندن اشاره‌گر به ابتدای فایل
            file_to_send.seek(0)
            files = {'document': (filename, file_to_send.getvalue(), 'application/pdf')}
            data = {'chat_id': current_app.config['BALE_CHAT_ID'], 'caption': caption}
            response = requests.post(url, files=files, data=data, timeout=30)

        print(f"DEBUG: کد وضعیت پاسخ از بله: {response.status_code}")
        print(f"DEBUG: محتوای پاسخ از بله: {response.text}")

        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                print(f"✅ فایل {filename} با موفقیت به گروه بله ارسال شد")
                return True
            else:
                error_msg = result.get('description', 'خطای نامشخص از بله')
                print(f"❌ خطا در ارسال فایل به بله (API Error): {error_msg}")
                return False
        else:
            print(f"❌ خطا در ارسال فایل به بله (HTTP Error): کد وضعیت {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        # این بخش خطاهای شبکه (مانند قطعی اینترنت) را می‌گیرد
        print(f"❌ خطای شبکه در ارسال فایل به بله: {e}")
        return False
    except Exception as e:
        print(f"❌ خطای کلی در ارسال فایل به بله: {e}")
        import traceback
        traceback.print_exc()
        return False

def apply_persian_font_and_style(plt):
    """تنظیمات یکسان و حرفه‌ای فونت فارسی + اندازه بزرگ و خوانا"""
    # تشخیص بهترین فونت فارسی موجود در سیستم
    available_fonts = [f.name for f in fm.fontManager.ttflist]
    
    # اولویت با فونت‌های کامل‌تر است
    if any('Vazir' in f for f in available_fonts):
        font_name = 'Vazir'  # Vazir معمولاً کامل است
    elif any('Nazanin' in f for f in available_fonts):
        font_name = 'B Nazanin'
    elif any('XB' in f for f in available_fonts):
        font_name = next(f for f in available_fonts if 'XB' in f)
    elif 'Tahoma' in available_fonts:
        font_name = 'Tahoma'
    else:
        font_name = 'DejaVu Sans'

    # فونت‌های مختلف با اندازه‌های متفاوت
    font_base = FontProperties(family=font_name, size=15)
    font_bold = FontProperties(family=font_name, size=15, weight='bold')
    font_large = FontProperties(family=font_name, size=18, weight='bold')
    font_title = FontProperties(family=font_name, size=24, weight='bold')
    font_table = FontProperties(family=font_name, size=22, weight='bold')

    # تنظیمات سراسری matplotlib
    plt.rcParams.update({
        'font.family': font_name,
        'font.size': 15,
        'axes.titlesize': 24,
        'axes.labelsize': 18,
        'xtick.labelsize': 14,
        'ytick.labelsize': 14,
        'legend.fontsize': 14,
        'figure.titlesize': 26,
    })

    return font_base, font_bold, font_large, font_title, font_table

def save_failed_report(file_content, filename, caption):
    """گزارشی که ارسال نشد را برای تلاش مجدد ذخیره می‌کند."""
    try:
        failed_dir = os.path.join(current_app.root_path, 'failed_reports')
        os.makedirs(failed_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"{timestamp}_{filename}"
        
        file_path = os.path.join(failed_dir, base_filename)
        caption_path = os.path.join(failed_dir, f"{base_filename}.txt")
        
        with open(file_path, 'wb') as f:
            f.write(file_content.getvalue())
        
        with open(caption_path, 'w', encoding='utf-8') as f:
            f.write(caption)
            
        print(f"INFO: گزارش ناموفق '{filename}' برای تلاش مجدد در مسیر '{file_path}' ذخیره شد.")
        return True
    except Exception as e:
        print(f"ERROR: خطا در ذخیره گزارش ناموفق: {e}")
        return False

# --- Section 4: TCP Server for Alarms ---
ALLOWED_MONITOR_IPS = [
    '172.16.60.62',   # IP سیستم مانیتورینگ اصلی
    '172.16.60.63',   # IP بکاپ (در صورت وجود)
    '127.0.0.1'       # برای تست لوکال
]

def start_tcp_server(app):  # <--- پارامتر app اضافه شد
    host = '0.0.0.0'
    port = 9999
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen(5)
    
    print(f"TCP Alarm Server فعال شد → {host}:{port}")

    while True:
        try:
            client_socket, addr = server_socket.accept()
            client_ip = addr[0]

            if client_ip not in ALLOWED_MONITOR_IPS:
                print(f"اتصال غیرمجاز از {client_ip} رد شد!")
                client_socket.close()
                continue

            data = client_socket.recv(4096).decode('utf-8').strip()
            if not data:
                client_socket.close()
                continue

            # --- کل کارهای پردازش باید داخل app_context باشد ---
            with app.app_context():
                try:
                    json_data = json.loads(data)
                    required_key = current_app.config.get('ALARM_SECRET_KEY')
                    
                    if not required_key or json_data.get('secret_key') != required_key:
                        print(f"کلید مخفی اشتباه از {client_ip}")
                        client_socket.close()
                        continue

                    network_name = json_data.get('network_name')
                    network = Network.query.filter_by(name=network_name).first()
                    if not network:
                        print(f"نام شبکه نامعتبر: {network_name}")
                        client_socket.close()
                        continue

                    start_time = json_data.get('start_time')
                    end_time = json_data.get('end_time')
                    duration = json_data.get('duration')

                    if not all([network_name, start_time, end_time, duration]):
                        print("داده ناقص")
                        client_socket.close()
                        continue

                    last_record = ShiftRecord.query.order_by(ShiftRecord.row_number.desc()).first()
                    next_row_number = (last_record.row_number + 1) if last_record else 1

                    new_alarm = ShiftRecord(
                        row_number=next_row_number,
                        date=jdatetime.date.today().strftime("%Y/%m/%d"),
                        shift=get_current_shift(),
                        network_name=network_name,
                        activity='قطعی صدا (آلارم)',
                        start_time=start_time,
                        end_time=end_time,
                        duration=duration,
                        created_by='system_monitor'
                    )
                    db.session.add(new_alarm)
                    db.session.commit()

                    print(f"آلارم معتبر ثبت شد ← شبکه: {network_name}")
                    alarm_message = f"آلارم قطعی صدا\nشبکه: {network_name}\nشروع: {start_time}\nپایان: {end_time}\nمدت: {duration}"
                    send_to_bale_async(type="message", text=alarm_message)

                except Exception as e:
                    print(f"خطا در پردازش آلارم: {e}")
                finally:
                    client_socket.close()

        except Exception as e:
            print(f"خطای سرور TCP: {e}")

def init_tcp_server(app):
    """ارسال شی app به ترد برای مدیریت Context"""
    # ارسال app به تابع start_tcp_server
    tcp_thread = threading.Thread(target=start_tcp_server, args=(app,), daemon=True)
    tcp_thread.start()
    print("✅ سرور TCP در نخ جداگانه راه‌اندازی شد.")

# --- Section 5: Chart Generation Functions ---
# (توابع نمودار به utils_charts.py منتقل شده‌اند و از آنجا ایمپورت می‌شوند)



@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login'))

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            if not user.security_question or not user.security_answer:
                flash('برای امنیت بیشتر، لطفاً سوال امنیتی خود را تنظیم کنید.', 'info')
                return redirect(url_for('main.set_security_question'))
            
            # --- تغییر کلیدی: اضافه شدن پشتیبانی از next برای ریدایرکت هوشمند ---
            next_page = request.args.get('next')
            if not next_page or urlparse(next_page).netloc != '':
                next_page = url_for('main.form')
            return redirect(next_page)
        else:
            flash('نام کاربری یا رمز عبور اشتباه است', 'danger')
    return render_template('login.html')

@main_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    selected_range = request.args.get('range', 'daily')
    start_date_str, end_date_str = get_jalali_date_range(selected_range)
    
    # ... (بخش کوئری‌های آماری بدون تغییر باقی بماند) ...
    query = ShiftRecord.query.filter(ShiftRecord.date >= start_date_str, ShiftRecord.date <= end_date_str)
    total_records = query.count()
    today_records = ShiftRecord.query.filter_by(date=jdatetime.date.today().strftime("%Y/%m/%d")).count()
    activity_counts = query.with_entities(ShiftRecord.activity, db.func.count(ShiftRecord.id)).group_by(ShiftRecord.activity).order_by(db.func.count(ShiftRecord.id).desc()).first()
    most_common_activity = activity_counts[0] if activity_counts else "ندارد"
    most_common_count = activity_counts[1] if activity_counts else 0
    network_counts = query.with_entities(ShiftRecord.network_name, db.func.count(ShiftRecord.id)).group_by(ShiftRecord.network_name).order_by(db.func.count(ShiftRecord.id).desc()).first()
    most_common_network = network_counts[0] if network_counts else "ندارد"
    most_common_network_count = network_counts[1] if network_counts else 0
    
    # === اصلاح فراخوانی توابع نمودار (استفاده از نام پارامترها) ===
    # اشتباه قبلی: ارسال تاریخ به جای df
    # اصلاح شده: استفاده از start_date=...
    
    activity_chart = create_pie_chart_activity(start_date=start_date_str, end_date=end_date_str)
    network_chart = create_network_chart(start_date=start_date_str, end_date=end_date_str)
    timeline_chart = create_timeline_chart(start_date=start_date_str, end_date=end_date_str)
    audio_outage_chart = create_audio_outage_scatter_chart(start_date=start_date_str, end_date=end_date_str)
    pgm_chart = create_pgm_chart(start_date=start_date_str, end_date=end_date_str)
    easycaster_chart = create_easycaster_chart(start_date=start_date_str, end_date=end_date_str)
    
    return render_template('dashboard.html', total_records=total_records, today_records=today_records,
                           most_common_activity=most_common_activity, most_common_count=most_common_count,
                           most_common_network=most_common_network, most_common_network_count=most_common_network_count,
                           activity_chart=activity_chart, network_chart=network_chart, timeline_chart=timeline_chart,
                           audio_outage_chart=audio_outage_chart, pgm_chart=pgm_chart, easycaster_chart=easycaster_chart)

@main_bp.route('/submit', methods=['POST'])
@login_required
def submit():
    try:
        print("DEBUG: Submit function started")

        submission_token = request.form.get('submission_token', '').strip()
        pending_tokens = session.get('pending_submission_tokens', [])
        if submission_token not in pending_tokens or not _claim_submission_token(submission_token):
            flash('این گزارش قبلاً ارسال شده است؛ ثبت تکراری انجام نشد.', 'warning')
            return redirect(url_for('main.form'))

        # توکن در همین نشست نیز یک‌بارمصرف است.
        session['pending_submission_tokens'] = [
            token for token in pending_tokens if token != submission_token
        ]
        session.modified = True

        date_str = request.form.get('date')
        print(f"DEBUG: Date: {date_str}")
        
        # اعتبارسنجی فرمت تاریخ جلالی
        try:
            jdatetime.datetime.strptime(date_str, "%Y/%m/%d")
        except (ValueError, TypeError):
            flash('فرمت تاریخ وارد شده نامعتبر است. لطفاً از فرمت YYYY/MM/DD استفاده کنید.', 'danger')
            return redirect(url_for('main.form'))

        activity = request.form.get('activity')
        print(f"DEBUG: Activity: {activity}")
        
        # اعتبارسنجی فیلدهای الزامی بر اساس نوع فعالیت (بروزرسانی شده برای DB)
        activity_obj = Activity.query.filter_by(name=activity).first()
        if not activity_obj:
            flash('فعالیت انتخاب‌شده معتبر نیست.', 'danger')
            return redirect(url_for('main.form'))
        required_fields = activity_obj.get_required_fields()
        
        missing_fields = [field for field in required_fields if not request.form.get(field)]
        if missing_fields:
            field_names = {
                'network_name': 'نام شبکه',
                'start_time': 'ساعت شروع',
                'end_time': 'ساعت پایان',
                'signal_time': 'ساعت دریافت سیگنال',
                'receiver': 'تحویل‌گیرنده'
            }
            missing_field_names = [field_names.get(f, f) for f in missing_fields]
            flash(f'لطفاً فیلدهای الزامی را پر کنید: {", ".join(missing_field_names)}', 'danger')
            return redirect(url_for('main.form'))
        
        # پیدا کردن آخرین رکورد برای شماره ردیف بعدی
        last_record = ShiftRecord.query.order_by(ShiftRecord.row_number.desc()).first()
        next_row_number = (last_record.row_number + 1) if last_record else 1
        print(f"DEBUG: Next row number: {next_row_number}")
        
        # ایجاد رکورد جدید
        new_record = ShiftRecord(
            row_number=next_row_number,
            date=request.form.get('date'),
            shift=request.form.get('shift'),
            location=request.form.get('location'),
            network_name=request.form.get('network_name'),
            activity=activity,
            deliverer=request.form.get('deliverer'),
            receiver=request.form.get('receiver'),
            signal_time=request.form.get('signal_time'),
            start_time=request.form.get('start_time'),
            end_time=request.form.get('end_time'),
            via_method=request.form.get('via_method'),
            transmission_line=request.form.get('transmission_line'),
            shift_staff=', '.join(request.form.getlist('shift_staff')),
            description=request.form.get('description'),
            comments=request.form.get('comments'),
            created_by=current_user.username
        )
        
        # محاسبه مدت زمان
        new_record.duration = calculate_duration(new_record.start_time, new_record.end_time)
        print(f"DEBUG: Duration calculated: {new_record.duration}")
        
        # ذخیره در دیتابیس
        db.session.add(new_record)
        db.session.commit()
        print(f"DEBUG: Record saved with ID: {new_record.id}")
        
        # =================================================================
        # ⭐ تغییرات اصلی: ساخت پیام پویا (Dynamic Message Generation) ⭐
        # =================================================================

        # 1. تعریف یک دیکشنری برای نگاشت نام فیلدها به عنوان‌های فارسی
        field_mapping = {
            'created_by': 'ثبت توسط',
            'date': 'تاریخ',
            'shift': 'شیفت',
            'network_name': 'شبکه',
            'activity': 'فعالیت',
            'deliverer': 'تحویل‌دهنده',
            'receiver': 'تحویل‌گیرنده',
            'location': 'لوکیشن',
            'signal_time': 'ساعت دریافت سیگنال',
            'start_time': 'شروع',
            'end_time': 'پایان',
            'duration': 'مدت زمان',
            'via_method': 'از طریق',
            'transmission_line': 'خط ارسالی',
            'shift_staff': 'پرسنل شیفت',
            'description': 'توضیحات',
            'comments': 'کامنت'
        }

        # 2. فیلدهای کلیدی که همیشه نمایش داده می‌شوند (حتی اگر خالی باشند)
        always_show = ['created_by', 'date', 'shift', 'activity', 'duration']
        
        # 3. ساخت بدنه پیام (Header)
        report_lines = ["گزارش جدید ثبت شد\n"]
        
        # 4. افزودن خطوط بر اساس وجود مقدار
        
        # خطوط کلیدی و اصلی
        report_lines.append(f"{field_mapping['created_by']}: {new_record.created_by}")
        report_lines.append(f"{field_mapping['date']}: {new_record.date}")
        report_lines.append(f"{field_mapping['shift']}: {new_record.shift}")
        report_lines.append(f"{field_mapping['activity']}: {new_record.activity}\n")
        
        # خطوط زمان و مدت زمان (مدیریت نمایش Duration)
        if new_record.duration != "00:00:00":
             if new_record.start_time and new_record.end_time:
                 report_lines.append(f"شروع: {new_record.start_time}")
                 report_lines.append(f"پایان: {new_record.end_time}")
             report_lines.append(f"مدت زمان: {new_record.duration}\n")
        
        # فیلدهای اختیاری
        for attr, label in field_mapping.items():
            if attr in always_show or attr in ['date', 'shift', 'activity', 'created_by', 'start_time', 'end_time', 'duration']:
                continue
            
            value = getattr(new_record, attr)
            # اگر مقدار وجود دارد و خالی یا شامل فقط فاصله نیست
            if value and str(value).strip():
                report_lines.append(f"{label}: {value}")

        # خط آخر: ردیف
        report_lines.append(f"\nردیف: {new_record.row_number}")

        report_message = "\n".join(report_lines)

        # =================================================================
        # پایان ساخت پیام پویا
        # =================================================================

        # ارسال به بله (صف غیرهمزمان)
        send_to_bale_async(type="message", text=report_message)

        # ارسال ایمیل برای هر گزارش جدید
        try:
            email_subject = f"گزارش جدید شیفت - ردیف {new_record.row_number}"
            email_body = (
                f"{report_message}\n\n"
                f"این ایمیل به صورت خودکار از سامانه ثبت شیفت ارسال شده است."
            )
            # تابع در utils_email.py تعریف شده:
            send_email_to_admins(email_subject, email_body)
            print("DEBUG: Email about new record sent to admins.")
        except Exception as e:
            # اگر هم ایمیل خطا داد، نگذاریم ثبت رکورد خراب شود
            print(f"ERROR: Failed to send email for new record: {e}")
            try:
                current_app.logger.error(f"Failed to send email for new record {new_record.row_number}: {e}")
            except Exception:
                pass
        
        flash('اطلاعات با موفقیت ثبت شد.', 'success')
        return redirect(url_for('main.form'))

    except Exception as e:
        db.session.rollback()
        print(f"ERROR in submit: {e}")
        try:
            current_app.logger.error(f"ERROR in submit: {e}")
        except Exception:
            pass
        flash('خطا در ثبت', 'danger')
        return redirect(url_for('main.form'))

@main_bp.route('/form')
@login_required
def form():
    last_record = ShiftRecord.query.order_by(ShiftRecord.row_number.desc()).first()
    next_row_number = (last_record.row_number + 1) if last_record else 1
    
    # لیست‌های پویا از دیتابیس (DB)
    network_names_db = Network.query.order_by(Network.name).all()
    network_names = sorted([n.name for n in network_names_db], key=persian_sort_key) 
    staff = [s.name for s in Staff.query.order_by(Staff.name).all()]
    activity_objects = Activity.query.order_by(Activity.name).all()
    activities = [a.name for a in activity_objects]
    activity_configs = {
        a.name: {
            'enabled': a.get_enabled_fields(),
            'required': a.get_required_fields()
        } for a in activity_objects
    }

    # برای هر بار نمایش فرم یک شناسه یک‌بارمصرف مستقل می‌سازیم.
    submission_token = secrets.token_urlsafe(32)
    pending_tokens = session.get('pending_submission_tokens', [])
    pending_tokens.append(submission_token)
    session['pending_submission_tokens'] = pending_tokens[-10:]
    session.modified = True
    if not session.get('checklist_token'):
        session['checklist_token'] = secrets.token_urlsafe(32)
    
    return render_template('form.html', network_names=network_names, staff=staff, shifts=SHIFTS,
                           activities=activities, via_methods=VIA_METHODS, transmission_lines=TRANSMISSION_LINES,
                           next_row_number=next_row_number, today=jdatetime.date.today().strftime("%Y/%m/%d"),
                           submission_token=submission_token, checklist_token=session['checklist_token'],
                           activity_configs=activity_configs)

@main_bp.route('/records')
@login_required
def records():
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'date')
    order = request.args.get('order', 'desc')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    network = request.args.get('network')
    activity = request.args.get('activity')
    
    query = ShiftRecord.query
    if start_date: query = query.filter(ShiftRecord.date >= start_date)
    if end_date: query = query.filter(ShiftRecord.date <= end_date)
    if network: query = query.filter(ShiftRecord.network_name == network)
    if activity: query = query.filter(ShiftRecord.activity == activity)
    
    if sort_by == 'date':
        query = query.order_by(ShiftRecord.date.desc(), ShiftRecord.start_time.desc()) if order == 'desc' else query.order_by(ShiftRecord.date.asc(), ShiftRecord.start_time.asc())
    elif sort_by == 'time':
        query = query.order_by(ShiftRecord.start_time.desc(), ShiftRecord.date.desc()) if order == 'desc' else query.order_by(ShiftRecord.start_time.asc(), ShiftRecord.date.asc())
    else:
        query = query.order_by(ShiftRecord.date.desc(), ShiftRecord.start_time.desc())
    
    records = query.paginate(page=page, per_page=20, error_out=False)
    
    # خواندن لیست‌ها از DB
    network_names_db = Network.query.all()
    network_names = sorted([n.name for n in network_names_db if n.name], key=persian_sort_key)
    activities = [a.name for a in Activity.query.all() if a.name]
    
    checklist_page = request.args.get('checklist_page', 1, type=int)
    inspections = ShiftChecklist.query.order_by(ShiftChecklist.shift_start.desc()).paginate(
        page=checklist_page, per_page=10, error_out=False)
    if not session.get('checklist_token'):
        session['checklist_token'] = secrets.token_urlsafe(32)
    return render_template('records.html', records=records, network_names=network_names,
                           activities=activities, inspections=inspections, answer_labels=_assigned_response_labels(0),
                           json_loads=json.loads, checklist_revision=checklist_revision,
                           checklist_token=session['checklist_token'], current_shift_start=current_checklist_shift()[0])

@main_bp.route('/reports')
@login_required
def reports():
    # لیست‌های پویا از دیتابیس (DB)
    network_names_db = Network.query.order_by(Network.name).all()
    network_names = sorted([n.name for n in network_names_db], key=persian_sort_key)
    activities = [a.name for a in Activity.query.order_by(Activity.name).all()]
    
    return render_template('reports.html', network_names=network_names, activities=activities)

@main_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        user = User.query.get(current_user.id)
        if not check_password_hash(user.password_hash, current_password):
            flash('رمز عبور فعلی اشتباه است', 'danger')
        elif new_password != confirm_password:
            flash('رمز عبور جدید و تکرار آن یکسان نیستند', 'danger')
        elif not new_password:
            flash('رمز عبور جدید نمی‌تواند خالی باشد', 'danger')
        else:
            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash('رمز عبور شما با موفقیت تغییر یافت', 'success')
            return redirect(url_for('main.dashboard'))
    return render_template('change_password.html')

@main_bp.route('/set-security-question', methods=['GET', 'POST'])
@login_required
def set_security_question():
    if request.method == 'POST':
        question = request.form.get('security_question')
        answer = request.form.get('security_answer')
        if not question or not answer:
            flash('لطفاً هر دو فیلد سوال و پاسخ را پر کنید.', 'warning')
            return redirect(url_for('main.set_security_question'))
        user = User.query.get(current_user.id)
        user.security_question = question
        user.security_answer = generate_password_hash(answer)
        db.session.commit()
        flash('سوال امنیتی شما با موفقیت تنظیم شد.', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('set_security_question.html')

@main_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username')
        user = User.query.filter_by(username=username).first()
        if user and user.security_question:
            session['reset_username'] = username
            return redirect(url_for('main.answer_security_question'))
        else:
            flash('نام کاربری یافت نشد یا این کاربر سوال امنیتی تنظیم نکرده است.', 'danger')
    return render_template('forgot_password.html')

@main_bp.route('/answer-security-question', methods=['GET', 'POST'])
def answer_security_question():
    username = session.get('reset_username')
    if not username:
        flash('خطا در فرآیند، لطفاً دوباره تلاش کنید.', 'danger')
        return redirect(url_for('main.forgot_password'))
    
    user = User.query.filter_by(username=username).first()
    if request.method == 'POST':
        answer = request.form.get('security_answer')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if not check_password_hash(user.security_answer, answer):
            flash('پاسخ امنیتی اشتباه است.', 'danger')
        elif new_password != confirm_password:
            flash('رمز عبور جدید و تکرار آن یکسان نیستند.', 'danger')
        else:
            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            session.pop('reset_username', None)
            flash('رمز عبور شما با موفقیت بازنشانی شد. اکنون می‌توانید وارد شوید.', 'success')
            return redirect(url_for('main.login'))
    return render_template('answer_security_question.html', user=user)

@main_bp.route('/about')
@login_required
def about():
    return render_template('about.html')

@main_bp.route('/edit_record/<int:record_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_record(record_id):

    
    record = ShiftRecord.query.get_or_404(record_id)
    
    if request.method == 'POST':
        record.row_number = request.form.get('row_number')
        record.date = request.form.get('date')
        record.shift = request.form.get('shift')
        record.location = request.form.get('location')  # اضافه شد
        record.network_name = request.form.get('network_name')
        record.activity = request.form.get('activity')
        record.deliverer = request.form.get('deliverer')
        record.receiver = request.form.get('receiver')
        record.signal_time = request.form.get('signal_time')  # اضافه شد
        record.start_time = request.form.get('start_time')
        record.end_time = request.form.get('end_time')
        record.duration = calculate_duration(record.start_time, record.end_time) # محاسبه مجدد
        record.via_method = request.form.get('via_method')
        record.transmission_line = request.form.get('transmission_line')
        record.shift_staff = ', '.join(request.form.getlist('shift_staff'))  # اصلاح شد
        record.description = request.form.get('description')
        record.comments = request.form.get('comments')
        record.admin_reply = request.form.get('admin_reply')  # اضافه شد
        
        db.session.commit()
        flash('رکورد با موفقیت ویرایش شد.', 'success')
        return redirect(url_for('main.records'))
    
    # خواندن لیست‌ها از DB
    network_names_db = Network.query.order_by(Network.name).all()
    network_names = sorted([n.name for n in network_names_db], key=persian_sort_key) 
    staff = [s.name for s in Staff.query.order_by(Staff.name).all()]
    activities = [a.name for a in Activity.query.order_by(Activity.name).all()]
    
    # ارسال لیست‌های مورد نیاز به تمپلیت
    return render_template('edit_form.html', 
                           record=record, 
                           network_names=network_names, 
                           staff=staff, 
                           shifts=SHIFTS,
                           activities=activities, 
                           via_methods=VIA_METHODS, 
                           transmission_lines=TRANSMISSION_LINES)

@main_bp.route('/admin/lists')
@login_required
@admin_required
def admin_lists():
    """صفحه مدیریت کاربران، شبکه‌ها، پرسنل و فعالیت‌ها"""

    users = User.query.order_by(User.username).all()
    networks = Network.query.order_by(Network.name).all()
    staff = Staff.query.order_by(Staff.name).all()
    activities = Activity.query.order_by(Activity.name).all()

    return render_template(
        'admin_lists.html',
        users=users,
        networks=networks,
        staff=staff,
        activities=activities
    )

@main_bp.route('/admin/users/<int:user_id>/toggle-role', methods=['POST'])
@login_required
@admin_required
def admin_user_toggle_role(user_id):

    user = User.query.get_or_404(user_id)

    # ادمین اصلی هرگز قابل تغییر نیست
    if user.username.strip().lower() == 'admin':

        flash(
            'نقش ادمین اصلی قابل تغییر نیست.',
            'warning'
        )

        return redirect(
            url_for('main.admin_lists')
        )

    # تغییر نقش
    if user.is_admin:
        user.role = 'user'

        flash(
            f'کاربر "{user.username}" به User تغییر کرد.',
            'success'
        )

    else:
        user.role = 'admin'

        flash(
            f'کاربر "{user.username}" به Admin تغییر کرد.',
            'success'
        )

    db.session.commit()

    return redirect(
        url_for('main.admin_lists')
    )



# --- روت‌های CRUD برای Network ---
@main_bp.route('/admin/networks/add', methods=['POST'])
@login_required
@admin_required
def admin_networks_add():
    name = request.form.get('name').strip()
    if name and not Network.query.filter_by(name=name).first():
        db.session.add(Network(name=name))
        db.session.commit()
        flash(f'شبکه "{name}" اضافه شد.', 'success')
    else:
        flash('این شبکه قبلاً وجود دارد یا نام خالی است.', 'danger')
    return redirect(url_for('main.admin_lists'))

@main_bp.route('/admin/networks/delete/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def admin_networks_delete(item_id):
    network = Network.query.get_or_404(item_id)
    try:
        db.session.delete(network)
        db.session.commit()
        flash(f'شبکه "{network.name}" حذف شد.', 'success')
    except Exception as e:
        flash('خطا: این شبکه در رکوردهای ثبت شده استفاده شده و قابل حذف نیست.', 'danger')
        db.session.rollback()
    return redirect(url_for('main.admin_lists'))

# --- روت‌های CRUD برای Staff ---
@main_bp.route('/admin/staff/add', methods=['POST'])
@login_required
@admin_required
def admin_staff_add():
    name = request.form.get('name').strip()
    if name and not Staff.query.filter_by(name=name).first():
        db.session.add(Staff(name=name))
        db.session.commit()
        flash(f'پرسنل "{name}" اضافه شد.', 'success')
    else:
        flash('این پرسنل قبلاً وجود دارد یا نام خالی است.', 'danger')
    return redirect(url_for('main.admin_lists'))

@main_bp.route('/admin/staff/delete/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def admin_staff_delete(item_id):
    staff = Staff.query.get_or_404(item_id)
    try:
        db.session.delete(staff)
        db.session.commit()
        flash(f'پرسنل "{staff.name}" حذف شد.', 'success')
    except Exception as e:
        flash('خطا: این پرسنل در رکوردهای ثبت شده استفاده شده و قابل حذف نیست.', 'danger')
        db.session.rollback()
    return redirect(url_for('main.admin_lists'))

# --- روت‌های CRUD برای Activity ---
@main_bp.route('/admin/activities/add', methods=['POST'])
@login_required
@admin_required
def admin_activities_add():
    name = (request.form.get('name') or '').strip()
    enabled_fields = request.form.getlist('enabled_fields')
    required_fields = request.form.getlist('required_fields')
    
    if name and not Activity.query.filter_by(name=name).first():
        activity = Activity(name=name)
        activity.set_field_config(enabled_fields, required_fields)
        db.session.add(activity)
        db.session.commit()
        flash(f'فعالیت "{name}" اضافه شد.', 'success')
    else:
        flash('این فعالیت قبلاً وجود دارد یا نام خالی است.', 'danger')
    return redirect(url_for('main.admin_lists'))

@main_bp.route('/admin/activities/update/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def admin_activities_update(item_id):
    activity = Activity.query.get_or_404(item_id)
    activity.set_field_config(
        request.form.getlist('enabled_fields'),
        request.form.getlist('required_fields')
    )
    db.session.commit()
    flash(f'تنظیمات فعالیت "{activity.name}" ذخیره شد.', 'success')
    return redirect(url_for('main.admin_lists'))

@main_bp.route('/admin/activities/delete/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def admin_activities_delete(item_id):
    activity = Activity.query.get_or_404(item_id)
    try:
        db.session.delete(activity)
        db.session.commit()
        flash(f'فعالیت "{activity.name}" حذف شد.', 'success')
    except Exception as e:
        flash('خطا: این فعالیت در رکوردهای ثبت شده استفاده شده و قابل حذف نیست.', 'danger')
        db.session.rollback()
    return redirect(url_for('main.admin_lists'))

# --- Section 7: Export Routes ---
@main_bp.route('/export_excel')
@login_required
def export_excel():
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        network_list = request.args.getlist('network')
        activity_list = request.args.getlist('activity')
        
        query = ShiftRecord.query
        if start_date: 
            query = query.filter(ShiftRecord.date >= start_date)
        if end_date: 
            query = query.filter(ShiftRecord.date <= end_date)
        if network_list: 
            query = query.filter(ShiftRecord.network_name.in_(network_list))
        if activity_list: 
            query = query.filter(ShiftRecord.activity.in_(activity_list))
        
        records = query.order_by(ShiftRecord.id.desc()).all()
        
        # تبدیل رکوردها به لیست دیکشنری برای DataFrame
        data = [{
            'ردیف': r.row_number, 'تاریخ': r.date, 'شیفت': r.shift, 'لوکیشن': r.location,
            'نام شبکه': r.network_name, 'فعالیت': r.activity, 'تحویل‌دهنده': r.deliverer,
            'تحویل‌گیرنده در نودال شهدا': r.receiver, 'ساعت دریافت سیگنال': r.signal_time,
            'ساعت شروع': r.start_time, 'ساعت پایان': r.end_time, 'مدت زمان': r.duration,
            'از طریق': r.via_method, 'خط ارسالی': r.transmission_line, 'پرسنل شیفت': r.shift_staff,
            'توضیحات': r.description, 'کامنت': r.comments, 'پاسخ ادمین': r.admin_reply, 'کاربر ثبت‌کننده': r.created_by
        } for r in records]
        
        df = pd.DataFrame(data)
        
        # ایجاد نام فایل
        filename = f"filtered_shift_records_{jdatetime.date.today().strftime('%Y-%m-%d')}.xlsx"
        
        # ایجاد یک بافر در حافظه (in-memory buffer)
        excel_buffer = io.BytesIO()
        
        # نوشتن DataFrame مستقیماً در بافر
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='گزارش فیلتر شده')
        
        # برگردن به ابتدای بافر برای خواندن آن توسط Flask
        excel_buffer.seek(0)
        
        # ارسال مستقیم بافر به کاربر
        return send_file(
            excel_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        print(f"Error in export_excel: {e}")
        import traceback
        traceback.print_exc()
        flash(f'خطا در خروجی گرفتن: {str(e)}', 'danger')
        return redirect(url_for('main.reports'))

# در routes.py

@main_bp.route('/export_pdf')
@login_required
def export_pdf():
    try:
        # به جای print، از لاگر استفاده کنید. این پیام در کنسول سرور نمایش داده می‌شود
        current_app.logger.info("=== PDF EXPORT STARTED ===")
        
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        network_list = request.args.getlist('network')
        activity_list = request.args.getlist('activity')

        pdf_buffer = io.BytesIO()
        
        font_prop = FontProperties(family=['B Nazanin', 'Arial', 'sans-serif']) if 'B Nazanin' in [f.name for f in fm.fontManager.ttflist] else FontProperties(family='sans-serif')

        chart_functions = [
            ('روند فعالیت‌ها در طول زمان', create_timeline_chart),
            ('تعداد فعالیت‌ها بر اساس شبکه', create_network_chart),
            ('توزیع انواع فعالیت', create_pie_chart_activity),
            ('جزئیات مدت زمان قطعی صدا', create_audio_outage_scatter_chart),
            ('ارتباط‌های کابلی (PGM)', create_pgm_chart),
            ('ارتباط‌های اینترنتی (Easy Caster)', create_easycaster_chart)
        ]

        successful_charts = []
        for title, chart_func in chart_functions:
            try:
                chart_url = chart_func(start_date=start_date, end_date=end_date, network_list=network_list, activity_list=activity_list)
                if chart_url:
                    successful_charts.append((title, chart_url))
                    # به جای print، از لاگر استفاده کنید
                    current_app.logger.info(f"✅ Chart '{title}' created successfully.")
            except Exception as e:
                # به جای print، از لاگر استفاده کنید
                current_app.logger.error(f"❌ Error in chart '{title}': {e}")

        with PdfPages(pdf_buffer) as pdf:
            if not successful_charts:
                fig, ax = plt.subplots(figsize=(10, 6))
                ax.text(0.5, 0.5, get_persian_text('هیچ داده‌ای موجود نیست'), 
                        fontproperties=font_prop, ha='center', va='center', fontsize=20, color='red')
                ax.axis('off')
                pdf.savefig(fig, bbox_inches='tight')
                plt.close(fig)
            else:
                num_charts = len(successful_charts)
                cols = 2
                rows = (num_charts + cols - 1) // cols
                fig_width = 16.5
                fig_height = 10 * rows 
                
                fig, axes = plt.subplots(rows, cols, figsize=(fig_width, fig_height))
                if num_charts == 1: axes = [axes]
                else: axes = axes.flatten()

                plt.subplots_adjust(top=0.92, hspace=0.4, wspace=0.2, bottom=0.05)
                fig.suptitle(get_persian_text('گزارش جامع فعالیت‌ها'), fontproperties=font_prop, fontsize=32, weight='bold', y=0.98)
                
                if start_date or end_date:
                    txt = f"بازه زمانی: {start_date} تا {end_date}"
                    fig.text(0.5, 0.96, get_persian_text(txt), ha='center', fontproperties=font_prop, fontsize=20, color='#555')

                for i, (title, chart_url) in enumerate(successful_charts):
                    ax = axes[i]
                    try:
                        chart_data = base64.b64decode(chart_url)
                        chart_image = plt.imread(io.BytesIO(chart_data))
                        ax.imshow(chart_image, aspect='equal')
                    except Exception as e:
                        current_app.logger.error(f"Failed to embed chart '{title}' into PDF: {e}")
                    ax.axis('off')

                for i in range(num_charts, len(axes)): fig.delaxes(axes[i])
                pdf.savefig(fig, bbox_inches='tight', dpi=150)
                plt.close(fig)

        pdf_buffer.seek(0)
        file_content = pdf_buffer.getvalue()
        file_size = len(file_content)
        # به جای print، از لاگر استفاده کنید
        current_app.logger.info(f"🏁 Final PDF Size: {file_size} bytes")

        if file_size == 0:
            return "Error: Generated PDF is empty", 500

        today_str = jdatetime.date.today().strftime("%Y-%m-%d")
        filename = f"report_{today_str}.pdf"

        response = make_response(file_content)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        response.headers['Content-Length'] = file_size
        
        return response

    except Exception as e:
        # به جای print و traceback.print_exc از لاگر استفاده کنید
        current_app.logger.critical(f"CRITICAL ERROR in PDF export: {e}")
        # برای مشاهده جزئیات خطا در لاگ، از traceback.format_exc استفاده کنید
        import traceback
        current_app.logger.critical(traceback.format_exc())
        return f"Server Error: {e}", 500
@main_bp.route('/import_excel', methods=['POST'])
@login_required
def import_excel():
    if 'excel_file' not in request.files:
        flash('فایلی انتخاب نشده است.', 'danger')
        return redirect(url_for('main.reports'))
    file = request.files['excel_file']
    if file.filename == '':
        flash('نام فایل خالی است.', 'danger')
        return redirect(url_for('main.reports'))
    if file and file.filename.endswith('.xlsx'):
        filename = secure_filename(file.filename)
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        try:
            df = pd.read_excel(filepath)
            df = df.fillna('')
            imported_count = 0
            skipped_count = 0

            # حلقه for درست است و همه چیز داخل آن قرار دارد
            for index, row in df.iterrows():
                try:
                    # خواندن مقادیر مورد نیاز از ردیف
                    start_time = row.get('start_time', '')
                    end_time = row.get('end_time', '')

                    # محاسبه مدت زمان با استفاده از تابع خود برنامه
                    calculated_duration = calculate_duration(start_time, end_time)

                    new_record = ShiftRecord(
                        row_number=row.get('row_number', index + 1), 
                        date=row.get('date', ''), 
                        shift=row.get('shift', ''),
                        location=row.get('location', ''), 
                        network_name=row.get('network_name', ''), 
                        activity=row.get('activity', ''), 
                        deliverer=row.get('deliverer', ''), 
                        receiver=row.get('receiver', ''), 
                        signal_time=row.get('signal_time', ''), 
                        start_time=start_time, 
                        end_time=end_time, 
                        # نکته کلیدی: از مدت زمان محاسبه شده استفاده می‌کنیم
                        duration=calculated_duration,
                        via_method=row.get('via_method', ''), 
                        transmission_line=row.get('transmission_line', ''), 
                        shift_staff=row.get('shift_staff', ''),
                        description=row.get('description', ''),
                        # --- تغییر کلیدی: اضافه شدن ستون‌های comments و admin_reply به پروسه ایمپورت ---
                        comments=row.get('comments', ''),
                        admin_reply=row.get('admin_reply', ''),
                        created_by=current_user.username
                    )
                    db.session.add(new_record)
                    imported_count += 1
                    print(f"Importing row {imported_count}: {row.get('row_number', index + 1)}")
                except Exception as e:
                    print(f"Error importing row {index}: {e}")
                    skipped_count += 1
            
            db.session.commit()
            flash(f'{imported_count} رکورد با موفقیت از فایل اکسل وارد شد. {skipped_count} رکورد به خاطر خطا رد شد.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'خطا در پردازش فایل اکسل: {str(e)}', 'danger')
        finally:
            if os.path.exists(filepath): 
                os.remove(filepath)
    else:
        flash('فرمت فایل نامعتبر است. لطفاً فقط فایل .xlsx آپلود کنید.', 'danger')
    return redirect(url_for('main.reports'))

# --- Section 8: API Routes ---
@main_bp.route('/api/resource_status')
@login_required
def api_resource_status():
    try:
        import pytz
        tehran_tz = pytz.timezone('Asia/Tehran')
        now = datetime.now(tehran_tz)
        current_time_str = now.strftime("%H:%M:%S")
        today_jalali = jdatetime.date.fromgregorian(date=now.date()).strftime("%Y/%m/%d")
        
        print(f"DEBUG API: Current time: {current_time_str}, Current date (Jalali): {today_jalali}")
        
        status = {"transmission_lines": {}, "via_methods": {}}

        def parse_time(time_str):
            if not time_str or time_str in ["", "HH:MM:SS", "00:00:00"]: 
                return None
            try:
                if len(time_str.split(":")) == 2: 
                    time_str += ":00"
                h, m, s = map(int, time_str.split(":"))
                return h * 3600 + m * 60 + s
            except Exception as e:
                return None

        def is_resource_busy(current_seconds, start_seconds, end_seconds):
            if start_seconds is None: 
                return False
            if end_seconds is None or end_seconds == 0: 
                return current_seconds >= start_seconds
            if end_seconds < start_seconds: 
                return current_seconds >= start_seconds or current_seconds <= end_seconds
            else: 
                return start_seconds <= current_seconds <= end_seconds
        
        def is_resource_future(current_seconds, start_seconds):
            """بررسی اینکه آیا منبع در آینده رزرو شده است"""
            if start_seconds is None: 
                return False
            return start_seconds > current_seconds

        today_records = ShiftRecord.query.filter(
            ShiftRecord.date >= today_jalali,
            ShiftRecord.start_time.isnot(None),
            ShiftRecord.start_time != "",
            ShiftRecord.start_time != "HH:MM:SS"
        ).all()
        
        current_seconds = parse_time(current_time_str)
        if current_seconds is None: 
            current_seconds = 0

        def check_resource_utilization(resource_list, dict_key, model_attribute):
            for resource_name in resource_list:
                is_busy = False
                is_future = False
                currently_active_records = []
                future_records = []
                
                for record in today_records:
                    record_resource = getattr(record, model_attribute, None)
                    if record_resource == resource_name and record.start_time:
                        
                        start_seconds = parse_time(record.start_time)
                        end_seconds = parse_time(record.end_time) if record.end_time and record.end_time not in ["", "00:00:00", "HH:MM:SS"] else None
                        
                        if start_seconds is not None and is_resource_busy(current_seconds, start_seconds, end_seconds):
                            is_busy = True
                            currently_active_records.append({
                                "network": record.network_name or "نامشخص",
                                "start_time": record.start_time,
                                "end_time": record.end_time or "نامشخص",
                                "activity": record.activity,
                                "date": record.date
                            })
                        elif start_seconds is not None and is_resource_future(current_seconds, start_seconds):
                            is_future = True
                            future_records.append({
                                "network": record.network_name or "نامشخص",
                                "start_time": record.start_time,
                                "end_time": record.end_time or "نامشخص",
                                "activity": record.activity,
                                "date": record.date
                            })
                
                if is_busy and currently_active_records:
                    has_conflict = len(currently_active_records) > 1
                    
                    if has_conflict:
                        network_names = [r['network'] for r in currently_active_records]
                        conflict_message = f"⚠️ هشدار تداخل منابع!\n\nمنبع: {resource_name}\nشبکه‌های همزمان: {', '.join(network_names)}\nزمان: {current_time_str}"
                        print(f"ALARM: Conflict detected for {resource_name}. Displaying in app only.")

                    status[dict_key][resource_name] = {
                        "status": "busy",
                        "message": f"مشغول - {currently_active_records[0]['network']}",
                        "conflicts": currently_active_records,
                        "conflict": has_conflict
                    }
                elif is_future and future_records:
                    # --- تغییر کلیدی: اصلاح منطق برای پیدا کردن نزدیک‌ترین رزرو آینده ---
                    # مرتب‌سازی رکوردهای آینده بر اساس تاریخ و زمان
                    future_records.sort(key=lambda x: (x['date'], x['start_time']))
                    
                    # منطق جدید برای تشخیص تداخل آینده
                    has_conflict = False
                    for i in range(len(future_records) - 1):
                        # فقط رکوردهای هم‌روز را با هم مقایسه کن
                        if future_records[i]['date'] == future_records[i+1]['date']:
                            # اگر پایان رکورد فعلی از شروع رکورد بعدی بزرگتر باشد، تداخل وجود دارد
                            end_time_current = parse_time(future_records[i]['end_time'])
                            start_time_next = parse_time(future_records[i+1]['start_time'])
                            if end_time_current > start_time_next:
                                has_conflict = True
                                break # تداخل پیدا شد، دیگر ادامه نده
                    
                    status[dict_key][resource_name] = {
                        "status": "future",
                        "message": f"رزرو شده - {future_records[0]['network']} در {future_records[0]['date']} از {future_records[0]['start_time']}",
                        "future_records": future_records,
                        "conflict": has_conflict
                    }
                else:
                    status[dict_key][resource_name] = {"status": "free"}

        check_resource_utilization(TRANSMISSION_LINES, 'transmission_lines', 'transmission_line')
        check_resource_utilization(VIA_METHODS, 'via_methods', 'via_method')
        
        return jsonify(status)
        
    except Exception as e:
        print(f"❌ DEBUG API: Error in api_resource_status: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@main_bp.route('/api/filter_reports')
@login_required
def api_filter_reports():
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        network_list = request.args.getlist('network')
        activity_list = request.args.getlist('activity')
        
        query = ShiftRecord.query
        if start_date: 
            query = query.filter(ShiftRecord.date >= start_date)
        if end_date: 
            query = query.filter(ShiftRecord.date <= end_date)
        if network_list: 
            query = query.filter(ShiftRecord.network_name.in_(network_list))
        if activity_list: 
            query = query.filter(ShiftRecord.activity.in_(activity_list))
        
        records = query.order_by(ShiftRecord.id.desc()).all()
        data = []
        for r in records:
            data.append({
                'row_number': r.row_number, 'date': r.date, 'shift': r.shift, 'location': r.location,
                'network_name': r.network_name, 'activity': r.activity, 'deliverer': r.deliverer,
                'receiver': r.receiver, 'start_time': r.start_time, 'end_time': r.end_time,
                'duration': r.duration, 'created_by': r.created_by,
                'via_method': r.via_method, 'transmission_line': r.transmission_line,
                'comments': r.comments, 'admin_reply': r.admin_reply
            })
        
        return jsonify(data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@main_bp.route('/api/last_record')
@login_required
def api_last_record():
    last_record = ShiftRecord.query.order_by(ShiftRecord.id.desc()).first()
    if not last_record:
        return jsonify({'status': 'no_records'})
    record_data = {
        'date': last_record.date,
        'shift': last_record.shift,
        'activity': last_record.activity,
        'location': last_record.location,
        'network_name': last_record.network_name,
        'deliverer': last_record.deliverer,
        'receiver': last_record.receiver,
        'signal_time': last_record.signal_time,
        'start_time': last_record.start_time,
        'end_time': last_record.end_time,
        'shift_staff': last_record.shift_staff,
        'description': last_record.description,
        'comments': last_record.comments,
        'via_method': last_record.via_method,
        'transmission_line': last_record.transmission_line
    }
    return jsonify(record_data)

@main_bp.route('/api/last_monitor_report')
@login_required
def api_last_monitor_report():
    """
    آخرین گزارشی که توسط سیستم مانیتورینگ ثبت شده را برمی‌گرداند.
    """
    last_record = ShiftRecord.query.filter_by(created_by='system_monitor').order_by(ShiftRecord.id.desc()).first()
    
    if not last_record:
        return jsonify({'status': 'no_records'})
    
    # آماده‌سازی داده‌ها برای ارسال به فرانت‌اند
    record_data = {
        'date': last_record.date,
        'shift': last_record.shift,
        # نام فعالیت را پاک‌سازی می‌کنیم تا "(آلارم)" نداشته باشد
        'activity': last_record.activity.replace(' (آلارم)', ''), 
        'location': last_record.location,
        'network_name': last_record.network_name,
        'deliverer': last_record.deliverer,
        'receiver': last_record.receiver,
        'signal_time': last_record.signal_time,
        'start_time': last_record.start_time,
        'end_time': last_record.end_time,
        'shift_staff': last_record.shift_staff,
        'description': last_record.description,
        'comments': last_record.comments,
        'via_method': last_record.via_method,
        'transmission_line': last_record.transmission_line
    }
    return jsonify(record_data)

@main_bp.route('/update_comment/<int:record_id>', methods=['POST'])
@login_required
@admin_required
def update_comment(record_id):

    
    record = ShiftRecord.query.get_or_404(record_id)
    data = request.get_json()
    record.admin_reply = data.get('admin_reply', '')
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'پاسخ با موفقیت ذخیره شد.'})

@main_bp.route('/delete_record/<int:record_id>', methods=['POST'])
@login_required
@admin_required
def delete_record(record_id):

    
    record = ShiftRecord.query.get_or_404(record_id)
    db.session.delete(record)
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'رکورد با موفقیت حذف شد.'})

# --- Section 9: Report Functions ---
def send_daily_summary_to_bale():
    """ساخت فایل اکسل خلاصه روزانه + ارسال به بله + ارسال به ایمیل مدیران"""
    try:
        today_jalali = jdatetime.date.today().strftime("%Y/%m/%d")
        daily_records = ShiftRecord.query.filter_by(date=today_jalali).order_by(ShiftRecord.row_number).all()

        if not daily_records:
            print(f"هیچ رکوردی برای تاریخ {today_jalali} پیدا نشد.")
            return

        # ساخت DataFrame برای ذخیره در اکسل
        data = [{
            'ردیف': r.row_number, 'تاریخ': r.date, 'شیفت': r.shift, 'لوکیشن': r.location or '-',
            'نام شبکه': r.network_name or '-', 'فعالیت': r.activity or '-', 'تحویل‌دهنده': r.deliverer or '-',
            'تحویل‌گیرنده در نودال شهدا': r.receiver or '-', 'ساعت دریافت سیگنال': r.signal_time or '-',
            'ساعت شروع': r.start_time or '-', 'ساعت پایان': r.end_time or '-', 'مدت زمان': r.duration or '-',
            'از طریق': r.via_method or '-', 'خط ارسالی': r.transmission_line or '-', 'پرسنل شیفت': r.shift_staff or '-',
            'توضیحات': r.description or '-', 'کامنت': r.comments or '-', 'پاسخ ادمین': r.admin_reply or '-',
            'کاربر ثبت‌کننده': r.created_by
        } for r in daily_records]

        df = pd.DataFrame(data)

        reports_dir = os.path.join(APP_ROOT, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        filename = f"daily_summary_{today_jalali.replace('/', '-')}.xlsx"
        excel_path = os.path.join(reports_dir, filename)

        df.to_excel(excel_path, index=False, engine='openpyxl')
        print(f"فایل اکسل ذخیره شد: {excel_path}")

        caption = f"گزارش خلاصه روزانه\nتاریخ: {today_jalali}\nتعداد گزارش‌ها: {len(daily_records)}"

        send_to_bale_async(type="document", file_path=excel_path, filename=filename, caption=caption)
        print(f"گزارش روزانه با موفقیت به صف ارسال اضافه شد: {filename}")

        try:
            email_subject = f"گزارش خلاصه روزانه شیفت‌ها - {today_jalali}"
            email_body = f"سلام\n\nگزارش خلاصه روزانه شیفت‌ها برای تاریخ {today_jalali} آماده شده است.\nتعداد رکوردها: {len(daily_records)}\n\nفایل اکسل در پیوست این ایمیل قرار دارد.\n\nبا احترام"
            enqueue_email(subject=email_subject, body=email_body, attachment_path=excel_path, attachment_filename=filename)
            print("✅ Daily summary email enqueued for admins.")
        except Exception as e:
            print(f"❌ خطا در صف‌گذاری ایمیل گزارش روزانه: {e}")

    except Exception as e:
        print(f"خطا در ساخت گزارش روزانه: {e}")
        traceback.print_exc()

def send_weekly_summary_to_bale():
    """ساخت فایل اکسل خلاصه هفتگی + ارسال به بله"""
    try:
        start_date, end_date = get_jalali_date_range('weekly')
        print(f"ساخت گزارش هفتگی برای بازه {start_date} تا {end_date}")

        weekly_records = ShiftRecord.query.filter(ShiftRecord.date >= start_date, ShiftRecord.date <= end_date).order_by(ShiftRecord.row_number).all()

        if not weekly_records:
            print(f"هیچ رکوردی برای بازه {start_date} تا {end_date} پیدا نشد.")
            return

        data = [{
            'ردیف': r.row_number, 'تاریخ': r.date, 'شیفت': r.shift, 'لوکیشن': r.location or '-',
            'نام شبکه': r.network_name or '-', 'فعالیت': r.activity or '-', 'تحویل‌دهنده': r.deliverer or '-',
            'تحویل‌گیرنده در نودال شهدا': r.receiver or '-', 'ساعت دریافت سیگنال': r.signal_time or '-',
            'ساعت شروع': r.start_time or '-', 'ساعت پایان': r.end_time or '-', 'مدت زمان': r.duration or '-',
            'از طریق': r.via_method or '-', 'خط ارسالی': r.transmission_line or '-', 'پرسنل شیفت': r.shift_staff or '-',
            'توضیحات': r.description or '-', 'کامنت': r.comments or '-', 'پاسخ ادمین': r.admin_reply or '-',
            'کاربر ثبت‌کننده': r.created_by
        } for r in weekly_records]

        df = pd.DataFrame(data)
        reports_dir = os.path.join(APP_ROOT, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        filename = f"weekly_summary_{start_date.replace('/', '-')}_to_{end_date.replace('/', '-')}.xlsx"
        excel_path = os.path.join(reports_dir, filename)

        df.to_excel(excel_path, index=False, engine='openpyxl')
        print(f"فایل اکسل هفتگی ذخیره شد: {excel_path}")

        caption = f"گزارش خلاصه هفتگی\nبازه: {start_date} تا {end_date}\nتعداد گزارش‌ها: {len(weekly_records)}"
        send_to_bale_async(type="document", file_path=excel_path, filename=filename, caption=caption)

    except Exception as e:
        print(f"خطا در ساخت گزارش هفتگی: {e}")
        traceback.print_exc()

# --- Section 11: Test Routes ---
@main_bp.route('/test_daily_report')
@login_required
def test_daily_report():
    try:
        send_daily_summary_to_bale()
        flash("تست ارسال گزارش روزانه اجرا شد. لطفاً کنسول را بررسی کنید.", 'info')
    except Exception as e:
        traceback.print_exc()
        flash(f"خطا در تست: {e}", 'danger')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/send_weekly_summary_to_bale')
@login_required
def send_weekly_summary_to_bale_route():
    try:
        send_weekly_summary_to_bale()
        flash("گزارش هفتگی به صف ارسال اضافه شد.", 'info')
    except Exception as e:
        traceback.print_exc()
        flash(f'خطا در ارسال گزارش هفتگی: {e}', 'danger')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/test_bale_direct')
@login_required
def test_bale_direct():
    try:
        # خط from app import حذف شد تا کرش نکند
        # از تابعی که خودتان در همین فایل تعریف کرده‌اید استفاده می‌کنیم
        message = f"این یک تست مستقیم از اپلیکیشن در ساعت {datetime.now().strftime('%H:%M:%S')} است."
        current_app.logger.info("--- DIRECT BALE TEST STARTED ---")
        
        success = send_message_to_bale(message) # استفاده از تابع داخل همین فایل
        
        current_app.logger.info(f"--- DIRECT BALE TEST FINISHED. Success: {success} ---")
        if success:
            flash("تست مستقیم با موفقیت انجام شد! پیام به بله ارسال شد.", "success")
        else:
            flash("تست مستقیم ناموفق بود. لطفاً لاگ را بررسی کنید.", "danger")
    except Exception as e:
        current_app.logger.error(f"--- DIRECT BALE TEST: ERROR --- {e}")
        flash(f"خطایی در تست مستقیم رخ داد: {e}", "danger")
    return redirect(url_for('main.dashboard'))


# User-assigned shift inspections
from assigned_checklists import register_assigned_checklists, response_labels as _assigned_response_labels
register_assigned_checklists(main_bp)


from checklist_excel_reports import register_checklist_excel_reports
register_checklist_excel_reports(main_bp)
