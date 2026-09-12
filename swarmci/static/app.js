/* SwarmCI adapter for the reused graph and media UI. */
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const artifact=p=>{if(!p)return '';const s=String(p).replaceAll('\\','/');const i=s.indexOf('artifacts/');return i<0?'': '/'+s.slice(i).split('/').map(encodeURIComponent).join('/');};
const colors=['#75e4c2','#b6a0ff','#ffba7a','#72c9ff','#f0a6d6','#dadf8d','#8da6ff'];
function workerColor(id){let h=0;for(const c of String(id))h=(h*31+c.charCodeAt(0))>>>0;return colors[h%colors.length];}
let targets={},current=null,snapshot=null,viewData=null,source=null,events=[],workerStates={},refreshTimer=null;
let generation=0,attachedAt=0,pendingPulses=[],cursor=null,playTimer=null,selected=null,selectionKey='',wall=false;
const isRunning=()=>snapshot&&['queued','running'].includes(snapshot.status);
async function api(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data;}
function message(text){$('#message').textContent=text;$('#message').hidden=!text;}
function setPanel(name){document.querySelectorAll('[data-panel]').forEach(b=>b.classList.toggle('selected',b.dataset.panel===name));for(const p of ['evidence','agents','findings'])$('#'+p+'-panel').hidden=p!==name;}
function actionLabel(a){const label=a?.label||[a?.kind,a?.text||a?.selector||a?.url].filter(Boolean).join(' · ')||'Observe state';return /xpath=|\/html\/body|nth-child/.test(label)?`${a?.kind==='fill'?'Fill':'Interact with'} page element`:label;}
function targetConfig(){const t=targets[$('#target').value];$('#target-json').value=JSON.stringify(t,null,2);const fixture=$('#target').value==='fixture';$('#engine').value=fixture?'fixture':$('#target').value==='plane'?'gemma':'browser-use';}
async function init(){try{
  targets=await api('/api/targets');const requested=new URLSearchParams(location.search).get('target');if(targets[requested])$('#target').value=requested;targetConfig();
  const runs=await api('/api/runs');renderRuns(runs);const requestedRun=new URLSearchParams(location.search).get('run');
  if(requestedRun&&runs.some(r=>r.id===requestedRun))await attach(requestedRun);else if(runs.length)await attach(runs[0].id);
}catch(e){message(e.message);}}
async function attach(id){
  const version=++generation;current=id;source?.close();source=null;clearTimeout(refreshTimer);refreshTimer=null;pause();
  cursor=null;events=[];workerStates={};pendingPulses=[];selected=null;selectionKey='';snapshot=null;attachedAt=Date.now()/1000;atlas.reset();window.story?.reset();
  $('#inspector-content').innerHTML='<div class="inspect-empty"><span>↖</span><h2>Select a screen to look inside.</h2><p>Real screenshots, action history, and independently recorded failure evidence.</p></div>';
  const url=new URL(location.href);url.searchParams.set('run',id);history.replaceState({},'',url);
  await refresh(version);if(version!==generation||!snapshot)return;
  source=new EventSource(`/api/runs/${encodeURIComponent(id)}/events`);
  source.onmessage=e=>{
    if(version!==generation)return;const event=JSON.parse(e.data),p=event.payload;
    events.push(event);if(events.length>20000)events.shift();
    if(p.worker){const w=workerStates[p.worker]??={};if(event.kind==='job.started')w.status='Restoring checkpoint';if(event.kind==='checkpoint.restored')w.status=p.inherited?`Inherited ${p.depth}-step path`:`Exploring · depth ${p.depth}`;if(event.kind==='transition'){w.status=actionLabel(p.action);w.state=p.target;}if(event.kind==='failure.candidate')w.status='Verifying failure';if(event.kind==='job.error')w.status='Worker error';}
    if(event.kind==='transition'&&event.created>=attachedAt&&cursor===null)pendingPulses.push(p);
    if(event.kind==='run.status'&&!['queued','running'].includes(p.status)){source?.close();source=null;}
    if(!refreshTimer)refreshTimer=setTimeout(()=>{refreshTimer=null;refresh(version);},250);
  };
  source.onerror=()=>{if(version===generation&&isRunning())message('Connection interrupted. Reconnecting to the event stream…');};
}
async function refresh(version=generation){try{
  const data=await api(`/api/runs/${encodeURIComponent(current)}`);if(version!==generation)return;snapshot=data;
  $('#run-title').textContent=data.config.target.name;$('#run-target').textContent=data.config.target.url;
  $('#run-kind').textContent=(data.config.engine==='fixture'?'CONTROLLED FIXTURE':'WEBSITE EXPLORATION')+' / '+data.config.engine.toUpperCase()+' / '+data.id;
  $('#cancel').hidden=!isRunning();if(data.error)message(data.error);
  render();window.story?.load();for(const p of pendingPulses.splice(0)){atlas.pulse(p,p.worker);window.story?.transition(p);}
}catch(e){if(version===generation)message(e.message);}}
function dataAtCursor(){
  if(cursor===null)return snapshot;
  const edges=snapshot.edges.slice(0,cursor),ids=new Set(edges.flatMap(e=>[e.source,e.target]));
  if(!edges.length&&snapshot.nodes.length)ids.add(snapshot.edges[0]?.source||snapshot.nodes[0].id);
  return {...snapshot,edges,nodes:snapshot.nodes.filter(n=>ids.has(n.id)),bugs:snapshot.bugs.filter(b=>edges.some(e=>e.target===b.state)),candidates:[]};
}
function workersFor(data){
  const map=new Map();for(const e of data.edges){const id=e.payload.worker||'Unassigned';map.set(id,{id,state:e.target,edge:e,screenshot:e.payload.screenshot,status:actionLabel(e.payload.action),inherited:e.payload.inherited});}
  if(cursor===null)for(const [id,w] of Object.entries(workerStates)){const prev=map.get(id)||{id};map.set(id,{...prev,...w});}
  return [...map.values()];
}
function render(){if(!snapshot)return;viewData=window.story?story.prepareData(dataAtCursor()):dataAtCursor();const workers=workersFor(viewData),total=snapshot.edges.length;
  $('#m-states').textContent=viewData.nodes.length;$('#m-transitions').textContent=viewData.edges.length;$('#m-workers').textContent=workers.length;$('#m-handoffs').textContent=viewData.edges.filter(e=>e.payload.inherited).length;$('#m-bugs').textContent=snapshot.bugs.length;
  $('#bug-count').textContent=snapshot.bugs.length+(snapshot.candidates?.length||0);$('#agent-count').textContent=workers.length;
  $('#run-status').textContent=cursor!==null?'REPLAY':isRunning()?'LIVE':snapshot.status.replaceAll('_',' ').toUpperCase();$('#run-status').classList.toggle('is-live',cursor===null&&isRunning());
  $('#graph-note').textContent=`${new Set(viewData.nodes.map(n=>n.screen_key)).size} screen groups · depth ${Math.max(0,...viewData.nodes.map(n=>n.depth))}`;
  $('#graph-empty').hidden=!!viewData.nodes.length;$('#map-caption').textContent=cursor!==null?'Playing recorded actions':isRunning()?'Following new browser actions':'Recorded exploration · select any screen';
  $('#replay-slider').max=total;$('#replay-slider').value=cursor??total;$('#replay-progress').textContent=`${cursor??total} / ${total}`;
  $('#playback-label').textContent=cursor!==null?'Replay':isRunning()?'Live':'Recorded';$('#go-live').textContent=isRunning()?'Go live':'Latest';
  $('#replay-play').disabled=!total;$('#replay-prev').disabled=(cursor??total)<=0;$('#replay-next').disabled=(cursor??total)>=total;
  const lastShots=new Map();viewData.edges.forEach(e=>{if(e.payload.screenshot)lastShots.set(e.target,e.payload.screenshot);});
  const graphData={...viewData,nodes:viewData.nodes.map(n=>({...n,screenshot:n.screenshot||lastShots.get(n.id)}))};
  atlas.update(graphData,workers);renderWorkers(workers);renderFilmstrip();renderFindings();renderActivity();if(wall)renderWall(workers);renderSelection();window.story?.render();
}
function renderWorkers(workers){$('#workers-list').innerHTML=workers.length?workers.map(w=>`<button class="worker-row ${selected?.type==='worker'&&selected.id===w.id?'selected':''}" data-worker="${esc(w.id)}" style="--worker-color:${workerColor(w.id)}"><span class="worker-avatar">✳</span><span><b>${esc(w.id)}</b><small>${esc(w.status||'Awaiting first action')}</small></span><span class="worker-state">${cursor!==null?'REPLAY':isRunning()?'●':'↗'}</span></button>`).join(''):'<p class="empty-copy">Workers appear after their first job starts.</p>';}
function renderWall(workers){$('#browser-wall').innerHTML=workers.length?workers.map(w=>`<button class="browser-tile" data-worker="${esc(w.id)}" style="--worker-color:${workerColor(w.id)}"><div><i></i><b>${esc(w.id)}</b><span>${w.inherited?'Shared checkpoint':'Exploration'}</span></div>${w.screenshot?`<img loading="lazy" src="${artifact(w.screenshot)}" alt="Latest recorded screen for ${esc(w.id)}">`:'<div class="no-image">Awaiting screenshot</div>'}<p>${esc(w.status)}</p></button>`).join(''):'<p class="empty-copy">Browser frames appear when workers take actions.</p>';}
function renderFilmstrip(){const edges=viewData.edges.slice(-100);$('#frame-note').textContent=`${viewData.edges.length>100?'Latest 100 of ':''}${viewData.edges.length} recorded frames`;
  $('#filmstrip').innerHTML=edges.length?edges.map(e=>`<button class="frame ${selected?.id===e.id?'selected':''}" data-edge="${e.id}" title="${esc(actionLabel(e.payload.action))}">${e.payload.screenshot?`<img loading="lazy" src="${artifact(e.payload.screenshot)}" alt="${esc(actionLabel(e.payload.action))}">`:'<span class="no-image">No screenshot</span>'}<span><i style="background:${workerColor(e.payload.worker)}"></i>${esc(actionLabel(e.payload.action))}</span></button>`).join(''):'<p class="empty-copy">No recorded actions at this point.</p>';}
