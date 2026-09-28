# api_routes.py
import pytz
import json
import traceback
import jdatetime
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from models import ShiftRecord
from routes import TRANSMISSION_LINES, VIA_METHODS

# تعریف یک Blueprint جدید
api_bp = Blueprint('api', __name__, url_prefix='/api')

def parse_time(time_str):
    """تبدیل زمان HH:MM:SS به ثانیه از نیمه‌شب"""
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
    """بررسی اینکه آیا منبع در حال حاضر مشغول است"""
    if start_seconds is None: 
        return False
    if end_seconds is None or end_seconds == 0: 
        return current_seconds >= start_seconds
    if end_seconds < start_seconds: 
        # شیفت شبانه‌روزی
        return current_seconds >= start_seconds or current_seconds <= end_seconds
    else: 
        return start_seconds <= current_seconds <= end_seconds

def is_resource_future(current_seconds, start_seconds):
    """بررسی اینکه آیا منبع در آینده رزرو شده است"""
    if start_seconds is None: 
        return False
    return start_seconds > current_seconds

def check_resource_utilization(resource_list, model_attribute, today_records, current_seconds, dict_key):
    """تابع اصلی چک کردن وضعیت منابع (برای جلوگیری از تکرار کد)"""
    status = {}
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
                print(f"ALARM: Conflict detected for {resource_name}. Displaying in app only.")

            status[resource_name] = {
                "status": "busy",
                "message": f"مشغول - {currently_active_records[0]['network']}",
                "conflicts": currently_active_records,
                "conflict": has_conflict
            }
        elif is_future and future_records:
            future_records.sort(key=lambda x: (x['date'], x['start_time']))
            
            # منطق تشخیص تداخل آینده
            has_conflict = False
            for i in range(len(future_records) - 1):
                if future_records[i]['date'] == future_records[i+1]['date']:
                    end_time_current = parse_time(future_records[i]['end_time'])
                    start_time_next = parse_time(future_records[i+1]['start_time'])
                    if end_time_current and start_time_next and end_time_current > start_time_next:
                        has_conflict = True
                        break 
            
            status[resource_name] = {
                "status": "future",
                "message": f"رزرو شده - {future_records[0]['network']} در {future_records[0]['date']} از {future_records[0]['start_time']}",
                "future_records": future_records,
                "conflict": has_conflict
            }
        else:
            status[resource_name] = {"status": "free"}
    return status

@api_bp.route('/resource_status')
@login_required
def api_resource_status():
    try:
        tehran_tz = pytz.timezone('Asia/Tehran')
        now = datetime.now(tehran_tz)
        current_time_str = now.strftime("%H:%M:%S")
        today_jalali = jdatetime.date.fromgregorian(date=now.date()).strftime("%Y/%m/%d")
        
        today_records = ShiftRecord.query.filter(
            ShiftRecord.date >= today_jalali,
            ShiftRecord.start_time.isnot(None),
            ShiftRecord.start_time != "",
            ShiftRecord.start_time != "HH:MM:SS"
        ).all()
        
        current_seconds = parse_time(current_time_str)
        if current_seconds is None: 
            current_seconds = 0

        transmission_lines_status = check_resource_utilization(TRANSMISSION_LINES, 'transmission_line', today_records, current_seconds, 'transmission_lines')
        via_methods_status = check_resource_utilization(VIA_METHODS, 'via_method', today_records, current_seconds, 'via_methods')
        
        return jsonify({"transmission_lines": transmission_lines_status, "via_methods": via_methods_status})
        
    except Exception as e:
        print(f"❌ DEBUG API: Error in api_resource_status: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/filter_reports')
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

@api_bp.route('/last_record')
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

@api_bp.route('/last_monitor_report')
@login_required
def api_last_monitor_report():
    """
    آخرین گزارشی که توسط سیستم مانیتورینگ ثبت شده را برمی‌گرداند.
    """
    last_record = ShiftRecord.query.filter_by(created_by='system_monitor').order_by(ShiftRecord.id.desc()).first()
    
    if not last_record:
        return jsonify({'status': 'no_records'})
    
    record_data = {
        'date': last_record.date,
        'shift': last_record.shift,
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