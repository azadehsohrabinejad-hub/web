"""Excel exports for existing checklist records; cleanup approved deleted snapshots."""
import io
import json
from datetime import datetime,timedelta
import jdatetime
from flask import request,send_file,flash,redirect,url_for,current_app
from flask_login import login_required,current_user
from sqlalchemy import inspect,text,or_
from models import db,ShiftChecklist


def purge_deleted_checklist_history():
    tables=set(inspect(db.engine).get_table_names())
    count=0
    if 'assigned_checklist_change' in tables:
        result=db.session.execute(text("DELETE FROM assigned_checklist_change WHERE record_id IN (SELECT record_id FROM (SELECT record_id FROM assigned_checklist_change WHERE action='delete') AS removed)"))
        count+=result.rowcount
    if 'shift_checklist_audit' in tables:
        result=db.session.execute(text("DELETE FROM shift_checklist_audit WHERE checklist_id IN (SELECT checklist_id FROM (SELECT checklist_id FROM shift_checklist_audit WHERE action IN ('delete','reset')) AS removed)"))
        count+=result.rowcount
    db.session.commit()
    return count


def register_checklist_excel_reports(bp):
    from assigned_checklists import AssignedChecklistDefinition as Definition,AssignedChecklistRecord as Record,LABELS
    cleaned=False

    @bp.before_request
    def checklist_history_cleanup_once():
        nonlocal cleaned
        if not cleaned:
            purge_deleted_checklist_history();cleaned=True

    @bp.after_request
    def cleanup_deleted_public_checklists(response):
        if request.endpoint=='main.admin_shift_checklist' and request.method=='POST' and response.status_code<400:
            purge_deleted_checklist_history()
        return response

    @bp.app_context_processor
    def checklist_export_context():
        if request.endpoint!='main.reports' or not current_user.is_authenticated:return {}
        definitions=Definition.query.order_by(Definition.id).all()
        # Prior submissions remain exportable to their author after access is disabled.
        owned={r.kind for r in Record.query.filter_by(created_by=current_user.username).all()}
        choices=[dict(id=0,title='چک‌لیست عمومی — بازدید شیفت')]
        for d in definitions:
            if current_user.is_admin or current_user.id in json.loads(d.user_ids) or d.id in owned:
                choices.append(dict(id=d.id,title=d.title))
        existing={x['id'] for x in choices}
        for kind in sorted(owned-existing):choices.append(dict(id=kind,title=f'چک‌لیست اختصاصی {kind}'))
        return dict(checklist_export_choices=choices)

    def parse_date(value):
        if not value:return None
        value=value.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')).replace('-','/')
        y,m,d=map(int,value.split('/'))
        return datetime.combine(jdatetime.date(y,m,d).togregorian(),datetime.min.time())

    @bp.route('/reports/checklists/excel')
    @login_required
    def checklist_export_excel():
        try:
            kind=int(request.args.get('kind','0'))
            if kind not in (0,1,2,3):raise ValueError()
            start=parse_date(request.args.get('start_date','').strip());end=parse_date(request.args.get('end_date','').strip())
            if start and end and start>end:raise ValueError()
        except (ValueError,TypeError,OverflowError):
            flash('چک‌لیست یا بازهٔ تاریخ نامعتبر است؛ تاریخ شمسی را به صورت ۱۴۰۵/۰۷/۱۱ وارد کنید.','danger');return redirect(url_for('main.reports'))
        q=ShiftChecklist.query if kind==0 else Record.query.filter_by(kind=kind)
        if kind and not current_user.is_admin:
            d=db.session.get(Definition,kind)
            assigned=bool(d and current_user.id in json.loads(d.user_ids))
            if not assigned:q=q.filter_by(created_by=current_user.username)
        if start:q=q.filter((ShiftChecklist if kind==0 else Record).shift_start>=start)
        if end:q=q.filter((ShiftChecklist if kind==0 else Record).shift_start<end+timedelta(days=1))
        cls=ShiftChecklist if kind==0 else Record
        records=q.order_by(cls.shift_start.asc(),cls.id.asc()).all()
        if not records:
            flash('برای این چک‌لیست و بازهٔ تاریخ گزارشی یافت نشد.','warning');return redirect(url_for('main.reports'))
        from openpyxl import Workbook
        from openpyxl.styles import Font,PatternFill,Alignment
        wb=Workbook();summary=wb.active;summary.title='خلاصه ثبت‌ها';details=wb.create_sheet('جزئیات موارد')
        summary.append(['شناسه','چک‌لیست','تاریخ شیفت','شیفت','ثبت‌کننده','زمان ثبت','دمای سرور °C','تایید / انجام شده','مشکل دارد','بررسی نشده','توضیحات'])
        details.append(['شناسه ثبت','چک‌لیست','تاریخ شیفت','شیفت','ثبت‌کننده','مورد','وضعیت','توضیح مورد','دمای سرور °C','زمان ثبت'])
        def safe(value):
            # Force user-entered text to stay text, including Excel formula-like prefixes.
            return "'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value
        for r in records:
            title='بازدید شیفت عمومی' if kind==0 else r.title
            date=jdatetime.date.fromgregorian(date=r.shift_start.date()).strftime('%Y/%m/%d')
            stamp=r.created_at.strftime('%Y-%m-%d %H:%M:%S');answers=json.loads(r.answers)
            counts={s:sum(a['status']==s for a in answers) for s in LABELS}
            summary.append([safe(v) for v in [r.id,title,date,r.shift_name,r.created_by,stamp,r.temperature,counts['ok'],counts['issue'],counts['unknown'],r.notes]])
            for a in answers:details.append([safe(v) for v in [r.id,title,date,r.shift_name,r.created_by,a['label'],a.get('status_label',LABELS.get(a['status'],a['status'])),a.get('note',''),r.temperature,stamp]])
        for sheet in wb:
            sheet.sheet_view.rightToLeft=True;sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
            for cell in sheet[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='243B53')
            for row in sheet.iter_rows():
                for cell in row:cell.alignment=Alignment(horizontal='right',vertical='top',wrap_text=True)
            for col in sheet.columns:
                letter=col[0].column_letter;sheet.column_dimensions[letter].width=min(60,max(14,max(len(str(c.value or '')) for c in col)+2))
            sheet.sheet_properties.pageSetUpPr.fitToPage=True;sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A4;sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0;sheet.print_title_rows='1:1'
        output=io.BytesIO();wb.save(output);output.seek(0)
        return send_file(output,as_attachment=True,download_name=f'checklist_{kind}_{datetime.now():%Y%m%d_%H%M%S}.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
