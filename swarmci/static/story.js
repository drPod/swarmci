/* Evidence-linked narration and page/state presentation. Prose comes from DSPy + DeepSeek. */
const story = (()=>{
  let messages=new Map(),requestRun=null,poll=null,busy=false,loadedCount=-1,error=null,pinned=false,pinnedEdge=null,lastShown=0,stageEdge=null,queued=null,dwellTimer=null;
  const byId=id=>viewData?.nodes.find(n=>n.id===id);
  const pathKey=e=>JSON.stringify(e.payload.path||[]);
  function reset(){clearTimeout(poll);clearTimeout(dwellTimer);messages=new Map();requestRun=null;busy=false;loadedCount=-1;error=null;pinned=false;pinnedEdge=null;stageEdge=null;queued=null;lastShown=0;$('#story-pin').textContent='Pin';$('#story-pin').setAttribute('aria-pressed','false');}
  function prepareData(data){
    const arrivals=new Map(),screens=new Map(),pages=new Map();
    for(const e of data.edges){const a=arrivals.get(e.target)||[];a.push(e);arrivals.set(e.target,a);}
    for(const n of data.nodes){screens.set(n.screen_key,(screens.get(n.screen_key)||0)+1);pages.set(n.page_key,(pages.get(n.page_key)||0)+1);}
    return {...data,nodes:data.nodes.map(n=>{const a=arrivals.get(n.id)||[];return {...n,arrival_count:a.length,arrival_paths:new Set(a.map(pathKey)).size,arrival_workers:new Set(a.map(e=>e.payload.worker)).size,page_variants:pages.get(n.page_key),same_screen_variants:screens.get(n.screen_key)};})};
  }
  async function load(){
    if(!snapshot||busy||(loadedCount===snapshot.edges.length&&requestRun===current))return;
    const run=current;requestRun=run;busy=true;const count=snapshot.edges.length;loadedCount=count;
    async function receive(data){if(run!==current)return;messages=new Map(data.messages.map(m=>[m.edge_id,m]));error=data.error;render();
      if(data.pending){poll=setTimeout(async()=>{try{await receive(await api(`/api/runs/${run}/narration`));}catch(e){if(run===current){busy=false;error='Explanation service unavailable';render();}}},1500);}
      else {busy=false;if(snapshot?.edges.length!==count)load();}
    }
    try{await receive(await api(`/api/runs/${run}/narration`,{}));}catch(e){if(run===current){busy=false;error='Explanation service unavailable';render();}}
  }
  function selectedEdge(){
    if(pinned&&pinnedEdge)return snapshot?.edges.find(e=>e.id===pinnedEdge);
    if(selected?.type==='edge')return viewData.edges.find(e=>e.id===selected.id);
    if(selected?.type==='worker')return [...viewData.edges].reverse().find(e=>e.payload.worker===selected.id);
    if(selected?.type==='state')return [...viewData.edges].reverse().find(e=>e.target===selected.id);
    if(cursor!==null)return viewData.edges.at(-1);
    return snapshot?.edges.find(e=>e.id===stageEdge)||viewData?.edges.at(-1);
  }
  function render(forcedEdge=null){
    if(!viewData)return;
    $('#story-retry').hidden=!error||busy;
    if(!forcedEdge&&!pinned&&['page','compare'].includes(selected?.type)){
      $('#story-evidence').disabled=true;$('#story-pin').disabled=true;delete $('#story-stage').dataset.edge;$('#story-stage').classList.remove('convergence');
      $('#story-kind').textContent=selected.type==='compare'?'STATE COMPARISON':'PAGE GROUP';
      $('#story-title').textContent=selected.type==='compare'?`Comparing variants ${byId(selected.id)?.variant} and ${byId(selected.other)?.variant}`:'Several states, one page';
      $('#story-happened').textContent=selected.type==='compare'?'The inspector shows captured property differences and the two screenshots.':'Each card has its own state key. Arrivals with matching keys join an existing card.';
      $('#story-significance').textContent='';$('#story-status').textContent='Recorded graph structure · choose an action for its generated explanation.';return;
    }
    const edge=pinned?selectedEdge():forcedEdge||selectedEdge();
    $('#story-evidence').disabled=!edge;$('#story-pin').disabled=!edge;
    if(!edge){$('#story-title').textContent='One page, several possible states.';$('#story-happened').textContent='Select an arrival or play the recorded actions to follow the exploration.';$('#story-significance').textContent='';$('#story-status').textContent='Page groups organize the map; matching state keys join arrival paths.';return;}
    stageEdge=edge.id;const index=snapshot.edges.findIndex(e=>e.id===edge.id)+1,m=messages.get(edge.id);
    const status=m?.kind==='convergence'?'EXISTING STATE MATCHED':m?.kind==='unchanged'?'STATE KEY UNCHANGED':m?.kind==='variant'?'NEW STATE VARIANT':'RECORDED ACTION';
    $('#story-kind').textContent=`${edge.payload.worker||'Worker'} · ACTION ${index} · ${status}`;
    $('#story-kind').style.color=workerColor(edge.payload.worker);
    $('#story-title').textContent=m?.headline||actionLabel(edge.payload.action);
    $('#story-happened').textContent=m?.happened.text||'';
    $('#story-significance').textContent=m?.significance.text||'';
    $('#story-stage').classList.toggle('convergence',m?.kind==='convergence');
    $('#story-status').textContent=m?`${pinned?'Pinned · ':''}Explanation of recorded evidence · DeepSeek V4.1 Flash · ${m.happened.evidence_ids.length+m.significance.evidence_ids.length} fact references` : error||`Preparing explanations · ${messages.size} of ${snapshot.edges.length} ready. Recorded action shown above.`;
    $('#story-stage').dataset.edge=edge.id;
  }
  function transition(edge){
    const id=edge.id,payload=edge.payload||edge;
    const full=snapshot?.edges.find(e=>e.id===id)||{...edge,payload};
    const earlier=snapshot?.edges.slice(0,snapshot.edges.findIndex(e=>e.id===id))||[];
    if(earlier.some(e=>e.target===edge.target||e.source===edge.target))atlas.arrival(edge.target);
    if(pinned)return;
    if(cursor!==null){render(full);return;}
    // Live narration has a six-second reading window; bursts do not flash text.
    const priority=e=>{const m=messages.get(e.id);return m?.kind==='convergence'?3:e.payload.inherited?2:1;};
    if(Date.now()-lastShown>=6000){lastShown=Date.now();render(full);return;}
    if(!queued||priority(full)>=priority(queued))queued=full;
    if(!dwellTimer)dwellTimer=setTimeout(()=>{dwellTimer=null;if(queued&&!pinned&&cursor===null){const e=queued;queued=null;lastShown=Date.now();render(e);}},Math.max(100,6000-(Date.now()-lastShown)));
  }
  function stateHeader(n){return `<div class="variant-identity"><button data-page="${esc(n.page_key)}">${esc(n.title||'Page')} ↗</button><strong>Variant ${n.variant} of ${n.page_variants}</strong><span>${esc(n.variant_note)}</span><div class="identity-counts"><b>${n.arrival_count} arrivals</b><b>${n.arrival_paths} paths</b><b>${n.arrival_workers} workers</b></div></div><details class="key-detail"><summary>How this state is identified</summary><p><b>State key</b><code>${esc(n.id)}</code><b>Screen family</b><code>${esc(n.screen_key)}</code></p><p>${n.same_screen_variants>1?`${n.same_screen_variants} variants share this screen fingerprint. Their fuller state fingerprints differ.`:'This screen fingerprint currently has one state variant.'} Grouping is visual organization; state identity is unchanged.</p></details>`;}
  function factsTable(a,b){const facts=[...new Set([...Object.keys(a.state_facts||{}),...Object.keys(b.state_facts||{})])];const hashes=[...new Set([...Object.keys(a.fingerprint_parts||{}),...Object.keys(b.fingerprint_parts||{})])];
    const labels={history:'Action history',app:'Application data',storage_key:'Stored browser data',controls:'Controls & values',text:'Visible text',dialogs:'Dialogs',scroll:'Scroll position',historyLength:'Browser history length',url:'URL',title:'Title'};
    return `<table class="difference-table"><thead><tr><th>Recorded property</th><th>Variant ${a.variant}</th><th>Variant ${b.variant}</th></tr></thead><tbody>${facts.map(k=>`<tr class="${a.state_facts[k]!==b.state_facts[k]?'different':''}"><th>${esc(k)}</th><td>${esc(a.state_facts[k]??'Not captured')}</td><td>${esc(b.state_facts[k]??'Not captured')}</td></tr>`).join('')}</tbody></table><h3>Fingerprint differences</h3><div class="fingerprint-diffs">${hashes.filter(k=>a.fingerprint_parts[k]!==b.fingerprint_parts[k]).map(k=>`<span>${esc(labels[k]||k)} differs</span>`).join('')||'<span>No captured component differences available.</span>'}</div><p class="muted comparison-note">A hash difference establishes that the captured values differ. It does not reveal their contents or prove a bug.</p>`;
  }
  function variantPicker(n){const siblings=viewData.nodes.filter(o=>o.page_key===n.page_key&&o.id!==n.id);if(!siblings.length)return '';
    return `<div class="variant-picker"><h3>Other states on this page <span>${siblings.length}</span></h3>${siblings.map(o=>`<div><button data-state="${o.id}"><b>V${o.variant}</b><span>${esc(o.label)}<small>${esc(o.variant_note)}</small></span></button><button class="compare-button" data-compare="${n.id}" data-other="${o.id}" title="Compare these state variants">Compare</button></div>`).join('')}</div>`;
  }
  function inspectPage(id){const nodes=viewData.nodes.filter(n=>n.page_key===id);if(!nodes.length)return;const arrivals=viewData.edges.filter(e=>nodes.some(n=>n.id===e.target));
    $('#inspector-content').innerHTML=`<div class="inspect-heading"><span class="kicker">PAGE GROUP · ${nodes.length} DISTINCT STATES</span><h2>${esc(nodes[0].title)}</h2><p class="muted">These states belong to the same page. Their state keys are different; grouping does not merge them.</p></div><div class="state-facts"><span><b>${arrivals.length}</b>arrivals</span><span><b>${new Set(nodes.map(n=>n.screen_key)).size}</b>screen families</span></div><div class="page-variants">${nodes.map(n=>`<button data-state="${n.id}">${n.screenshot?`<img loading="lazy" src="${artifact(n.screenshot)}" alt="Variant ${n.variant}">`:''}<b>Variant ${n.variant} · ${esc(n.label)}</b><small>${esc(n.variant_note)}</small><span>${n.arrival_count} arrivals · ${n.arrival_paths} paths</span></button>`).join('')}</div>`;
  }
  function inspectComparison(aId,bId){const a=byId(aId),b=byId(bId);if(!a||!b)return;
    $('#inspector-content').innerHTML=`<div class="inspect-heading"><span class="kicker">SAME PAGE · DIFFERENT STATES</span><h2>Variant ${a.variant} ↔ Variant ${b.variant}</h2><p class="muted">${a.screen_key===b.screen_key?'Same screen fingerprint, different state keys.':'Different screen fingerprints on the same page.'}</p></div>${renderBeforeAfterCompare(artifact(a.screenshot),artifact(b.screenshot))}<div class="compare-labels"><span>Left: Variant ${a.variant}</span><span>Right: Variant ${b.variant}</span></div>${factsTable(a,b)}<div class="evidence-links"><button class="primary" data-state="${a.id}">Inspect V${a.variant}</button><button data-state="${b.id}">Inspect V${b.variant} ↗</button></div>`;
    $('#inspector-content').querySelectorAll('[data-compare-slider]').forEach(i=>i.oninput=()=>i.parentElement.style.setProperty('--split',i.value+'%'));
    atlas.highlight(a.id);
  }
  function showEvidence(){const edge=snapshot?.edges.find(e=>e.id===$('#story-stage').dataset.edge);if(!edge)return;selectEdge(edge.id);const m=messages.get(edge.id);if(!m)return;
    const holder=document.createElement('details');holder.className='narration-evidence';holder.open=true;
    holder.innerHTML=`<summary>Facts behind this explanation</summary><p class="muted">${esc(m.headline)}</p>${m.facts.map(f=>`<div><code>${esc(f.id)}</code><p>${esc(f.text)}</p></div>`).join('')}`;
    $('#inspector-content').prepend(holder);
  }
  $('#collapse-pages').onclick=()=>atlas.collapseAll();
  $('#story-pin').onclick=()=>{pinned=!pinned;pinnedEdge=pinned?stageEdge:null;$('#story-pin').textContent=pinned?'Unpin':'Pin';$('#story-pin').setAttribute('aria-pressed',String(pinned));render();};
  $('#story-evidence').onclick=showEvidence;
  $('#story-retry').onclick=()=>{loadedCount=-1;load();render();};
  document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.page)selectPage(b.dataset.page);if(b.dataset.state)selectState(b.dataset.state);if(b.dataset.compare){selected={type:'compare',id:b.dataset.compare,other:b.dataset.other};selectionKey='';setPanel('evidence');inspectComparison(selected.id,selected.other);render();}});
  return {reset,prepareData,load,render,transition,stateHeader,variantPicker,inspectPage,inspectComparison};
})();
function selectPage(id){selected={type:'page',id};selectionKey='';setPanel('evidence');story.inspectPage(id);story.render();}
window.story=story;
if(snapshot){render();story.load();}
