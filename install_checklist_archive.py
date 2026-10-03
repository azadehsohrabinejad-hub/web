import ast
import shutil
from pathlib import Path
from datetime import datetime

HOOK='''
# Audited archive extension
from checklist_archive import register_checklist_archive
_original_assigned_register = register_assigned_checklists
def register_assigned_checklists(bp):
    _original_assigned_register(bp)
    register_checklist_archive(bp)
'''

def install(root,package):
    root=root.resolve();package=package.resolve()
    target=root/'assigned_checklists.py'
    s=target.read_text(encoding='utf-8-sig')
    if '# Audited archive extension' not in s:s+='\n'+HOOK
    ast.parse(s)
    changes={'assigned_checklists.py':s}
    for name in ('templates/_assigned_checklists.html','templates/_assigned_checklist_records.html'):
        path=root/name;s=path.read_text(encoding='utf-8-sig')
        if 'assigned_checklist_archive' not in s:
            link='''<p class="mt-3"><a class="btn btn-sm btn-outline-primary" href="{{ url_for('main.assigned_checklist_archive') }}">بایگانی، ویرایش و چاپ چک‌لیست‌ها</a></p>\n'''
            s=link+s if name.endswith('_records.html') else s.replace('{% if assigned_lists %}','{% if assigned_lists %}\n'+link,1)
        changes[name]=s
    # Navigation is visible for authenticated users, including authors whose assignment was removed.
    name='templates/base.html';s=(root/name).read_text(encoding='utf-8-sig')
    if 'assigned_checklist_archive' not in s:
        anchor='{% if current_user.is_admin %}'
        if anchor not in s:raise ValueError('Admin navigation marker missing')
        s=s.replace(anchor,'''<li class="nav-item"><a class="nav-link" href="{{ url_for('main.assigned_checklist_archive') }}">بایگانی چک‌لیست‌ها</a></li>\n'''+anchor,1)
    changes[name]=s
    files=['checklist_archive.py','templates/assigned_checklist_archive.html','templates/assigned_checklist_edit.html']
    for name in files:
        if not (package/name).is_file():raise FileNotFoundError(name)
    backup=root/'backups'/('before_checklist_archive_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    for name in list(changes)+files:
        if (root/name).exists():
            dest=backup/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,dest)
    for name,s in changes.items():(root/name).write_text(s,encoding='utf-8')
    for name in files:
        if (package/name).resolve()!=(root/name).resolve():
            (root/name).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(package/name,root/name)
    print('Installed. Backup:',backup)
    print('Restart app, then Ctrl+F5. Open the checklist archive from navigation.')

if __name__=='__main__':
    try:install(Path.cwd(),Path(__file__).resolve().parent)
    except (OSError,ValueError,SyntaxError) as exc:raise SystemExit('Installation stopped: '+str(exc))
