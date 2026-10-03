"""Three optional, user-assigned inspections with configurable response labels."""
import json
import math
import secrets
import hashlib
from datetime import datetime, timedelta
from flask import request, session, jsonify, render_template, redirect, url_for, flash, abort, current_app
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import jdatetime
from models import db, User
from bale_service import send_to_bale_async

LABELS = {'ok': 'سالم', 'issue': 'مشکل دارد', 'unknown': 'قابل بررسی نبود'}

class AssignedChecklistDefinition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    items = db.Column(db.Text, nullable=False)
    user_ids = db.Column(db.Text, nullable=False, default='[]')
    temperature_required = db.Column(db.Boolean, nullable=False, default=False)

class AssignedChecklistOptions(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    labels_json = db.Column(db.Text, nullable=False)


def response_labels(kind):
    options = db.session.get(AssignedChecklistOptions, kind)
    return json.loads(options.labels_json) if options else dict(LABELS)


class AssignedChecklistRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.Integer, nullable=False)
    shift_start = db.Column(db.DateTime, nullable=False)
    shift_name = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    answers = db.Column(db.Text, nullable=False)
    temperature = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=False, default='')
    created_by = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    __table_args__ = (db.UniqueConstraint('kind', 'shift_start', name='uq_assigned_checklist_shift'),)

    @property
    def date_label(self):
        return jdatetime.date.fromgregorian(date=self.shift_start.date()).strftime('%Y/%m/%d')


def shift_at(now=None):
    now = now or datetime.now()
    if 6 <= now.hour < 14:
        return now.replace(hour=6, minute=0, second=0, microsecond=0), 'صبح'
    if 14 <= now.hour < 22:
        return now.replace(hour=14, minute=0, second=0, microsecond=0), 'ظهر'
    day = now if now.hour >= 22 else now - timedelta(days=1)
    return day.replace(hour=22, minute=0, second=0, microsecond=0), 'شب'


def permitted(definition):
    return bool(definition and definition.enabled and int(current_user.id) in json.loads(definition.user_ids))


def version(definition):
    data = f'{definition.title}|{definition.items}|{definition.temperature_required}|{json.dumps(response_labels(definition.id), sort_keys=True)}'
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def token():
    if not session.get('assigned_checklist_token'):
        session['assigned_checklist_token'] = secrets.token_urlsafe(32)
    return session['assigned_checklist_token']


def check_token(value):
    if not secrets.compare_digest(str(value or ''), session.get('assigned_checklist_token', '')) or not session.get('assigned_checklist_token'):
        abort(403)


