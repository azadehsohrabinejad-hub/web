"""Run in C:\\web after extracting this package into C:\\web\\assigned_checklists_patch."""
import ast
import shutil
from pathlib import Path
from datetime import datetime

IDLE_SCRIPT = '''    // Two hours since the last user action; background API polling is not activity.
    const inactivityLimitMs = 2 * 60 * 60 * 1000;
    let lastUserActivity = Date.now();
    let inactivityTimer;
    function checkInactivity() {
        const remaining = inactivityLimitMs - (Date.now() - lastUserActivity);
        if (remaining <= 0) {
            window.location.href = "{{ url_for('main.logout') }}";
            return;
        }
        clearTimeout(inactivityTimer);
        inactivityTimer = setTimeout(checkInactivity, remaining);
    }
    function resetTimer() {
        if (Date.now() - lastUserActivity >= inactivityLimitMs) {
            checkInactivity(); return;
        }
        lastUserActivity = Date.now();
        checkInactivity();
    }
    ['mousemove', 'keydown', 'scroll', 'click', 'touchstart'].forEach(event =>
        document.addEventListener(event, resetTimer, {passive:true}));
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) checkInactivity();
    });
    checkInactivity();
'''


def plan_changes(root):
    names = ['routes.py','app.py','templates/base.html','templates/form.html','templates/records.html','static/js/shift_checklist.js']
    contents = {name:(root/name).read_text(encoding='utf-8-sig').replace('\r\n','\n') for name in names}
    s = contents['routes.py']
    if 'register_assigned_checklists(main_bp)' not in s:
        s += '\n# User-assigned shift inspections\nfrom assigned_checklists import register_assigned_checklists\nregister_assigned_checklists(main_bp)\n'
    s=s.replace('from assigned_checklists import register_assigned_checklists', 'from assigned_checklists import register_assigned_checklists, response_labels as _assigned_response_labels') if 'response_labels as _assigned_response_labels' not in s else s
    s=s.replace('items=active_checklist_items(), can_manage=', 'answer_labels=_assigned_response_labels(0), items=active_checklist_items(), can_manage=') if 'answer_labels=_assigned_response_labels(0), items=' not in s else s
    s=s.replace("'status': answer['status'], 'note': note", "'status': answer['status'], 'status_label': _assigned_response_labels(0)[answer['status']], 'note': note")
    s=s.replace("{ANSWER_LABELS.get(a['status'], a['status'])}", "{a.get('status_label', ANSWER_LABELS.get(a['status'], a['status']))}")
    s=s.replace("            item['status'], item['note'] = status, note", "            item['status'], item['note'] = status, note\n            item['status_label'] = _assigned_response_labels(0)[status]") if "item['status_label'] = _assigned_response_labels(0)[status]" not in s else s
    old_counts = "f\"سالم: {counts['ok']} | مشکل‌دار: {counts['issue']} | بررسی‌نشده: {counts['unknown']}\""
    new_counts = "' | '.join(f\"{next((a.get('status_label', ANSWER_LABELS[key]) for a in answers if a['status'] == key), _assigned_response_labels(0)[key])}: {counts[key]}\" for key in ANSWER_LABELS)"
    s=s.replace(old_counts,new_counts)
    s=s.replace('answer_labels=ANSWER_LABELS,', 'answer_labels=_assigned_response_labels(0),')
    check="    submitted = data.get('answers')"
    if "data.get('answer_labels')" not in s:
        s=s.replace(check, "    if data.get('answer_labels') is not None and data['answer_labels'] != _assigned_response_labels(0):\n        return jsonify(error='پاسخ‌ها تغییر کرده‌اند؛ صفحه را تازه‌سازی کنید.'), 409\n"+check,1)
    contents['routes.py'] = s
    s = contents['app.py']
    if "app.config['PERMANENT_SESSION_LIFETIME'] = _assigned_timedelta(hours=2)" not in s:
        anchor='    login_manager.init_app(app)'
        if anchor not in s: raise ValueError('app.py: login_manager.init_app anchor missing')
        s=s.replace(anchor, anchor+"\n    from datetime import timedelta as _assigned_timedelta\n    app.config['PERMANENT_SESSION_LIFETIME'] = _assigned_timedelta(hours=2)",1)
    contents['app.py']=s
    s=contents['templates/base.html']
    if 'const inactivityLimitMs = 2 * 60 * 60 * 1000;' not in s:
        start=s.find('    let inactivityTimer;')
        if start<0: raise ValueError('base.html: existing inactivity timer not found')
        end=s.find('    </script>',start)
        if end<0: raise ValueError('base.html: timer closing script not found')
        s=s[:start]+IDLE_SCRIPT+s[end:]
    if "url_for('main.assigned_checklist_admin')" not in s:
        anchor='{% if current_user.is_admin %}'
        if anchor not in s: raise ValueError('base.html: admin navigation marker missing')
        s=s.replace(anchor,anchor+'''\n                    <li class="nav-item"><a class="nav-link text-warning" href="{{ url_for('main.assigned_checklist_admin') }}"><i class="fas fa-clipboard-check me-1"></i> چک‌لیست‌های اختصاصی</a></li>''',1)
    contents['templates/base.html']=s
    s=contents['templates/form.html']
    if "include '_assigned_checklists.html'" not in s:
        anchor="{% include '_shift_checklist.html' %}"
        if anchor not in s: raise ValueError('form.html: public checklist include missing')
        s=s.replace(anchor,anchor+"\n            {% include '_assigned_checklists.html' %}",1)
    if "filename='js/assigned_checklists.js'" not in s:
        anchor='{% block scripts %}'
        if anchor not in s: raise ValueError('form.html: scripts block missing')
        s=s.replace(anchor,anchor+'''\n<script src="{{ url_for('static', filename='js/assigned_checklists.js', v='1') }}"></script>''',1)
    if "filename='js/checklist_bulk.js'" not in s:
        s=s.replace('{% block scripts %}', '{% block scripts %}\n<script src="{{ url_for(\'static\', filename=\'js/checklist_bulk.js\', v=\'1\') }}"></script>',1)
    s=s.replace("filename='js/assigned_checklists.js', v='1'", "filename='js/assigned_checklists.js', v='2'")
    import re
    s=re.sub(r"filename='js/shift_checklist.js', v='[^']*'", "filename='js/shift_checklist.js', v='8'",s)
    contents['templates/form.html']=s
    s=contents['templates/records.html']
    if "include '_assigned_checklist_records.html'" not in s:
        start=s.find('{% block content %}')
        end=s.find('{% endblock %}',start)
        if start<0 or end<0: raise ValueError('records.html: content block missing')
        s=s[:end]+"{% include '_assigned_checklist_records.html' %}\n"+s[end:]
    s=s.replace('{{ answer_labels[answer.status] }}', '{{ answer.status_label | default(answer_labels[answer.status]) }}')
    contents['templates/records.html']=s
    s=contents['static/js/shift_checklist.js']
    s=s.replace('  let current = null;', '  let current = null;\n  let renderedAnswerLabels = null;') if 'let renderedAnswerLabels' not in s else s
    s=s.replace('    items.replaceChildren();', '    renderedAnswerLabels = current.answer_labels || {ok: "سالم", issue: "مشکل دارد", unknown: "قابل بررسی نبود"};\n    items.replaceChildren();') if 'renderedAnswerLabels = current.answer_labels' not in s else s
    s=s.replace("[['ok', 'سالم'], ['issue', 'مشکل دارد'], ['unknown', 'قابل بررسی نبود']]", "Object.entries(renderedAnswerLabels)")
    s=s.replace('shift_start: current.shift_start, answers,', 'shift_start: current.shift_start, answer_labels: renderedAnswerLabels, answers,')
    s=s.replace('JSON.stringify(current.items) !== JSON.stringify(data.items)', '(JSON.stringify(current.items) !== JSON.stringify(data.items) || JSON.stringify(current.answer_labels) !== JSON.stringify(data.answer_labels))') if 'JSON.stringify(current.answer_labels)' not in s else s
    contents['static/js/shift_checklist.js']=s
    for name in ('routes.py','app.py'): ast.parse(contents[name])
    return contents


