let pid=0,store=null;const $=id=>document.getElementById(id);const money=x=>x==null?'—':Number(x).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url,opts){const r=await fetch(url,{...opts,headers:{...opts?.headers,'X-Sonifarma-Request':'1'}});if(r.status===401){location.replace('/login');throw Error('Sessão encerrada')}if(!r.ok){let message='Não foi possível concluir a operação.';try{const body=await r.json();message=typeof body.detail==='string'?body.detail:message}catch{}throw Error(message)}return r.json()}
async function loadProcesses(){const a=await api('/api/processes');$('process').innerHTML=a.map(x=>`<option value="${x.id}">${esc(x.name)}</option>`).join('');pid=Number($('process').value);await load()}
function showError(error){$('notice').classList.add('error');$('notice').textContent='Erro: '+error.message;}
async function load(){if(!pid)return;const currentPid=pid;const result=await api('/api/data/'+currentPid);if(currentPid!==pid)return;store=result;const s=store.summary;for(const [id,key] of [['needsCount','needs'],['quotesCount','quotes'],['supplierCount','suppliers'],['selectedCount','selected']])$(id).textContent=s[key];$('pendingCount').textContent=s.pending;$('championCount').textContent=s.champions;$('selectedTotal').textContent=money(s.selected_total);$('savingTotal').textContent=money(s.indicative_saving)+' ('+s.comparable_count+' itens)';$('pdf').href='/api/export/'+pid;$('draftXlsx').href='/api/drafts/'+pid+'/xlsx';$('draftPdf').href='/api/drafts/'+pid+'/pdf';render();await Promise.all([loadDrafts(),loadAudit()])}
function render(){
 if(!store)return;
 const query=$('search').value.toUpperCase(),f=$('filter').value;
 let arr=store.needs.filter(n=>(n.name+' '+n.code+' '+n.candidates.map(x=>x.supplier).join(' ')).toUpperCase().includes(query));
 arr=arr.filter(n=>f==='all'||f==='matched'&&n.candidates.length||f==='missing'&&!n.candidates.length||f==='selected'&&n.choice);
 $('body').innerHTML=arr.map(n=>{
  const chosen=n.choice&&store.quotes.find(x=>x.id===n.choice.quote_id);
  const opts=[...n.candidates];if(chosen&&!opts.some(x=>x.id===chosen.id))opts.unshift(chosen);
  const status=chosen?(n.choice.reason?.includes('(conferir)')?'Pré-selecionado · conferir':(n.choice.reason?.startsWith('Campeão automático')?'Campeão selecionado':'Seleção do comprador')):n.champion?'Campeão disponível':'Conferir vínculo';
  return `<article class="purchase-item">
   <div class="item-main"><div class="item-title"><strong>${esc(n.name)}</strong><span class="code">${esc(n.code)}</span></div>
    <div class="item-fig"><small>Necessidade</small><b>${esc(n.qty??'?')} ${esc(n.unit)}</b></div>
    <div class="item-fig"><small>Último custo</small><b>${money(n.last_cost)}</b></div>
    <div class="item-fig supplier"><small>Fornecedor escolhido</small><b>${chosen?esc(chosen.supplier):'—'}</b></div>
    <div class="item-fig"><small>Preço base</small><b>${chosen?money(chosen.unit_cost):'—'}</b></div>
    <div class="item-status"><span class="pill ${chosen?'ok':''}">${status}</span></div>
    <button class="outline" onclick="toggleDetail(${n.id},this)" aria-expanded="false" aria-controls="detail-${n.id}" aria-label="Ver detalhes do insumo">Detalhes ▾</button>
   </div>
   <div class="item-detail" id="detail-${n.id}" hidden>
    <div class="detail-col"><small>Campeão validado</small><b>${n.champion?esc(n.champion.supplier)+' — '+money(n.champion.unit_cost):'Ainda não validado'}</b>
     <small>Diferença vs. custo anterior</small><b>${n.saving==null?'Não comparável':money(n.saving)+' ('+(n.delta_pct==null?'—':n.delta_pct+'%')+')'}</b>
     <small>${esc(n.comparison_status)}</small></div>
    <div class="detail-col grow"><label for="sel-${n.id}">Selecionar fornecedor</label><select id="sel-${n.id}" onchange="selectQuote(${n.id},this.value)"><option value="">Sem seleção</option>${opts.map(x=>`<option value="${x.id}" ${chosen&&chosen.id===x.id?'selected':''}>${esc(x.supplier)} — ${money(x.unit_cost)} / ${esc(x.base_unit)} ${x.verified?'✓ validado':'(sugestão)'}</option>`).join('')}</select>
    <button class="outline" onclick="manualMatch(${n.id})">Buscar e validar cotação</button></div>
    <div class="detail-col grow"><small>Cotações sugeridas</small>${n.candidates.length?n.candidates.slice(0,5).map(x=>`<div class="quote-line">${esc(x.supplier)} · ${money(x.unit_cost)} / ${esc(x.base_unit)} ${x.verified?'✓':'· conferir'}</div>`).join(''):'Nenhuma correspondência automática'}</div>
   </div></article>`
 }).join('')||'<p>Nenhum insumo encontrado.</p>';
}
function toggleDetail(id,button){const el=$('detail-'+id);el.hidden=!el.hidden;button.setAttribute('aria-expanded',String(!el.hidden));button.textContent=el.hidden?'Detalhes ▾':'Recolher ▴';}
async function autoChampions(){
 if(!confirm('Selecionar automaticamente o menor preço SOMENTE entre cotações com vínculo aprovado e unidade base compatível? Escolhas já feitas não serão alteradas.'))return;
 try{const r=await api('/api/auto-champions/'+pid,{method:'POST'});await load();alert(r.selected+' campeões selecionados. '+r.pending+' itens sem campeão validado.\n'+r.warning)}catch(e){alert('Erro: '+e.message)}
}
async function selectQuote(n,id){try{if(!id){const f=new FormData();f.append('need_id',n);await api('/api/unchoose',{method:'POST',body:f});await load();return;}const f=new FormData();f.append('need_id',n);f.append('quote_id',id);f.append('reason',prompt('Motivo da escolha (opcional):','Seleção do comprador')||'Seleção do comprador');await api('/api/choose',{method:'POST',body:f});await load()}catch(error){showError(error);render()}}
async function manualMatch(n){try{const name=prompt('Digite parte do nome do produto cotado:');if(!name)return;const candidates=store.quotes.filter(q=>q.product.toUpperCase().includes(name.toUpperCase())).slice(0,20);if(!candidates.length){alert('Nenhuma cotação encontrada');return}const list=candidates.map((x,i)=>`${i+1}. ${x.supplier} | ${x.product} | ${money(x.total)}`).join('\n');const index=Number(prompt('Escolha o número para vincular a cotação ao insumo:\n'+list));if(!Number.isInteger(index)||index<1||index>candidates.length)return;const f=new FormData();f.append('need_id',n);f.append('quote_id',candidates[index-1].id);await api('/api/match',{method:'POST',body:f});await load()}catch(error){showError(error)}}
async function newProcess(){try{const name=prompt('Nome do processo de compras:');if(!name)return;const f=new FormData();f.append('name',name);const r=await api('/api/processes',{method:'POST',body:f});await loadProcesses();$('process').value=r.id;pid=r.id;await load()}catch(error){showError(error)}}
$('process').onchange=async e=>{pid=Number(e.target.value);await load().catch(showError)};$('search').oninput=render;$('filter').onchange=render;
for(const [id,path] of [['needForm','needs'],['quoteForm','quotes']])$(id).onsubmit=async e=>{e.preventDefault();const form=new FormData(e.target);$('notice').classList.remove('error');$('notice').textContent='Importando...';const button=e.target.querySelector('button');button.disabled=true;try{const r=await api('/api/'+path+'/'+pid,{method:'POST',body:form});$('notice').textContent=`${r.imported} registros importados. ${r.warning||''}`;await load()}catch(err){showError(err)}finally{button.disabled=false}};
loadProcesses().catch(showError);

