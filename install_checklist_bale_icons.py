"""Add status icons to public and assigned checklist Bale messages."""
import ast
import shutil
from datetime import datetime
from pathlib import Path

OLD = '''f"• {a['label']}:'''
NEW = '''f"{ {'ok': '✅', 'issue': '❌', 'unknown': '🟡'}.get(a['status'], '🟡') } {a['label']}:'''


def install(root):
    changes = {}
    for name in ('routes.py', 'assigned_checklists.py'):
        path = root / name
        source = path.read_text(encoding='utf-8-sig')
        if NEW in source:
            continue
        if source.count(OLD) != 1:
            raise ValueError(name + ': checklist message format not recognized; no files changed.')
        updated = source.replace(OLD, NEW, 1)
        ast.parse(updated)
        changes[name] = updated
    if not changes:
        print('Checklist Bale icons are already installed.')
        return
    backup = root / 'backups' / ('before_checklist_bale_icons_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    backup.mkdir(parents=True)
    for name in changes:
        shutil.copy2(root / name, backup / name)
    for name, source in changes.items():
        (root / name).write_text(source, encoding='utf-8')
    print('Installed: OK ✅ | Problem ❌ | Not checked 🟡')
    print('Backup:', backup)
    print('Restart the app. Icons will appear in future checklist Bale reports.')


if __name__ == '__main__':
    try:
        install(Path.cwd())
    except (OSError, ValueError, SyntaxError) as exc:
        raise SystemExit('Installation stopped: ' + str(exc))