function renderFindings(){const bugs=snapshot.bugs.map(b=>`<button class="finding-card verified" data-bug="${esc(b.id)}"><span class="finding-badge">✓ VERIFIED IN A FRESH BROWSER</span>${b.screenshot?`<img loading="lazy" src="${artifact(b.screenshot)}" alt="Failure evidence">`:''}<h3>${esc(b.title)}</h3><p>${b.steps} actions · ${b.videos?.length?'Video replay available':'Recorded evidence'}</p><span class="finding-link">Inspect reproduction ↗</span></button>`).join('');
  const candidates=(snapshot.candidates||[]).map((c,i)=>`<button class="finding-card candidate" data-candidate="${i}"><span class="finding-badge">? SUSPECTED · NEEDS REVIEW</span><h3>${esc(c.title)}</h3><p>${esc(c.observed)}</p><span class="finding-link">Inspect evidence ↗</span></button>`).join('');
  $('#findings').innerHTML=bugs+candidates||'<p class="empty-copy">No findings yet. Confirmed bugs and suspected issues will appear here with their evidence.</p>';}
function renderActivity(){const labels={'state.merged':'Paths reached a shared state','checkpoint.restored':'Restored a checkpoint','failure.candidate':'Replaying a suspected failure','bug.verified':'Failure independently verified','job.error':'Worker encountered an error','checkpoint.drift':'Checkpoint changed; branch stopped','ux.candidate':'Suspected UX issue recorded'};
  $('#activity').innerHTML=events.filter(e=>labels[e.kind]).slice(-35).reverse().map(e=>`<div class="event ${e.kind==='bug.verified'?'danger':''}"><i></i><div>${esc(e.payload.title||e.payload.message||labels[e.kind])}<small>${esc(e.payload.worker||'Coordinator')} · ${new Date(e.created*1000).toLocaleTimeString()}</small></div></div>`).join('');}
