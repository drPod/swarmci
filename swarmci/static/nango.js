// Render Nango's live catalog and schemas; JSON Editor owns the generated form.
let nangoCatalog, nangoFunctions=[], nangoEditor, selectedFinding;
const nangoAccount=()=>{const x=JSON.parse(document.querySelector('#nango-account').value||'{}');return {integration:x.provider_config_key,connection_id:x.connection_id}};
async function loadNango(){
 try{
  nangoCatalog=await api('/api/integrations');
  $('#nango-account').innerHTML=nangoCatalog.connections.map(x=>`<option value="${esc(JSON.stringify(x))}">${esc(x.provider)} · ${esc(x.connection_id.slice(0,8))}${x.errors?.length?' · needs reconnect':''}</option>`).join('');
  $('#nango-connect-list').innerHTML=nangoCatalog.integrations.map(x=>`<button class="secondary" data-connect="${esc(x.unique_key)}">Connect ${esc(x.display_name||x.provider)}</button>`).join('');
  $('#nango-status').textContent=`${nangoCatalog.connections.length} connected accounts · ${nangoCatalog.providers.length} providers available through Nango`;
  await loadNangoFunctions();renderNangoProviders();
 }catch(e){$('#nango-status').textContent=e.message}
}
async function loadNangoFunctions(){
 const account=nangoAccount();if(!account.integration)return;
 try{const result=await api('/api/integrations/functions/'+encodeURIComponent(account.integration));nangoFunctions=result.data.filter(x=>x.type==='action'&&(/^(get-|list-|search-)/.test(x.name)||['create-issue','create-ticket','add-issue-comment','create-comment','create-attachment'].includes(x.name)));$('#nango-action').innerHTML=nangoFunctions.map(x=>`<option>${esc(x.name)}</option>`).join('');renderNangoForm()}catch(e){$('#nango-result').textContent=e.message}
}
function renderNangoForm(){
 nangoEditor?.destroy();const f=nangoFunctions.find(x=>x.name===$('#nango-action').value);if(!f)return;
 const defs=f.json_schema.definitions;const schema={...defs[f.input],definitions:defs,title:f.name};
 nangoEditor=new JSONEditor($('#nango-form'),{schema,theme:'html',disable_collapse:true,disable_edit_json:true,disable_properties:true,show_errors:'interaction'});
 nangoEditor.on('ready',()=>{const values={};if(schema.properties.owner)values.owner='drPod';if(schema.properties.repo)values.repo='swarmci-demo';nangoEditor.setValue(values)});
 $('#nango-description').textContent=f.description;
}
function renderNangoProviders(){
 if(!nangoCatalog)return;const q=$('#nango-search').value.toLowerCase();
 const rows=nangoCatalog.providers.filter(x=>(x.display_name+' '+x.name+' '+x.categories).toLowerCase().includes(q));
 $('#nango-providers').innerHTML=rows.slice(0,40).map(x=>`<div class="integration-row"><b>${esc(x.display_name||x.name)}</b><span>${esc(x.auth_mode)}</span><button class="text-button" data-templates="${esc(x.name)}">Browse actions</button></div>`).join('');
}
async function publishFinding(id){
 selectedFinding=id;await loadNango();$('#publish-repository').value='drPod/swarmci-demo';$('#publish-result').textContent='';$('#publish-dialog').showModal();
 const github=nangoCatalog?.connections.filter(x=>x.provider?.startsWith('github'))||[];
 $('#publish-account').innerHTML=github.map(x=>`<option value="${esc(JSON.stringify(x))}">${esc(x.provider_config_key)} · ${esc(x.connection_id.slice(0,8))}</option>`).join('');
}
$('#nango-refresh').onclick=loadNango;$('#nango-account').onchange=loadNangoFunctions;$('#nango-action').onchange=renderNangoForm;$('#nango-search').oninput=renderNangoProviders;
$('#nango-run').onclick=async()=>{try{const errors=nangoEditor.validate();if(errors.length)throw Error(errors.map(x=>x.message).join('; '));$('#nango-run').disabled=true;const result=await api('/api/integrations/action',{...nangoAccount(),name:$('#nango-action').value,input:nangoEditor.getValue()});$('#nango-result').textContent=JSON.stringify(result,null,2)}catch(e){$('#nango-result').textContent=e.message}finally{$('#nango-run').disabled=false}};
$('#publish-submit').onclick=async()=>{const b=$('#publish-submit');b.disabled=true;try{const c=JSON.parse($('#publish-account').value);$('#publish-result').textContent='Uploading evidence and creating the issue and PR through Nango…';const r=await api(`/api/integrations/publish/${current}/${selectedFinding}`,{integration:c.provider_config_key,connection_id:c.connection_id,repository:$('#publish-repository').value});$('#publish-result').innerHTML=`<a href="${esc(r.issue.url)}" target="_blank" rel="noopener">Open GitHub issue ↗</a> · <a href="${esc(r.pr.url)}" target="_blank" rel="noopener">Open regression PR ↗</a>`}catch(e){$('#publish-result').textContent=e.message}finally{b.disabled=false}};
$('#publish-close').onclick=()=>$('#publish-dialog').close();
document.addEventListener('click',async event=>{const el=event.target.closest('[data-connect],[data-templates],[data-enable]');if(!el)return;try{
 if(el.dataset.connect){const r=await api('/api/integrations/connect',{integration:el.dataset.connect});window.open(r.connect_link,'_blank','noopener')}
 if(el.dataset.templates){const d=await api('/api/integrations/templates/'+encodeURIComponent(el.dataset.templates));const integration=nangoCatalog.integrations.find(x=>x.provider===el.dataset.templates);$('#nango-template-list').innerHTML=`<h3>${esc(el.dataset.templates)} catalog actions</h3>`+(integration?'':'<p><a href="https://app.nango.dev" target="_blank" rel="noopener">Set up this integration in Nango</a>, then refresh and connect the account.</p>')+d.data.filter(x=>x.type==='action'&&(/^(get-|list-|search-)/.test(x.name)||['create-issue','create-ticket','create-comment','create-attachment','add-issue-comment'].includes(x.name))).map(x=>`<div class="integration-row"><b>${esc(x.name)}</b><span>${esc(x.description)}</span>${integration?`<button data-enable="${esc(x.name)}" data-integration="${esc(integration.unique_key)}">Enable template</button>`:''}</div>`).join('')}
 if(el.dataset.enable){const r=await api('/api/integrations/enable',{integration:el.dataset.integration,name:el.dataset.enable});$('#nango-result').textContent='Template deployment: '+r.status;await loadNangoFunctions()}
}catch(e){$('#nango-result').textContent=e.message}});
loadNango();
