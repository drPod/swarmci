const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeLink = value => { try { const u = new URL(value, location.origin); return ['http:','https:'].includes(u.protocol) ? escapeHTML(u.href) : '#'; } catch { return '#'; } };
async function readJSON(path) { const r = await fetch(path, {cache:'no-store'}); if (!r.ok) return null; return r.json(); }
async function refreshCorpus() {
 const button = document.querySelector('#refresh'); button.disabled = true;
 document.querySelector('#status').textContent = 'Refreshing source reports and independent worker results…';
 try {
  const batches = await Promise.all(['penpot','a','b','c'].map(n => readJSON(`/artifacts/demo-imports/${n}.json`).catch(() => null)));
  const reports = batches.flatMap(x => x ? (Array.isArray(x) ? x : [x]) : []);
  const unique = [...new Map(reports.map(x => [x.source_url,x])).values()];
  let workerCount = 0, verifiedCount = 0;
  const cards = await Promise.all(unique.map(async report => {
   const parts = new URL(report.source_url).pathname.split('/').filter(Boolean);
   const repo = parts.slice(0,2).join('/');
   const path = `/artifacts/demo-workers/${parts[0]}--${parts[1]}/result.json`;
   let resultPath = path;
   let result = await readJSON(path).catch(() => null);
   if (!result && repo === 'calcom/cal.diy') { resultPath = '/artifacts/demo-workers/calcom--cal.com/result.json'; result = await readJSON(resultPath).catch(() => null); }
   if (result) workerCount++;
   const publication = await readJSON(resultPath.replace('result.json', 'publication.json')).catch(() => null);
   const reproduced = result?.status === 'reproduced';
   const verified = report.status === 'verified-functional-variant';
   if (verified || reproduced) verifiedCount++;
   const workerStatus = result ? String(result.status || result.outcome || 'Result available') : 'No independent worker result yet';
   return `<article class="card ${verified || reproduced ? 'verified' : ''}"><div class="repo">${escapeHTML(repo)} · #${escapeHTML(parts[3])}</div><span class="Label ${verified || reproduced ? 'Label--success' : 'Label--secondary'}">${verified ? 'Verified functional variant' : reproduced ? 'Browser reproduction recorded' : 'Imported · unverified'}</span><h2>${escapeHTML(report.title)}</h2><div class="links"><a href="${safeLink(report.demo_url)}" target="_blank" rel="noopener">Open demo issue ↗</a><a href="${safeLink(report.source_url)}" target="_blank" rel="noopener">Original report ↗</a>${verified ? '<a href="/static/review.html">Watch verification ↗</a>' : ''}</div>${publication?.video_url ? `<video controls preload="metadata" poster="${safeLink(publication.grouped_after_url || publication.preview_url)}" style="width:100%;border-radius:6px" src="${safeLink(publication.video_url)}"></video><a href="${safeLink(publication.comment_url)}" target="_blank" rel="noopener">Published browser evidence ↗</a>` : publication?.preview_url ? `<a href="${safeLink(publication.comment_url)}" target="_blank" rel="noopener"><img src="${safeLink(publication.preview_url)}" alt="Actual browser verification screenshot" style="width:100%;border-radius:6px"></a>` : ''}<div class="worker">${verified ? 'Penpot 2.17.2 · 2 failing grouped attempts, 2 passing direct-child controls. Original error page and proposed fix not verified.' : `Worker: ${escapeHTML(workerStatus)}`}${result ? `<br><a href="${safeLink(resultPath)}" target="_blank" rel="noopener">Inspect worker result JSON ↗</a>` : ''}</div></article>`;
  }));
  document.querySelector('#cards').innerHTML = cards.join('');
  document.querySelector('#total').textContent = new Set(unique.map(x => new URL(x.source_url).pathname.split('/').slice(1,3).join('/'))).size;
  document.querySelector('#verified').textContent = verifiedCount;
  document.querySelector('#workers').textContent = workerCount;
  document.querySelector('#status').textContent = `Updated ${new Date().toLocaleTimeString()} · ${unique.length} exact source reports`;
 } catch (error) { document.querySelector('#status').textContent = `Unable to load reports: ${error.message}`; }
 finally { button.disabled = false; }
}
document.querySelector('#refresh').addEventListener('click', refreshCorpus);
refreshCorpus();
