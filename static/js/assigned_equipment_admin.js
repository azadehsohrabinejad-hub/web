(() => {
  'use strict';
  document.querySelectorAll('.equipment-editor').forEach(editor => {
    const form=editor.closest('form'), textarea=form.querySelector('textarea[name="items"]');
    const original=JSON.parse(editor.querySelector('.equipment-initial').textContent);
    let columns=[...new Set(original.flatMap(item=>Object.keys(item.equipment||{})))];
    let values=Object.fromEntries(original.map(item=>[item.label,item.equipment||{}]));
    const wrap=editor.querySelector('.equipment-table-wrap'), hidden=editor.querySelector('.equipment-json');
    const labels=()=>textarea.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
    function collect(){wrap.querySelectorAll('input[data-col]').forEach(input=>{
      const label=input.dataset.label,col=input.dataset.col;
      (values[label] ||= {})[col]=input.value;
    });}
    function render(){
      const table=document.createElement('table');table.className='table table-sm table-bordered align-middle';
      const head=document.createElement('thead'),hr=document.createElement('tr');
      const th=document.createElement('th');th.textContent='مورد بازدید';hr.append(th);
      columns.forEach(col=>{const th=document.createElement('th'), span=document.createElement('span');span.textContent=col+' ';
        const remove=document.createElement('button');remove.type='button';remove.className='btn btn-sm btn-outline-danger';remove.textContent='×';remove.title='حذف ستون '+col;
        remove.addEventListener('click',()=>{if(!confirm('ستون «'+col+'» حذف شود؟'))return;collect();columns=columns.filter(x=>x!==col);render();});th.append(span,remove);hr.append(th);});
      head.append(hr);table.append(head);const body=document.createElement('tbody');
      labels().forEach(label=>{const tr=document.createElement('tr'),td=document.createElement('th');td.textContent=label;tr.append(td);
        columns.forEach(col=>{const cell=document.createElement('td'),input=document.createElement('input');input.className='form-control form-control-sm';input.maxLength=300;input.value=(values[label]||{})[col]||'';input.dataset.label=label;input.dataset.col=col;cell.append(input);tr.append(cell);});body.append(tr);});
      table.append(body);wrap.replaceChildren(table);
    }
    editor.querySelector('.equipment-add-column').addEventListener('click',()=>{
      const input=editor.querySelector('.equipment-column-input'),col=input.value.trim();
      if(!col||col.length>60||columns.includes(col)||columns.length>=12){alert('نام ستون باید یکتا و حداکثر ۶۰ نویسه باشد (حداکثر ۱۲ ستون).');return;}
      collect();columns.push(col);input.value='';render();
    });
    editor.querySelector('.equipment-refresh').addEventListener('click',()=>{collect();render();});
    form.addEventListener('submit',()=>{collect();hidden.value=columns.length?JSON.stringify({columns,rows:labels().map(label=>Object.fromEntries(columns.map(col=>[col,(values[label]||{})[col]||''])))}):'';});
    render();
  });
})();
