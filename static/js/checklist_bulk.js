(function () {
  'use strict';
  const items=document.getElementById('checklistItems');
  if(!items)return;
  const toolbar=document.createElement('div');toolbar.className='d-flex flex-wrap gap-2 mb-3';
  [['ok','همگی انجام شده','btn-outline-success'],['unknown','همگی انجام نشده','btn-outline-secondary']].forEach(([value,text,style])=>{
    const button=document.createElement('button');button.type='button';button.className='btn btn-sm '+style;button.textContent=text;
    button.addEventListener('click',()=>{
      items.querySelectorAll(`input[type="radio"][value="${value}"]`).forEach(input=>{input.checked=true;input.dispatchEvent(new Event('change'));});
      items.querySelectorAll('[data-note-for]').forEach(input=>input.value='');
    });toolbar.append(button);
  });
  const hint=document.createElement('small');hint.className='text-muted align-self-center';hint.textContent='انتخاب گروهی قابل اصلاح است؛ ثبت نهایی را پس از مرور بزنید.';toolbar.append(hint);items.before(toolbar);
})();
