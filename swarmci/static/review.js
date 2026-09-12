const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
window.addEventListener('DOMContentLoaded',async()=>{
 const root='/artifacts/penpot-verified';
 try{
  const response=await fetch(root+'/review-data.json');if(!response.ok)throw Error('Evidence is not available on this server');const data=await response.json();
  const grouped=data.attempts.filter(x=>x.variant==='nested-groups'),direct=data.attempts.filter(x=>x.variant==='direct-child');
  document.querySelector('#verification').textContent=`${grouped.filter(x=>x.status==='failed').length}/${grouped.length} failures · ${direct.filter(x=>x.status==='passed').length}/${direct.length} controls pass`;
  document.querySelector('#failure-video').innerHTML=renderArtifactCard('Recorded grouped failure',root+'/nested-groups-1/replay.mp4','video');
  document.querySelector('#control-video').innerHTML=renderArtifactCard('Recorded direct-child control',root+'/direct-child-1/replay.mp4','video');
  document.querySelector('#failure-video video').poster=root+'/nested-groups-1/after.png';
  document.querySelector('#control-video video').poster=root+'/direct-child-1/after.png';
  document.querySelector('#compare').innerHTML=renderBeforeAfterCompare(root+'/direct-child-1/after.png',root+'/nested-groups-1/after.png');
  const compare=document.querySelector('#compare');compare.querySelector('.artifact-compare-title').innerHTML=`Compare outcomes · <a href="${root}/direct-child-1/after.png" target="_blank" rel="noopener">passing control</a> · <a href="${root}/nested-groups-1/after.png" target="_blank" rel="noopener">grouped failure</a>`;compare.querySelector('input').setAttribute('aria-label','Compare passing control and grouped failure');
  document.querySelector('#attempts').innerHTML=data.attempts.map(r=>`<div class="d-flex flex-justify-between border-bottom py-3"><div><strong>${esc(r.variant)}</strong><small class="d-block color-fg-muted">Attempt ${r.repetition} · ${esc(r.observed||r.error)}</small></div><span class="Label ${r.status==='passed'?'Label--success':r.status==='failed'?'Label--danger':'Label--attention'}">${esc(r.status.toUpperCase())}</span></div>`).join('');
  document.querySelector('#filmstrip').innerHTML=grouped[0].steps.map((label,i)=>`<a href="${root}/nested-groups-1/step-${String(i+1).padStart(2,'0')}.png" target="_blank" rel="noopener"><img src="${root}/nested-groups-1/step-${String(i+1).padStart(2,'0')}.png" alt="${esc(label)}"><small class="d-block">${esc(label)}</small></a>`).join('');
  const links=await (await fetch(root+'/github.json')).json();document.querySelector('#review-pr').href=links.pr;
  const cloud=links.cloud_attempts||[];document.querySelector('#cloud-verification').textContent=cloud.length?`GitHub Actions independently verified: ${cloud.filter(x=>x.status==='failed').length} product assertion failures · ${cloud.filter(x=>x.status==='passed').length} passing controls · ${cloud.filter(x=>x.status==='error').length} setup errors.`:'Cloud verification pending';
  document.querySelector('#ci-links').innerHTML=`<a class="btn mr-2" href="${esc(links.ci||'https://github.com/drPod/penpot/actions')}" target="_blank" rel="noopener">Open GitHub checks ↗</a><a class="btn" href="${esc(links.upstream_issue_comment||'https://github.com/penpot/penpot/issues/11656')}" target="_blank" rel="noopener">Evidence on original issue ↗</a><a class="btn ml-2" href="${esc(links.demo_issue)}" target="_blank" rel="noopener">Exact issue in demo repo ↗</a>`;
 }catch(e){document.querySelector('#verification').textContent=e.message}
});
document.addEventListener('input',event=>{if(event.target.matches('[data-compare-slider]'))event.target.closest('.artifact-slider').style.setProperty('--split',event.target.value+'%')});
