import json
import hashlib
import secrets
import time
from datetime import datetime
import jdatetime
from flask import request,session,abort,render_template,redirect,url_for,flash,current_app
from flask_login import current_user,login_required
from models import db,ShiftRecord,Activity,Network,Staff

class OrdinaryReportChange(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    record_id=db.Column(db.Integer,nullable=False,index=True)
    action=db.Column(db.String(20),nullable=False)
    reason=db.Column(db.String(500),nullable=False)
    actor=db.Column(db.String(80),nullable=False)
    changed_at=db.Column(db.DateTime,nullable=False,default=datetime.now)
    before=db.Column(db.Text,nullable=False)
    after=db.Column(db.Text,nullable=True)

FIELDS=[('date','تاریخ شمسی'),('shift','شیفت'),('location','محل'),('network_name','شبکه'),('activity','فعالیت'),('deliverer','تحویل‌دهنده'),('receiver','تحویل‌گیرنده'),('signal_time','ساعت دریافت سیگنال'),('start_time','ساعت شروع'),('end_time','ساعت پایان'),('via_method','نوع ارتباط'),('transmission_line','خط انتقال'),('shift_staff','کارکنان شیفت'),('description','شرح گزارش'),('comments','توضیحات')]

def snapshot(r):
    return {col.name:(getattr(r,col.name).isoformat() if isinstance(getattr(r,col.name),datetime) else getattr(r,col.name)) for col in r.__table__.columns}

def revision(r):return hashlib.sha256(json.dumps(snapshot(r),sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def allowed(r):return current_user.is_admin or r.created_by==current_user.username

def csrf():
    if not session.get('ordinary_changes_token'):session['ordinary_changes_token']=secrets.token_urlsafe(32)
    return session['ordinary_changes_token']

def check_csrf():
    if not session.get('ordinary_changes_token') or not secrets.compare_digest(str(request.form.get('token','')),session['ordinary_changes_token']):abort(403)

def register_ordinary_report_changes(bp):
    # Route existing edit/delete controls through the same reason gate.
    @bp.before_request
    def reason_gate_legacy_reports():
        if request.endpoint in ('main.edit_record','main.delete_record') and current_user.is_authenticated:
            return redirect(url_for('main.ordinary_report_reason',record_id=request.view_args['record_id']),code=303)

    @bp.route('/reports/manage')
    @login_required
    def ordinary_report_picker():
        q=ShiftRecord.query
        if not current_user.is_admin:q=q.filter_by(created_by=current_user.username)
        date=request.args.get('date','').strip();network=request.args.get('network','').strip()
        if date:q=q.filter_by(date=date.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789')))
        if network:q=q.filter_by(network_name=network)
        page=q.order_by(ShiftRecord.id.desc()).paginate(page=max(1,request.args.get('page',1,type=int)),per_page=50,error_out=False)
        return render_template('ordinary_report_picker.html',page=page,date=date,network=network)

    @bp.route('/reports/<int:record_id>/reason',methods=['GET','POST'])
    @login_required
    def ordinary_report_reason(record_id):
        r=db.session.get(ShiftRecord,record_id)
        if not r:abort(404)
        if not allowed(r):abort(403)
        if request.method=='POST':
            check_csrf();reason=request.form.get('reason','').strip();action=request.form.get('action')
            if action not in ('edit','delete') or not 1<=len(reason)<=500:
                flash('علت ویرایش یا حذف را بنویسید؛ حداکثر ۵۰۰ نویسه.','danger')
            else:
                ticket=secrets.token_urlsafe(24)
                gates=session.get('ordinary_report_gates',{})
                gates={k:v for k,v in gates.items() if time.time()-v['time']<1800}
                if len(gates)>=10:gates.pop(next(iter(gates)))
                gates[ticket]=dict(record_id=r.id,reason=reason,action=action,revision=revision(r),time=time.time())
                session['ordinary_report_gates']=gates
                return redirect(url_for('main.ordinary_report_apply',record_id=r.id,ticket=ticket))
        return render_template('ordinary_report_reason.html',record=r,token=csrf())

    @bp.route('/reports/<int:record_id>/change',methods=['GET','POST'])
    @login_required
    def ordinary_report_apply(record_id):
        r=db.session.get(ShiftRecord,record_id)
        if not r:abort(404)
        if not allowed(r):abort(403)
        ticket=request.args.get('ticket','');gate=session.get('ordinary_report_gates',{}).get(ticket)
        if not gate or gate['record_id']!=r.id or time.time()-gate['time']>=1800:
            flash('ابتدا علت تغییر را ثبت کنید.','warning');return redirect(url_for('main.ordinary_report_reason',record_id=r.id))
        if revision(r)!=gate['revision']:
            flash('این گزارش تغییر کرده است؛ دوباره آن را انتخاب کنید.','warning');return redirect(url_for('main.ordinary_report_reason',record_id=r.id))
        values={key:getattr(r,key) or '' for key,_ in FIELDS}
        if request.method=='POST':
            check_csrf();before=snapshot(r)
            if gate['action']=='edit':
                values={key:request.form.get(key,'').strip() for key,_ in FIELDS}
                if current_user.is_admin:values['admin_reply']=request.form.get('admin_reply','').strip()
                error=validate(values)
                if error:
                    flash(error,'danger');return render_form(r,gate,values)
                from routes import calculate_duration
                duration=calculate_duration(values['start_time'],values['end_time'])
                updates=dict(values,duration=duration)
            change=OrdinaryReportChange(record_id=r.id,action=gate['action'],reason=gate['reason'],actor=current_user.username,before=json.dumps(before,ensure_ascii=False))
            # Atomic content match prevents a simultaneous change from being overwritten.
            exact={col.name:getattr(r,col.name) for col in r.__table__.columns}
            q=ShiftRecord.query.filter_by(**exact)
            if gate['action']=='delete':affected=q.delete(synchronize_session=False)
            else:
                affected=q.update(updates,synchronize_session=False)
                after=dict(before,**updates);change.after=json.dumps(after,ensure_ascii=False)
            if affected!=1:
                db.session.rollback();flash('گزارش هم‌زمان تغییر کرده است.','warning');return redirect(url_for('main.ordinary_report_picker'))
            db.session.add(change);db.session.commit()
            gates=session.get('ordinary_report_gates',{});gates.pop(ticket,None);session['ordinary_report_gates']=gates
            try:
                from bale_service import send_to_bale_async
                verb='ویرایش' if gate['action']=='edit' else 'حذف'
                msg=f"{verb} گزارش ردیف {before['row_number']} | {before['date']} | {before['network_name'] or ''}\nتوسط: {current_user.username}\nعلت: {gate['reason']}"
                if gate['action']=='edit':msg+='\n'+'\n'.join(f'{label}: {values[key]}' for key,label in FIELDS if values[key])
                send_to_bale_async(type='message',text=msg)
            except Exception:current_app.logger.exception('Report change saved; Bale enqueue failed')
            flash('تغییر گزارش با ثبت علت و سابقه انجام شد.','success');return redirect(url_for('main.ordinary_report_history'))
        return render_form(r,gate,values)

    def validate(values):
        try:jdatetime.datetime.strptime(values['date'].translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789')),'%Y/%m/%d')
        except (ValueError,TypeError):return 'تاریخ شمسی معتبر وارد کنید.'
        values['date']=values['date'].translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789'))
        from routes import SHIFTS
        if values['shift'] not in SHIFTS:return 'شیفت معتبر انتخاب کنید.'
        activity=Activity.query.filter_by(name=values['activity']).first()
        if not activity:return 'فعالیت معتبر انتخاب کنید.'
        if any(not values.get(key) for key in activity.get_required_fields()):return 'فیلدهای الزامی این فعالیت را تکمیل کنید.'
        for key in ('signal_time','start_time','end_time'):
            if values[key]:
                try:datetime.strptime(values[key],'%H:%M:%S')
                except ValueError:return 'ساعت‌ها را به صورت HH:MM:SS وارد کنید.'
        for key,value in values.items():
            col=ShiftRecord.__table__.columns[key]
            limit=getattr(col.type,'length',None) or 10000
            if len(value)>limit:return 'متن یکی از فیلدها بیش از حد طولانی است.'
        return None

    def render_form(r,gate,values):
        from routes import SHIFTS,VIA_METHODS,TRANSMISSION_LINES
        choices={'shift':SHIFTS,'activity':[a.name for a in Activity.query.order_by(Activity.name)],'network_name':[n.name for n in Network.query.order_by(Network.name)],'via_method':VIA_METHODS,'transmission_line':TRANSMISSION_LINES}
        return render_template('ordinary_report_change.html',record=r,gate=gate,values=values,fields=FIELDS,choices=choices,token=csrf())

    @bp.route('/reports/change-history')
    @login_required
    def ordinary_report_history():
        q=OrdinaryReportChange.query
        if not current_user.is_admin:q=q.filter_by(actor=current_user.username)
        page=q.order_by(OrdinaryReportChange.id.desc()).paginate(page=max(1,request.args.get('page',1,type=int)),per_page=30,error_out=False)
        entries=[dict(change=c,before=json.loads(c.before),after=json.loads(c.after) if c.after else None) for c in page.items]
        return render_template('ordinary_report_history.html',entries=entries,page=page,fields=FIELDS)