function routeEdges(edge){if(!edge)return [];const wanted=edge.payload.path||[];return snapshot.edges.filter(e=>{const p=e.payload.path||[];return p.length<=wanted.length&&p.length>0&&JSON.stringify(p)===JSON.stringify(wanted.slice(0,p.length));});}
function stepsHtml(path){return `<ol class="steps">${(path||[]).map(a=>`<li>${esc(actionLabel(a))}</li>`).join('')}</ol>`;}
function beforeImage(edge){if(!edge)return '';const length=edge.payload.path?.length||0;const prior=snapshot.edges.find(e=>e.payload.job===edge.payload.job&&e.payload.path?.length===length-1);return artifact(prior?.payload.screenshot||snapshot.nodes.find(n=>n.id===edge.source)?.screenshot);}
function selectState(id){selected={type:'state',id};selectionKey='';setPanel('evidence');renderSelection();window.story?.render();}
function selectWorker(id){selected={type:'worker',id};selectionKey='';setPanel('evidence');renderSelection();window.story?.render();}
function selectEdge(id){selected={type:'edge',id};selectionKey='';setPanel('evidence');renderSelection();window.story?.render();}
function selectBug(id){selected={type:'bug',id};selectionKey='';setPanel('evidence');renderSelection();window.story?.render();}
function renderSelection(){if(!selected||!viewData)return;
  if(selected.type==='page'){window.story?.inspectPage(selected.id);return;}
  if(selected.type==='compare'){window.story?.inspectComparison(selected.id,selected.other);return;}
  let title='',subtitle='',content='',stateId=null,edge=null,path=[];
  if(selected.type==='bug'){
    const b=snapshot.bugs.find(b=>b.id===selected.id);if(!b)return;stateId=b.state;title=b.title;subtitle='VERIFIED FAILURE · INDEPENDENT REPLAY';path=b.path;
    edge=snapshot.edges.find(e=>e.target===b.state);
    content=`<div class="evidence-banner">✓ Reproduced in a fresh browser</div>`+(b.videos?.[0]?renderArtifactCard('Verification recording',artifact(b.videos[0]),'video'):renderArtifactCard('Verification screenshot',artifact(b.screenshot)))+
    `<div class="evidence-links"><a class="primary" href="/api/runs/${current}/bugs/${b.id}/bundle">↓ Export CI test</a><a href="${artifact(b.report)}" target="_blank" rel="noreferrer">Full report ↗</a><a href="/static/integrations.html?run=${encodeURIComponent(current)}&amp;bug=${encodeURIComponent(b.id)}">Nango export ↗</a></div>`+
    `<h3>What failed</h3>${(b.checks||[]).filter(c=>!c.passed).map(c=>`<p class="check-failed">× ${esc(c.name)}</p>`).join('')}`;
  }else if(selected.type==='candidate'){
    const c=snapshot.candidates[Number(selected.id)];if(!c)return;stateId=c.state;title=c.title;subtitle='SUSPECTED ISSUE · NEEDS REVIEW';
    content=`<div class="candidate-banner">Not independently verified</div>${renderArtifactCard('Recorded evidence',artifact(c.screenshot))}<h3>Expected</h3><p>${esc(c.expected)}</p><h3>Observed</h3><p>${esc(c.observed)}</p>`;
  }else{
    if(selected.type==='worker'){
      const w=workersFor(viewData).find(w=>w.id===selected.id);if(!w){$('#inspector-content').innerHTML='<p class="empty-copy">This worker has not acted at this playback position.</p>';return;}
      edge=w.edge;stateId=w.state;title=w.id;subtitle='FOLLOWING WORKER · '+(cursor!==null?'REPLAY':isRunning()?'LATEST ACTION':'RECORDED');
    }else if(selected.type==='edge'){edge=viewData.edges.find(e=>e.id===selected.id);stateId=edge?.target;title=actionLabel(edge?.payload.action);subtitle='RECORDED BROWSER ACTION';}
    else {stateId=selected.id;edge=[...viewData.edges].reverse().find(e=>e.target===stateId);title=viewData.nodes.find(n=>n.id===stateId)?.label;subtitle='DISCOVERED APPLICATION STATE';}
    const n=viewData.nodes.find(n=>n.id===stateId);
    if(!n){$('#inspector-content').innerHTML='<p class="empty-copy">This state has not been reached at this playback position.</p>';atlas.highlight(null);return;}
    const arrivals=viewData.edges.filter(e=>e.target===stateId),shot=artifact(edge?.payload.screenshot||n.screenshot);path=edge?.payload.path||[];
    content=(window.story?.stateHeader(n)||'')+renderArtifactCard('Browser screenshot',shot)+`<div class="state-facts"><span><b>${n.depth}</b> steps deep</span><span><b>${arrivals.length}</b> recorded arrivals</span></div>`;
    if(edge){content+=`<div class="action-detail"><span class="kicker">${esc(edge.payload.worker)}</span><h3>${esc(actionLabel(edge.payload.action))}</h3>${edge.payload.inherited?'<p class="handoff-note">↗ Continued from another worker’s checkpoint</p>':''}</div>`;
      const before=beforeImage(edge);if(before&&before!==shot)content+=renderBeforeAfterCompare(before,shot);
    }
    const failure=snapshot.bugs.find(b=>b.state===stateId);if(failure)content+=`<button class="failure-callout" data-bug="${esc(failure.id)}">▶ A verified failure was found here. Watch its replay ↗</button>`;
    if(window.story)content+=story.variantPicker(n);
    if(arrivals.length>1)content+=`<h3>Exact-key arrivals</h3><p class="muted">${new Set(arrivals.map(e=>e.payload.worker)).size} workers · ${n.arrival_paths||0} distinct action sequences. Matching observations share this card; their histories remain separate.</p><div class="arrival-list">${arrivals.slice(-12).map(e=>`<button data-edge="${e.id}"><i style="background:${workerColor(e.payload.worker)}"></i>${esc(e.payload.worker)}<span>${e.payload.path?.length||0} steps ↗</span></button>`).join('')}</div>`;
  }
  document.querySelectorAll('.frame').forEach(frame=>frame.classList.toggle('selected',frame.dataset.edge===edge?.id));
  const key=selected.type+selected.id+edge?.id+stateId+path?.length+viewData.edges.length;if(key===selectionKey)return;selectionKey=key;
  const route=routeEdges(edge);atlas.highlight(stateId,new Set(route.map(e=>e.id)));
  $('#inspector-content').innerHTML=`<div class="inspect-heading"><span class="kicker">${esc(subtitle)}</span><h2>${esc(title||'Starting checkpoint')}</h2></div>${content}${path?.length?'<h3>Sequence to this point</h3>'+stepsHtml(path):''}`;
  $('#inspector-content').querySelectorAll('[data-compare-slider]').forEach(input=>input.oninput=()=>input.parentElement.style.setProperty('--split',input.value+'%'));
  // Open captured screenshots in place while leaving videos playable inline.
  $('#inspector-content').querySelectorAll('.artifact-card a:has(img)').forEach(a=>a.onclick=e=>{e.preventDefault();$('#full-image').src=a.href;$('#image-title').textContent=title;$('#image-dialog').showModal();});
}
function pause(){clearInterval(playTimer);playTimer=null;$('#replay-play').textContent='▶';$('#replay-play').setAttribute('aria-label','Play recorded exploration');}
function seek(value){pause();cursor=Math.max(0,Math.min(snapshot.edges.length,Number(value)));selectionKey='';render();if(cursor){selectEdge(snapshot.edges[cursor-1].id);}}
function play(){if(playTimer){pause();return;}if(!snapshot?.edges.length)return;if(cursor===null||cursor>=snapshot.edges.length)cursor=0;
  $('#replay-play').textContent='Ⅱ';$('#replay-play').setAttribute('aria-label','Pause recorded exploration');
  const step=()=>{if(cursor>=snapshot.edges.length){pause();return;}cursor++;selected={type:'edge',id:snapshot.edges[cursor-1].id};selectionKey='';render();const e=snapshot.edges[cursor-1];atlas.pulse(e,e.payload.worker);window.story?.transition(e);};
  step();playTimer=setInterval(step,6500/Number($('#replay-speed').value));
}
function renderRuns(runs){$('#run-list').innerHTML=runs.length?runs.map(r=>`<button class="run-row" data-run="${r.id}"><div><b>${r.id}</b><small>${new Date(r.created*1000).toLocaleString()}</small></div><span>${esc(r.status.replaceAll('_',' '))} ↗</span></button>`).join(''):'<p class="empty-copy">No runs yet.</p>';}
// Event delegation keeps controls working as live content updates.
document.addEventListener('click',e=>{const el=e.target.closest('button');if(!el)return;
  if(el.dataset.close!==undefined){el.closest('dialog').close();return;}
  if(el.dataset.panel)setPanel(el.dataset.panel);
  if(el.dataset.worker)selectWorker(el.dataset.worker);
  if(el.dataset.edge)selectEdge(el.dataset.edge);
  if(el.dataset.bug)selectBug(el.dataset.bug);
  if(el.dataset.candidate!==undefined){selected={type:'candidate',id:el.dataset.candidate};selectionKey='';setPanel('evidence');renderSelection();window.story?.render();}
  if(el.dataset.run){$('#history-dialog').close();attach(el.dataset.run);}
});
for(const id of ['launch-open','empty-launch'])$('#'+id).onclick=()=>$('#launch-dialog').showModal();
$('#target').onchange=targetConfig;
$('#history-open').onclick=async()=>{$('#history-dialog').showModal();try{renderRuns(await api('/api/runs'));}catch(e){message(e.message);}};
$('#integrations-open').onclick=async()=>{$('#integrations-dialog').showModal();try{const h=await api('/api/health');$('#integration-list').innerHTML=Object.entries(h.integrations).map(([k,v])=>`<div class="integration-row"><b>${esc(k)}</b><span>${esc(typeof v==='object'?JSON.stringify(v):v)}</span></div>`).join('');}catch(e){$('#integration-list').textContent=e.message;}};
$('#start').onclick=async()=>{const btn=$('#start');btn.disabled=true;$('#launch-error').textContent='';try{
  const target=JSON.parse($('#target-json').value);if($('#target').value==='fixture')target.url=location.origin+'/fixture';
  const workers=Number($('#workers').value);const r=await api('/api/runs',{target,engine:$('#engine').value,execution:workers>8?'ray':'local',workers,max_jobs:workers>8?1000:40,max_depth:16,budget_seconds:Number($('#budget').value),use_gemma:$('#gemma').checked,cloud_browser:$('#cloud').checked});$('#launch-dialog').close();message('');await attach(r.id);
}catch(e){$('#launch-error').textContent=e.message;}finally{btn.disabled=false;}};
$('#import-issue').onclick=async()=>{const btn=$('#import-issue');btn.disabled=true;try{const issue=await api('/api/issues/import',{url:$('#issue-url').value});$('#issue-detail').hidden=false;$('#issue-detail').textContent=issue.title;const t=JSON.parse($('#target-json').value);t.objective=issue.body;t.issue_url=issue.url;$('#target-json').value=JSON.stringify(t,null,2);}catch(e){$('#launch-error').textContent=e.message;}finally{btn.disabled=false;}};
$('#cancel').onclick=async()=>{try{await api(`/api/runs/${current}/cancel`,{});message('Stopping exploration; keeping recorded evidence.');}catch(e){message(e.message);}};
$('#replay-play').onclick=play;$('#replay-slider').oninput=e=>seek(e.target.value);$('#replay-prev').onclick=()=>seek((cursor??snapshot.edges.length)-1);$('#replay-next').onclick=()=>seek((cursor??snapshot.edges.length)+1);
$('#replay-speed').onchange=()=>{if(playTimer){pause();play();}};
$('#go-live').onclick=()=>{pause();cursor=null;selectionKey='';render();};
$('#wall-view').onclick=()=>{wall=true;$('#browser-wall').hidden=false;$('#graph-wrap').hidden=true;$('#wall-view').classList.add('selected');$('#map-view').classList.remove('selected');if(viewData)renderWall(workersFor(viewData));};
$('#map-view').onclick=()=>{wall=false;$('#browser-wall').hidden=true;$('#graph-wrap').hidden=false;$('#map-view').classList.add('selected');$('#wall-view').classList.remove('selected');atlas.resize();};
init();