def install(root, package):
    root = root.resolve()
    package = package.resolve()
    changes=plan_changes(root)  # Validate all anchors before editing anything.
    backup=root/'backups'/('before_assigned_checklists_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    new_names=['static/js/checklist_bulk.js','assigned_checklists.py','static/js/assigned_checklists.js','templates/assigned_checklist_admin.html','templates/_assigned_checklists.html','templates/_assigned_checklist_records.html']
    for name in new_names:
        if not (package/name).is_file():
            raise FileNotFoundError('Missing package file: '+str(package/name))
    for name in list(changes)+new_names:
        target=root/name
        if target.exists():
            dest=backup/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,dest)
    for name,content in changes.items():
        target=root/name
        if target.read_text(encoding='utf-8-sig').replace('\r\n','\n') != content:
            target.write_text(content,encoding='utf-8')
    for name in new_names:
        source=package/name
        dest=root/name
        if source.resolve() == dest.resolve():
            continue  # Package extracted directly into C:\web: already in place.
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,dest)
    print('Installed. Backup:', backup)
    print('Restart the app, then refresh with Ctrl+F5. Database files were not changed by the installer.')

if __name__=='__main__':
    package=Path(__file__).resolve().parent
    root=Path.cwd()
    try: install(root,package)
    except (ValueError,OSError) as exc:
        raise SystemExit('Installation stopped: '+str(exc))
