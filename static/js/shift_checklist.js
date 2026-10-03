(function () {
  'use strict';
  const config = JSON.parse(document.getElementById('checklistConfig').textContent);
  const badge = document.getElementById('checklistBadge');
  const card = document.getElementById('checklistCard');
  const reminder = document.getElementById('checklistReminder');
  const summary = document.getElementById('checklistSummary');
  const shiftLabel = document.getElementById('checklistShift');
  const modalLabel = document.getElementById('checklistModalShift');
  const open = document.getElementById('checklistOpen');
  const form = document.getElementById('checklistForm');
  const items = document.getElementById('checklistItems');
  const progress = document.getElementById('checklistProgress');
  const error = document.getElementById('checklistError');
  const save = document.getElementById('checklistSave');
  const modal = document.getElementById('checklistModal');
  const actions = document.getElementById('checklistActions');
  const resetForm = document.getElementById('checklistResetForm');
  document.getElementById('checklistResetOpen').addEventListener('click', () => resetForm.classList.toggle('d-none'));
  document.getElementById('checklistResetCancel').addEventListener('click', () => resetForm.classList.add('d-none'));
  // Bootstrap places the backdrop under <body>. Modals inside the sticky
  // sidebar remain in its stacking context and end up behind that backdrop.
  document.body.appendChild(modal);
  const managePortal = document.getElementById('checklistManageModal');
  if (managePortal) document.body.appendChild(managePortal);
  let current = null;
  let renderedAnswerLabels = null;
  let statusReceivedAt = 0;
  let boundaryRefreshRequested = false;

  function updateReminder() {
    if (!current) return;
    const remaining = Number(current.seconds_remaining) - (performance.now() - statusReceivedAt) / 1000;
    const urgent = !current.completed && remaining > 0 && remaining <= 600;
    card.classList.toggle('checklist-pending', !current.completed);
    card.classList.toggle('checklist-urgent', urgent);
    card.classList.toggle('checklist-complete', Boolean(current.completed));
    if (!current.completed) {
      badge.className = urgent ? 'badge bg-danger' : 'badge bg-warning text-dark';
      badge.textContent = urgent ? 'نیاز به تکمیل' : 'ثبت نشده';
    }
    reminder.classList.toggle('d-none', Boolean(current.completed));
    const message = urgent ? 'کمتر از ۱۰ دقیقه تا پایان شیفت؛ لطفاً بازدید را تکمیل کنید.' :
      remaining <= 0 ? 'شیفت تغییر کرده است؛ در حال دریافت وضعیت جدید…' : 'لطفاً بازدید این شیفت را تکمیل کنید.';
    if (reminder.textContent !== message) reminder.textContent = message;
    if (remaining <= 0 && !boundaryRefreshRequested) {
      boundaryRefreshRequested = true;
      refresh();
    }
  }

  if (config.manageUrl) {
    const manageModal = document.getElementById('checklistManageModal');
    const manageItems = document.getElementById('checklistManageItems');
    const manageError = document.getElementById('checklistManageError');
    const add = document.getElementById('checklistAddItem');
    const manageSave = document.getElementById('checklistManageSave');
    function appendEditor(item = {id: '', label: ''}) {
      const row = document.createElement('div');
      row.className = 'input-group mb-2'; row.dataset.id = item.id;
      const input = document.createElement('input');
      input.type = 'text'; input.className = 'form-control'; input.maxLength = 200;
      input.value = item.label; input.placeholder = 'عنوان مورد بازدید';
      const remove = document.createElement('button');
      remove.type = 'button'; remove.className = 'btn btn-outline-danger'; remove.textContent = 'حذف';
      remove.addEventListener('click', () => row.remove());
      row.append(input, remove); manageItems.append(row);
      if (!item.id) input.focus();
    }
    manageModal.addEventListener('show.bs.modal', () => {
      manageError.classList.add('d-none'); manageItems.replaceChildren();
      (current?.items || []).forEach(appendEditor);
    });
    add.addEventListener('click', () => {
      if (manageItems.children.length < 40) appendEditor();
    });
    manageSave.addEventListener('click', async () => {
      const rows = [...manageItems.children];
      const labels = rows.map(row => row.querySelector('input').value.trim());
      if (!labels.length || labels.some(label => !label)) {
        manageError.textContent = 'حداقل یک مورد لازم است و عنوان‌ها نمی‌توانند خالی باشند.';
        manageError.classList.remove('d-none'); return;
      }
      manageSave.disabled = true;
      try {
        const response = await fetch(config.manageUrl, {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({token: config.token, labels, items: rows.map(row => ({id: row.dataset.id}))})});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'ذخیره نشد.');
        bootstrap.Modal.getInstance(manageModal)?.hide();
        await refresh();
      } catch (e) { manageError.textContent = e.message; manageError.classList.remove('d-none'); }
      finally { manageSave.disabled = false; }
    });
  }

  function showError(message) { error.textContent = message; error.classList.remove('d-none'); }
  function updateProgress() {
    progress.textContent = `${items.querySelectorAll('input[type=radio]:checked').length} از ${current.items.length} مورد پاسخ داده شد`;
  }
  function renderItems(list) {
    renderedAnswerLabels = current.answer_labels || {ok: "سالم", issue: "مشکل دارد", unknown: "قابل بررسی نبود"};
    items.replaceChildren();
    list.forEach((item, index) => {
      const row = document.createElement('div');
      row.className = 'checklist-item border rounded p-3 mb-2';
      const title = document.createElement('div');
      title.className = 'fw-semibold mb-2';
      title.textContent = `${index + 1}. ${item.label}`;
      row.append(title);
      const choices = document.createElement('div');
      choices.className = 'd-flex flex-wrap gap-2';
      Object.entries(renderedAnswerLabels).forEach(([value, label]) => {
        const wrapper = document.createElement('label');
        wrapper.className = 'checklist-choice';
        const radio = document.createElement('input');
        radio.type = 'radio'; radio.name = `item_${item.id}`; radio.value = value;
        radio.addEventListener('change', () => { note.classList.toggle('d-none', value !== 'issue'); updateProgress(); });
        wrapper.append(radio, document.createTextNode(` ${label}`));
        choices.append(wrapper);
      });
      row.append(choices);
      const note = document.createElement('input');
      note.type = 'text'; note.className = 'form-control form-control-sm mt-2 d-none';
      note.placeholder = 'شرح مشکل (الزامی)'; note.maxLength = 500;
      note.dataset.noteFor = item.id;
      row.append(note); items.append(row);
    });
    updateProgress();
  }
  function render(data) {
    const changed = !current || current.shift_start !== data.shift_start;
    const wasCompleted = Boolean(current?.completed);
    if (changed && modal.classList.contains('show')) bootstrap.Modal.getInstance(modal)?.hide();
    const itemsChanged = current && (JSON.stringify(current.items) !== JSON.stringify(data.items) || JSON.stringify(current.answer_labels) !== JSON.stringify(data.answer_labels));
    current = data;
    statusReceivedAt = performance.now();
    boundaryRefreshRequested = false;
    shiftLabel.textContent = `شیفت ${data.shift_name} · ${data.shift_date}`;
    modalLabel.textContent = shiftLabel.textContent;
    if (data.completed) {
      const c = data.completed;
      badge.className = 'badge bg-success'; badge.textContent = 'ثبت شد';
      summary.textContent = `دمای سرور: ${c.temperature} °C · ${c.counts.ok} سالم، ${c.counts.issue} مشکل‌دار، ${c.counts.unknown} بررسی‌نشده · ${c.created_at} توسط ${c.created_by}`;
      open.classList.add('d-none');
      actions.classList.toggle('d-none', !data.can_manage);
      resetForm.action = `/shift-checklist/${encodeURIComponent(c.id)}/admin`;
      document.getElementById('checklistRevision').value = c.revision;
    } else {
      badge.className = 'badge bg-warning text-dark'; badge.textContent = 'ثبت نشده';
      summary.textContent = 'بازدید این شیفت هنوز ثبت نشده است.';
      open.classList.remove('d-none');
      actions.classList.add('d-none'); resetForm.classList.add('d-none');
      if (changed || wasCompleted || (itemsChanged && !modal.classList.contains('show'))) { form.reset(); renderItems(data.items); }
    }
    updateReminder();
  }
  async function refresh() {
    try {
      const response = await fetch(config.url, {cache: 'no-store'});
      if (!response.ok) throw new Error('دریافت وضعیت ممکن نشد.');
      render(await response.json());
    } catch (e) {
      if (!current) { badge.className = 'badge bg-secondary'; badge.textContent = 'نامشخص'; summary.textContent = e.message; }
    }
  }
  form.addEventListener('submit', async event => {
    event.preventDefault(); error.classList.add('d-none');
    if (!current || current.completed) return;
    const answers = {};
    for (const item of current.items) {
      const selected = [...form.querySelectorAll(`input[name="item_${item.id}"]`)].find(input => input.checked);
      if (!selected) { showError('وضعیت همه موارد را مشخص کنید.'); return; }
      const note = items.querySelector(`input[data-note-for="${item.id}"]`).value.trim();
      if (selected.value === 'issue' && !note) { showError('برای موارد مشکل‌دار، شرح مشکل را بنویسید.'); return; }
      answers[item.id] = {status: selected.value, note};
    }
    const temperature = document.getElementById('serverTemperature').value;
    if (temperature === '') { showError('دمای سرور را وارد کنید.'); return; }
    save.disabled = true;
    try {
      const response = await fetch(config.url, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({token: config.token, shift_start: current.shift_start, answer_labels: renderedAnswerLabels, answers,
          temperature, notes: document.getElementById('checklistNotes').value})
      });
      const result = await response.json();
      if (!response.ok) { showError(result.error || 'ثبت بازدید انجام نشد.'); if (response.status === 409) await refresh(); return; }
      bootstrap.Modal.getInstance(modal)?.hide();
      await refresh();
    } catch (e) { showError('ارتباط با سرور برقرار نشد. دوباره تلاش کنید.'); }
    finally { save.disabled = false; }
  });
  refresh();
  setInterval(refresh, 30000);
  setInterval(updateReminder, 1000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
