"""Remove the two optional change packages and add checklist Excel reports."""
import ast
import re
import shutil
from pathlib import Path
from datetime import datetime


def install(root,package):
    root=root.resolve();package=package.resolve();changes={}
    s=(root/'routes.py').read_text(encoding='utf-8-sig')
    s=re.sub(r'^from ordinary_report_changes import register_ordinary_report_changes\s*\nregister_ordinary_report_changes\(main_bp\)\s*\n?', '',s,flags=re.M)
    if 'register_checklist_excel_reports(main_bp)' not in s:s+='\nfrom checklist_excel_reports import register_checklist_excel_reports\nregister_checklist_excel_reports(main_bp)\n'
    changes['routes.py']=s
    s=(root/'assigned_checklists.py').read_text(encoding='utf-8-sig')
    hook='''# Audited archive extension
from checklist_archive import register_checklist_archive
_original_assigned_register = register_assigned_checklists
def register_assigned_checklists(bp):
    _original_assigned_register(bp)
    register_checklist_archive(bp)'''
    s=s.replace(hook,'')
    if 'register_checklist_archive(bp)' in s:raise ValueError('Archive hook was modified; stopped before changing files.')
    changes['assigned_checklists.py']=s
    endpoints=('ordinary_report_picker','ordinary_report_history','assigned_checklist_archive')
    for name in ('templates/form.html','templates/records.html','templates/base.html','templates/_assigned_checklists.html','templates/_assigned_checklist_records.html'):
        s=(root/name).read_text(encoding='utf-8-sig')
        for endpoint in endpoints:
            # Only remove the controls introduced by the two optional installers.
            pattern=r'<a\b[^>]*href="\{\{\s*url_for\(\'main\.'+endpoint+r"'\)[^\"]*\"[^>]*>.*?</a>"
            s=re.sub(pattern,'',s,flags=re.S)
        s=re.sub(r'<p\b[^>]*>\s*</p>','',s)
        s=re.sub(r'<li\b[^>]*>\s*</li>','',s)
        changes[name]=s
    s=(root/'templates/reports.html').read_text(encoding='utf-8-sig')
    if "include '_checklist_excel_report.html'" not in s:
        anchor='{% block content %}'
        if anchor not in s:raise ValueError('reports.html content block missing')
        s=s.replace(anchor,anchor+"\n{% include '_checklist_excel_report.html' %}",1)
    changes['templates/reports.html']=s
    for name in ('routes.py','assigned_checklists.py'):ast.parse(changes[name])
    for name,s in changes.items():
        if any("url_for('main."+ep+"')" in s for ep in endpoints):raise ValueError('A rollback link could not be removed: '+name)
    files=['checklist_excel_reports.py','templates/_checklist_excel_report.html']
    for name in files:
        if not (package/name).is_file():raise FileNotFoundError(name)
    backup=root/'backups'/('before_checklist_excel_reports_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    for name in list(changes)+files:
        if (root/name).exists():
            dest=backup/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,dest)
    for name,s in changes.items():(root/name).write_text(s,encoding='utf-8')
    for name in files:
        dest=root/name
        if dest.resolve()!=(package/name).resolve():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(package/name,dest)
    print('Installed. Backup:',backup)
    print('Restart app and Ctrl+F5. Open Reports > Checklist report > Excel.')
    print('Deleted checklist history will be permanently removed from the active database on the first request.')

if __name__=='__main__':
    try:install(Path.cwd(),Path(__file__).resolve().parent)
    except (OSError,ValueError,SyntaxError) as exc:raise SystemExit('Installation stopped: '+str(exc))
