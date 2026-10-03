(function () {
  'use strict';
  const node = document.getElementById('assignedChecklistConfig');
  if (!node) return;
  const config = JSON.parse(node.textContent);
  const cards = document.getElementById('assignedChecklistCards');
  const modal = document.getElementById('assignedChecklistModal');
  document.body.appendChild(modal);
  const form = document.getElementById('assignedChecklistForm');
  const items = document.getElementById('assignedChecklistItems');
  const error = document.getElementById('assignedChecklistError');
  const save = document.getElementById('assignedChecklistSave');
  let status = null, selected = null, receivedAt = 0, busy = false;
  const instance = () => bootstrap.Modal.getOrCreateInstance(modal);
  const bulk = document.createElement('div'); bulk.className='d-flex flex-wrap gap-2 mb-3';
  const doneButton=document.createElement('button'), undoneButton=document.createElement('button');
  [[doneButton,'ok','btn btn-outline-success btn-sm'],[undoneButton,'unknown','btn btn-outline-secondary btn-sm']].forEach(([button,value,css])=>{
    button.type='button';button.className=css;button.addEventListener('click',()=>{
      items.querySelectorAll(`input[type="radio"][value="${value}"]`).forEach(input=>{input.checked=true;input.dispatchEvent(new Event('change'));});
      items.querySelectorAll('[data-item-note]').forEach(input=>input.value='');
    });bulk.append(button);
  });
  const hint=document.createElement('small');hint.className='text-muted align-self-center';hint.textContent='پس از انتخاب گروهی، موارد را مرور کنید و سپس ثبت نهایی را بزنید.';bulk.append(hint);
  items.before(bulk);
  function warn(message) { error.textContent = message; error.classList.remove('d-none'); }
  function open(list) {
    selected = {...list, shift_start:status.shift_start};
    doneButton.textContent='همگی: '+list.answer_labels.ok;undoneButton.textContent='همگی: '+list.answer_labels.unknown;
    form.reset(); error.classList.add('d-none'); items.replaceChildren();
    document.getElementById('assignedChecklistTitle').textContent = `${list.title} · شیفت ${status.shift_name}`;
    document.getElementById('assignedChecklistTemperatureWrap').classList.toggle('d-none', !list.temperature_required);
    document.getElementById('assignedChecklistTemperature').required = list.temperature_required;
    list.items.forEach((item, index) => {
      const row = document.createElement('div'); row.className = 'border rounded p-3 mb-2';
      const label = document.createElement('div'); label.className = 'fw-semibold mb-2'; label.textContent = `${index+1}. ${item.label}`;row.append(label);
      const choices = document.createElement('div'); choices.className = 'd-flex flex-wrap gap-3';
      const note = document.createElement('input'); note.type = 'text'; note.className = 'form-control mt-2 d-none';note.placeholder = 'شرح مشکل (الزامی)';note.maxLength=500;note.dataset.itemNote=item.id;
      [['ok',list.answer_labels.ok],['issue',list.answer_labels.issue],['unknown',list.answer_labels.unknown]].forEach(([value,text]) => {
        const wrapper=document.createElement('label');const input=document.createElement('input');input.type='radio';input.name=`assigned_${item.id}`;input.value=value;
        input.addEventListener('change',()=>note.classList.toggle('d-none',value!=='issue'));
        wrapper.append(input,document.createTextNode(' '+text));choices.append(wrapper);
      });row.append(choices,note);items.append(row);
    });instance().show();
  }
  function draw() {
    if (!status) return;
    const remaining=status.seconds_remaining-(performance.now()-receivedAt)/1000;
    cards.replaceChildren();
    status.lists.forEach(list => {
      const card=document.createElement('section');card.className='card assigned-card shadow mb-3';
      const body=document.createElement('div');body.className='card-body';
      const heading=document.createElement('h6');heading.textContent=list.title;
      const summary=document.createElement('div');summary.className='small mb-2';
      if(list.completed){card.classList.add('assigned-complete');summary.textContent=`ثبت شد · ${list.completed.time} توسط ${list.completed.created_by}`;}
      else {const urgent=remaining>0&&remaining<=600;card.classList.toggle('assigned-urgent',urgent);summary.textContent=urgent?'۱۰ دقیقهٔ پایانی شیفت؛ لطفاً تکمیل کنید.':'بازدید این شیفت هنوز ثبت نشده است.';}
      body.append(heading,summary);
      if(!list.completed){const button=document.createElement('button');button.type='button';button.className='btn btn-primary btn-sm';button.textContent='تکمیل چک‌لیست';button.addEventListener('click',()=>open(list));body.append(button);}
      card.append(body);cards.append(card);
    });
  }
  async function refresh() {
    if(busy)return;busy=true;
    try{const response=await fetch(config.statusUrl,{cache:'no-store'});if(!response.ok)throw Error('دریافت چک‌لیست ممکن نشد.');
      const data=await response.json();if(selected&&(!data.lists.some(l=>l.id===selected.id&&!l.completed)||data.shift_start!==selected.shift_start)){instance().hide();selected=null;}
      status=data;receivedAt=performance.now();draw();
    }catch(e){if(!status){cards.textContent='دریافت چک‌لیست‌های اختصاصی ممکن نشد؛ صفحه را تازه‌سازی کنید.';}}
    finally{busy=false;}
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault();error.classList.add('d-none');if(!selected)return;
    const answers={};
    for(const item of selected.items){const radio=form.querySelector(`input[name="assigned_${item.id}"]:checked`);const note=items.querySelector(`[data-item-note="${item.id}"]`).value.trim();
      if(!radio){warn('همهٔ موارد را تعیین وضعیت کنید.');return;}if(radio.value==='issue'&&!note){warn('شرح مشکل را بنویسید.');return;}answers[item.id]={status:radio.value,note};}
    save.disabled=true;
    try{const url=config.saveUrl.replace(/\/0$/,`/${selected.id}`);
      const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:config.token,shift_start:selected.shift_start,version:selected.version,answers,temperature:document.getElementById('assignedChecklistTemperature').value,notes:document.getElementById('assignedChecklistNotes').value})});
      const result=await response.json();if(!response.ok){warn(result.error||'ثبت انجام نشد یا دسترسی شما تغییر کرده است.');return;}
      instance().hide();selected=null;await refresh();
    }catch(e){warn('ارتباط با سرور برقرار نشد؛ دوباره تلاش کنید.');}finally{save.disabled=false;}
  });
  refresh();setInterval(refresh,30000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
})();