def register_assigned_checklists(bp):
    @bp.before_request
    def assigned_session_lifetime():
        if current_user.is_authenticated:
            session.permanent = True

    @bp.app_context_processor
    def assigned_context():
        if not current_user.is_authenticated:
            return {}
        if request.endpoint not in ('main.form', 'main.records', 'main.assigned_checklist_admin'):
            return {}
        try:
            definitions = AssignedChecklistDefinition.query.filter_by(enabled=True).all()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Assigned checklist tables unavailable; ordinary form remains usable')
            return {}
        lists = [d for d in definitions if permitted(d)]
        result = {'assigned_lists': lists, 'assigned_token': token()}
        if request.endpoint == 'main.records':
            query = AssignedChecklistRecord.query
            if not current_user.is_admin:
                ids = [d.id for d in lists]
                query = query.filter(AssignedChecklistRecord.kind.in_(ids))
            result['assigned_recent_records'] = query.order_by(AssignedChecklistRecord.shift_start.desc(), AssignedChecklistRecord.id.desc()).limit(30).all()
            result['assigned_labels'] = LABELS
            result['assigned_json_loads'] = json.loads
        return result

    @bp.route('/admin/assigned-checklists', methods=['GET', 'POST'])
    @login_required
    def assigned_checklist_admin():
        if not current_user.is_admin:
            abort(403)
        users = User.query.order_by(User.username).all()
        if request.method == 'POST':
            check_token(request.form.get('token'))
            kind = request.form.get('kind', type=int)
            answer_labels = {key: request.form.get('answer_'+key, LABELS[key]).strip() for key in LABELS}
            if any(not 1 <= len(value) <= 60 for value in answer_labels.values()) or len(set(answer_labels.values())) != 3:
                flash('سه پاسخ متفاوت با حداکثر ۶۰ نویسه وارد کنید.', 'danger')
                return redirect(url_for('main.assigned_checklist_admin'))
            if kind == 0:
                options = db.session.get(AssignedChecklistOptions, 0)
                if options is None:
                    options = AssignedChecklistOptions(id=0)
                    db.session.add(options)
                options.labels_json = json.dumps(answer_labels, ensure_ascii=False)
                db.session.commit()
                flash('پاسخ‌های چک‌لیست عمومی ذخیره شد.', 'success')
                return redirect(url_for('main.assigned_checklist_admin'))
            title = request.form.get('title', '').strip()
            labels = [s.strip() for s in request.form.get('items', '').splitlines() if s.strip()]
            try:
                user_ids = sorted(set(int(s) for s in request.form.getlist('users')))
            except ValueError:
                abort(400)
            if kind not in (1, 2, 3) or not 1 <= len(title) <= 160 or not 1 <= len(labels) <= 40 or any(len(s) > 200 for s in labels) or not set(user_ids) <= {u.id for u in users}:
                flash('عنوان، موارد یا کاربران انتخاب‌شده نامعتبر هستند؛ بین ۱ تا ۴۰ مورد وارد کنید.', 'danger')
                return redirect(url_for('main.assigned_checklist_admin'))
            definition = db.session.get(AssignedChecklistDefinition, kind)
            if definition is None:
                definition = AssignedChecklistDefinition(id=kind)
                db.session.add(definition)
            definition.title = title
            definition.items = json.dumps([{'id': str(i+1), 'label': label} for i, label in enumerate(labels)], ensure_ascii=False)
            definition.user_ids = json.dumps(user_ids)
            definition.enabled = request.form.get('enabled') == 'on'
            definition.temperature_required = request.form.get('temperature_required') == 'on'
            options = db.session.get(AssignedChecklistOptions, kind)
            if options is None:
                options = AssignedChecklistOptions(id=kind)
                db.session.add(options)
            options.labels_json = json.dumps(answer_labels, ensure_ascii=False)
            db.session.commit()
            flash('تنظیمات چک‌لیست و دسترسی افراد ذخیره شد.', 'success')
            return redirect(url_for('main.assigned_checklist_admin'))
        configs = []
        for kind in (1, 2, 3):
            d = db.session.get(AssignedChecklistDefinition, kind)
            configs.append({'id': kind, 'title': d.title if d else f'چک‌لیست اختصاصی {kind}',
                'enabled': d.enabled if d else False,
                'labels': '\n'.join(i['label'] for i in json.loads(d.items)) if d else 'مورد بازدید ۱\nمورد بازدید ۲',
                'user_ids': json.loads(d.user_ids) if d else [],
                'temperature_required': d.temperature_required if d else False, 'answer_labels': response_labels(kind)})
        return render_template('assigned_checklist_admin.html', configs=configs, users=users, assigned_token=token(), public_labels=response_labels(0))

    @bp.route('/api/assigned-checklists', methods=['GET'])
    @login_required
    def assigned_checklist_status():
        now = datetime.now()
        start, name = shift_at(now)
        result = []
        for d in AssignedChecklistDefinition.query.filter_by(enabled=True).all():
            if not permitted(d):
                continue
            record = AssignedChecklistRecord.query.filter_by(kind=d.id, shift_start=start).first()
            result.append({'id': d.id, 'title': d.title, 'items': json.loads(d.items), 'version': version(d),
                'temperature_required': d.temperature_required, 'answer_labels': response_labels(d.id),
                'completed': {'created_by': record.created_by, 'time': record.created_at.strftime('%H:%M'),
                    'answers': json.loads(record.answers), 'temperature': record.temperature} if record else None})
        return jsonify(lists=result, shift_start=start.isoformat(), shift_name=name,
            seconds_remaining=((start+timedelta(hours=8))-now).total_seconds())

    @bp.route('/api/assigned-checklists/<int:kind>', methods=['POST'])
    @login_required
    def assigned_checklist_save(kind):
        data = request.get_json(silent=True) or {}
        check_token(data.get('token'))
        d = db.session.get(AssignedChecklistDefinition, kind)
        if not permitted(d):
            abort(403)
        start, name = shift_at()
        if data.get('shift_start') != start.isoformat() or data.get('version') != version(d):
            return jsonify(error='شیفت یا موارد چک‌لیست تغییر کرده‌اند؛ پنجره را ببندید و دوباره باز کنید.'), 409
        if AssignedChecklistRecord.query.filter_by(kind=kind, shift_start=start).first():
            return jsonify(error='این چک‌لیست در این شیفت قبلاً ثبت شده است.'), 409
        submitted = data.get('answers')
        items = json.loads(d.items)
        if not isinstance(submitted, dict) or set(submitted) != {i['id'] for i in items}:
            return jsonify(error='همهٔ موارد را تعیین وضعیت کنید.'), 400
        answers = []
        for item in items:
            a = submitted[item['id']]
            if not isinstance(a, dict) or a.get('status') not in LABELS:
                return jsonify(error='پاسخ نامعتبر است.'), 400
            note = str(a.get('note', '')).strip()
            if len(note) > 500 or (a['status'] == 'issue' and not note):
                return jsonify(error='برای مورد مشکل‌دار، شرح مشکل لازم است.'), 400
            answers.append(dict(item, status=a['status'], status_label=response_labels(kind)[a['status']], note=note))
        temperature = None
        if d.temperature_required:
            try:
                temperature = float(str(data.get('temperature', '')).replace('٫', '.'))
            except (ValueError, TypeError):
                return jsonify(error='دما را عددی وارد کنید.'), 400
            if not math.isfinite(temperature) or not -100 <= temperature <= 150:
                return jsonify(error='دمای واردشده معتبر نیست.'), 400
        notes = str(data.get('notes', '')).strip()
        if len(notes) > 1000:
            return jsonify(error='توضیحات بیش از حد طولانی است.'), 400
        record = AssignedChecklistRecord(kind=kind, shift_start=start, shift_name=name, title=d.title,
            answers=json.dumps(answers, ensure_ascii=False), temperature=temperature, notes=notes, created_by=current_user.username)
        try:
            db.session.add(record)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify(error='این چک‌لیست در این شیفت قبلاً ثبت شده است.'), 409
        message = f'{record.title} | شیفت {name} | {record.date_label}\nثبت: {record.created_at:%H:%M} | {record.created_by}'
        if temperature is not None:
            message += f'\nدمای سرور: {temperature:g} °C'
        message += '\n' + '\n'.join(f"{ {'ok': '✅', 'issue': '❌', 'unknown': '🟡'}.get(a['status'], '🟡') } {a['label']}: {a.get('status_label', LABELS[a['status']])}" + (f" — {a['note']}" if a['note'] else '') for a in answers)
        if notes:
            message += '\nتوضیحات: ' + notes
        try:
            send_to_bale_async(type='message', text=message)
        except Exception:
            current_app.logger.exception('Assigned checklist saved but Bale enqueue failed: %s', record.id)
        return jsonify(ok=True), 201



