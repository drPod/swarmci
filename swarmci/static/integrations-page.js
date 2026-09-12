const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let current=null;
async function api(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail));return d}
async function findings(){try{const runs=await api('/api/runs'),all=await Promise.all(runs.slice(0,20).map(r=>api('/api/runs/'+r.id)));$('#finding-select').innerHTML=all.flatMap(s=>s.bugs.map(b=>`<option value="${esc(JSON.stringify({run:s.id,bug:b.id}))}">${esc(s.config.target.name+' · '+b.title)}</option>`)).join('');const q=new URLSearchParams(location.search);if(q.has('run')){$('#finding-select').value=JSON.stringify({run:q.get('run'),bug:q.get('bug')})}}catch(e){$('#nango-result').textContent=e.message}}
$('#publish-open').onclick=()=>{const value=$('#finding-select').value;if(!value)return;const f=JSON.parse(value);current=f.run;publishFinding(f.bug)};
findings();
