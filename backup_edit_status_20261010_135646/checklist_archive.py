"""Assigned checklist archive, printable reports and audited mutations."""
import hashlib
import json
import math
from datetime import datetime, timedelta
import jdatetime
from flask import request, render_template, redirect, url_for, flash, abort, current_app
from flask_login import current_user, login_required
from sqlalchemy import or_
from models import db

class AssignedChecklistChange(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, nullable=False, index=True)
    kind = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    actor = db.Column(db.String(80), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    snapshot = db.Column(db.Text, nullable=False)
    after_snapshot = db.Column(db.Text, nullable=True)


def register_checklist_archive(bp):
    from assigned_checklists import (AssignedChecklistRecord as Record, AssignedChecklistDefinition as Definition, shift_at,
        LABELS, response_labels, check_token, token)
    from bale_service import send_to_bale_async

    def snapshot(r):
        return dict(id=r.id, kind=r.kind, title=r.title, shift_start=r.shift_start.isoformat(),
            shift_name=r.shift_name, answers=json.loads(r.answers), temperature=r.temperature,
            notes=r.notes, created_by=r.created_by, created_at=r.created_at.isoformat())

    def revision(r):
        return hashlib.sha256(json.dumps(snapshot(r),sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    def can_manage(r):
        return current_user.is_admin or r.created_by == current_user.username

    def authorized_kinds():
        return [d.id for d in Definition.query.all() if current_user.id in json.loads(d.user_ids)]

    def accessible(r):
        return current_user.is_admin or r.created_by == current_user.username or r.kind in authorized_kinds()

    def decorate(s):
        s=dict(s)
        s['date_label']=jdatetime.date.fromgregorian(date=datetime.fromisoformat(s['shift_start']).date()).strftime('%Y/%m/%d')
        return s

    def announce(r, action, reason):
        icons={'ok':'✅','issue':'❌','unknown':'🟡'}
        s=decorate(snapshot(r))
        title={'edit':'ویرایش چک‌لیست','reset':'بازنشانی بازدید این شیفت','delete':'حذف چک‌لیست'}[action]
        lines=[f"{title}: {r.title} | شیفت {r.shift_name} | {s['date_label']}",
            f'توسط: {current_user.username}',f'علت: {reason}']
        if action=='edit':
            lines += [f"{icons.get(a['status'],'🟡')} {a['label']}: {a.get('status_label',LABELS[a['status']])}" + (f" — {a['note']}" if a.get('note') else '') for a in s['answers']]
            if r.temperature is not None: lines.append(f'دمای سرور: {r.temperature:g} °C')
            if r.notes: lines.append('توضیحات: '+r.notes)
        try: send_to_bale_async(type='message',text='\n'.join(lines))
        except Exception: current_app.logger.exception('Checklist change committed; Bale enqueue failed')

    @bp.route('/assigned-checklists/archive')
    @login_required
    def assigned_checklist_archive():
        query=Record.query
        changes=AssignedChecklistChange.query
        if not current_user.is_admin:
            ids=authorized_kinds()
            query=query.filter(or_(Record.kind.in_(ids),Record.created_by==current_user.username))
            # Audits remain accessible to their original author after access revocation.
        kind=request.args.get('kind',type=int)
        if kind: query=query.filter_by(kind=kind);changes=changes.filter_by(kind=kind)
        date_text=request.args.get('date','').strip()
        if date_text:
            try:
                y,m,d=map(int,date_text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789')).replace('-','/').split('/'))
                date=jdatetime.date(y,m,d).togregorian()
            except (ValueError,TypeError):
                flash('تاریخ را به صورت ۱۴۰۵/۰۷/۱۱ وارد کنید.','danger');return redirect(url_for('main.assigned_checklist_archive'))
            start=datetime.combine(date,datetime.min.time());end=start+timedelta(days=1)
            query=query.filter(Record.shift_start>=start,Record.shift_start<end)
        records=query.order_by(Record.shift_start.desc(),Record.id.desc()).all()
        history=[]
        for change in changes.order_by(AssignedChecklistChange.id.desc()).all():
            s=decorate(json.loads(change.snapshot))
            if not current_user.is_admin and change.kind not in ids and s['created_by']!=current_user.username:continue
            if date_text and datetime.fromisoformat(s['shift_start']).date()!=date:continue
            history.append(dict(change=change,before=s,after=decorate(json.loads(change.after_snapshot)) if change.after_snapshot else None))
        return render_template('assigned_checklist_archive.html', records=[dict(data=decorate(snapshot(r)),revision=revision(r),manage=can_manage(r)) for r in records],history=history,token=token(),labels=LABELS,kind=kind,date_text=date_text)

    @bp.route('/assigned-checklists/<int:record_id>/manage',methods=['GET','POST'])
    @login_required
    def assigned_checklist_manage(record_id):
        r=db.session.get(Record,record_id)
        if not r:abort(404)
        if not can_manage(r):abort(403)
        if request.method=='GET':
            return render_template('assigned_checklist_edit.html',record=decorate(snapshot(r)),revision=revision(r),token=token(),labels=response_labels(r.kind))
        check_token(request.form.get('token'))
        # Reject a stale form before applying changes.
        r=Record.query.filter_by(id=record_id).with_for_update().first()
        if not r:abort(409)
        if request.form.get('revision')!=revision(r):
            flash('گزارش تغییر کرده است؛ دوباره باز کنید.','warning');return redirect(url_for('main.assigned_checklist_manage',record_id=r.id))
        action=request.form.get('action');reason=request.form.get('reason','').strip()
        if action not in ('edit','delete','reset') or not 3<=len(reason)<=500:
            flash('علت ویرایش یا حذف الزامی است (حداکثر ۵۰۰ نویسه).','danger');return redirect(url_for('main.assigned_checklist_manage',record_id=r.id))
        if action=='reset' and r.shift_start!=shift_at()[0]:
            flash('بازنشانی فقط برای بازدید شیفت جاری مجاز است؛ بازدیدهای قدیمی را ویرایش یا حذف کنید.','danger')
            return redirect(url_for('main.assigned_checklist_manage',record_id=r.id))
        before=snapshot(r)
        before_answers=r.answers
        if action=='edit':
            answers=json.loads(r.answers)
            for a in answers:
                status=request.form.get('status_'+str(a['id']));note=request.form.get('note_'+str(a['id']),'').strip()
                if status not in LABELS or len(note)>500 or (status=='issue' and not note):
                    flash('همه پاسخ‌ها را مشخص کنید؛ برای مشکل، توضیح لازم است.','danger');return redirect(url_for('main.assigned_checklist_manage',record_id=r.id))
                a.update(status=status,note=note,status_label=response_labels(r.kind)[status])
            temp=request.form.get('temperature','').strip()
            try: temperature=float(temp.replace('٫','.')) if temp else None
            except ValueError:temperature=float('nan')
            if (r.temperature is not None and temperature is None) or (temperature is not None and (not math.isfinite(temperature) or not -100<=temperature<=150)):
                flash('دمای معتبر وارد کنید.','danger');return redirect(url_for('main.assigned_checklist_manage',record_id=r.id))
            notes=request.form.get('notes','').strip()
            if len(notes)>1000:abort(400)
            r.answers=json.dumps(answers,ensure_ascii=False);r.temperature=temperature;r.notes=notes
        change=AssignedChecklistChange(record_id=r.id,kind=r.kind,action=action,reason=reason,actor=current_user.username,snapshot=json.dumps(before,ensure_ascii=False),after_snapshot=json.dumps(snapshot(r),ensure_ascii=False) if action=='edit' else None)
        after_values=dict(answers=r.answers,temperature=r.temperature,notes=r.notes)
        # Match the stored content atomically; simultaneous submissions cannot lose an update.
        db.session.expunge(r)
        match=Record.query.filter_by(id=record_id,answers=before_answers,temperature=before['temperature'],notes=before['notes'])
        affected=match.delete(synchronize_session=False) if action=='delete' else match.update(after_values,synchronize_session=False)
        if affected!=1:
            db.session.rollback();flash('گزارش هم‌زمان تغییر کرده است؛ دوباره باز کنید.','warning')
            return redirect(url_for('main.assigned_checklist_archive'))
        db.session.add(change)
        db.session.commit();announce(r,action,reason)
        flash('گزارش ویرایش شد.' if action=='edit' else 'بازدید این شیفت بازنشانی شد؛ سابقه قبلی محفوظ است و اکنون امکان ثبت مجدد وجود دارد.' if action=='reset' else 'گزارش حذف شد؛ نسخه قبلی در سابقه بایگانی محفوظ است و ثبت مجدد این شیفت امکان‌پذیر شد.','success')
        return redirect(url_for('main.assigned_checklist_archive'))
