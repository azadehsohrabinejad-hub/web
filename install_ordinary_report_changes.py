import ast
import shutil
from pathlib import Path
from datetime import datetime

def install(root,package):
    root=root.resolve();package=package.resolve()
    s=(root/'routes.py').read_text(encoding='utf-8-sig')
    if 'register_ordinary_report_changes(main_bp)' not in s:s+='\nfrom ordinary_report_changes import register_ordinary_report_changes\nregister_ordinary_report_changes(main_bp)\n'
    ast.parse(s);changes={'routes.py':s}
    s=(root/'templates/form.html').read_text(encoding='utf-8-sig')
    if 'ordinary_report_picker' not in s:
        anchor='<button type="button" class="btn btn-info" onclick="copyLastReport()">'
        if anchor not in s:raise ValueError('Copy previous report button not found; no files changed.')
        s=s.replace(anchor,'''<a class="btn btn-outline-primary" href="{{ url_for('main.ordinary_report_picker') }}">ویرایش / حذف گزارش</a>\n                            '''+anchor,1)
    changes['templates/form.html']=s
    s=(root/'templates/records.html').read_text(encoding='utf-8-sig')
    if 'ordinary_report_history' not in s:s=s.replace('{% block content %}', '''{% block content %}\n<p><a class="btn btn-outline-primary" href="{{ url_for('main.ordinary_report_history') }}">سابقهٔ ویرایش و حذف گزارش‌ها</a></p>''',1)
    changes['templates/records.html']=s
    files=['ordinary_report_changes.py']+['templates/'+n for n in ('ordinary_report_picker.html','ordinary_report_reason.html','ordinary_report_change.html','ordinary_report_history.html')]
    for name in files:
        if not (package/name).is_file():raise FileNotFoundError(name)
    backup=root/'backups'/('before_ordinary_report_changes_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    for name in list(changes)+files:
        if (root/name).exists():
            dest=backup/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,dest)
    for name,s in changes.items():(root/name).write_text(s,encoding='utf-8')
    for name in files:
        dest=root/name
        if dest.resolve()!=(package/name).resolve():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(package/name,dest)
    print('Installed. Backup:',backup)
    print('Restart app and refresh with Ctrl+F5.')
if __name__=='__main__':
    try:install(Path.cwd(),Path(__file__).resolve().parent)
    except (OSError,ValueError,SyntaxError) as exc:raise SystemExit('Installation stopped: '+str(exc))