async function loadDrafts(){const currentPid=pid;const d=await api('/api/drafts/'+currentPid);if(currentPid!==pid)return;$('draftsSummary').innerHTML=d.suppliers.length?'<div class="scroll"><table><thead><tr><th>Fornecedor</th><th>Itens selecionados</th><th>Itens pendentes</th><th>Total estimado comparável</th></tr></thead><tbody>'+d.suppliers.map(x=>`<tr><td><b>${esc(x.supplier)}</b></td><td>${x.items.length}</td><td>${x.pending}</td><td>${money(x.total_estimated)}</td></tr>`).join('')+'</tbody></table></div>':'Nenhum fornecedor selecionado. Escolha fornecedores no comparativo abaixo.'}

async function loadAudit(){const currentPid=pid;if(!currentPid)return;const rows=await api('/api/audit/'+currentPid);if(currentPid!==pid)return;const labels={VALIDAR_VINCULO:'Vínculo aprovado',SELECIONAR:'Fornecedor selecionado',REMOVER:'Seleção removida',CAMPEAO_AUTOMATICO:'Seleção automática'};$('auditBody').innerHTML=rows.length?'<table><thead><tr><th>Data</th><th>Ação</th><th>Insumo</th><th>Motivo</th></tr></thead><tbody>'+rows.map(row=>`<tr><td>${esc(new Date(row.created).toLocaleString('pt-BR'))}</td><td>${esc(labels[row.action]||row.action)}</td><td>${esc(store?.needs.find(n=>n.id===row.need_id)?.name||row.need_id)}</td><td>${esc(row.reason||'—')}</td></tr>`).join('')+'</tbody></table>':'<p class="empty">Nenhuma decisão registrada neste processo.</p>';}
function updateNavigation(){const hash=location.hash||'#dashboard';document.querySelectorAll('nav a').forEach(link=>{const active=link.getAttribute('href')===hash&&!link.textContent.includes('Campeões');link.classList.toggle('active',active);if(active)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current')})}window.addEventListener('hashchange',updateNavigation);updateNavigation();

async function logout(){try{await api("/api/auth/logout",{method:"POST"});location.replace("/login")}catch(error){showError(error)}}
