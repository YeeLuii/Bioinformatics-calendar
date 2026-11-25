'use strict';
const diagnosticNames={ok:'正常',unknown:'尚未核实',unverified:'未验证',available:'当前可访问',missing_at_path:'当前路径未找到目录'};
const runNames={unknown:'尚未核实',queued:'排队中',running:'运行中',succeeded:'运行成功',failed:'运行失败',cancelled:'已取消'};
const adoptionNames={pending:'待确认',exploratory:'探索性结果',adopted:'已采用'};
function readableTime(value){if(!value)return '未登记';return String(value).replace('T',' ').replace(/\.\d+(?=[+Z])/,'');}
function projectProvenance(p){
 return `<div class="project-provenance"><div><strong>资料依据</strong><span>${esc(p.source||'尚未登记来源')}</span></div><div>资料整理：${esc(readableTime(p.updated_at))}</div><div>实际观察：${esc(readableTime(p.observed_at))} · 结果复核：${esc(readableTime(p.reviewed_at))}</div>${p.run_status&&p.run_status!=='unknown'?`<div>运行观察：${esc(readableTime(p.run_observed_at))} · ${esc(p.run_source||'运行来源待补充')}</div>`:''}<small>登记状态不代表实时监控；运行成功不等于结果已通过复核。</small></div>`;
}
function resultVersionsHTML(p){
 const versions=p.result_versions||[];if(!versions.length)return '';
 return `<details class="result-versions" open><summary>结果版本 · ${versions.length}</summary>${versions.map(v=>`<article class="result-version"><div><strong>${esc(v.name||v.id)}</strong><span>${esc(v.version)}</span></div><p>${badge(v.category||'pending')} <span class="version-adoption">${esc(({pending:'待确认',exploratory:'探索版本',adopted:'当前采用',superseded:'历史版本'})[v.status]||v.status||'待确认')}</span></p>${v.scope?`<p>${esc(v.scope)}</p>`:''}${v.todo?`<p>待完成：${esc(v.todo)}</p>`:''}${v.path?`<code>${esc(v.path)}</code><button class="text-button" data-copy="${esc(v.path)}">复制结果位置</button>`:''}<small>来源：${esc(v.source||'未登记')}<br>观察：${esc(readableTime(v.observed_at))} · 复核：${esc(readableTime(v.reviewed_at))}</small></article>`).join('')}</details>`;
}
function globalSearch(){
 drawer('<h2>搜索工作区</h2><label class="global-search-label"><span>项目、任务、会话、文件夹与地址</span><input type="search" id="workspace-search" placeholder="输入名称、目录或版本" autocomplete="off"></label><div id="workspace-search-results"></div>');
 let records=[];
 for(const p of data.projects){records.push({kind:'项目',title:p.name,detail:p.status+' · '+p.current_version,search:[p.name,p.summary,p.source,p.status,p.todo,p.current_version].join(' '),go:()=>showProject(p.id)});
  for(const a of [{label:'本地目录',path:p.local},{label:'服务器目录',path:p.remote},...(p.addresses||[])].filter(a=>a.path))records.push({kind:'地址',title:a.label||p.name,detail:a.path,search:p.name+' '+a.path+' '+a.label,go:()=>showProject(p.id)});
  for(const v of p.result_versions||[])records.push({kind:'结果版本',title:v.name||v.id,detail:p.name+' · '+v.version,search:[p.name,v.name,v.version,v.path,v.source,v.scope].join(' '),go:()=>showProject(p.id)});
 }
 for(const t of taskItems)records.push({kind:'任务',title:t.title,detail:(taskProjectLabel(taskProject(t)))+' · '+t.date,search:[t.title,t.notes,t.date,taskProjectLabel(taskProject(t))].join(' '),go:()=>taskEditor(t.id)});
 for(const c of boardReady?board.cards:[])if(c.type!=='project')records.push({kind:typeNames[c.type],title:c.title,detail:c.type==='folder'?'桌面分组':c.target,search:c.title+' '+c.target,go:()=>openCard(c.id)});
 for(const b of data.bundles)records.push({kind:'结果包',title:b.name,detail:b.current_version,search:[b.name,b.current_version,b.scope,projectBy(b.project_id)?.name].join(' '),go:()=>showBundle(b.id)});
 const input=$('#workspace-search');
 const refresh=()=>{const q=input.value.trim().toLocaleLowerCase(),matched=records.filter(r=>!q||r.search.toLocaleLowerCase().includes(q));$('#workspace-search-results').innerHTML='<p class="form-note">'+matched.length+' 条匹配'+(matched.length>80?'，显示前 80 条，请缩小关键词。':'')+'</p>'+matched.slice(0,80).map((r,i)=>`<button class="search-result" data-search-result="${i}"><span class="search-kind">${esc(r.kind)}</span><strong>${esc(r.title)}</strong><small>${esc(r.detail)}</small></button>`).join('');$$('[data-search-result]').forEach(b=>b.onclick=()=>{close();matched[Number(b.dataset.searchResult)].go();});};
 input.oninput=refresh;refresh();input.focus();
 // Include project-linked chats even when they have no desktop shortcut.
 Promise.allSettled(data.projects.map(p=>api('/api/v1/projects/'+encodeURIComponent(p.id)+'/threads').then(d=>({p,threads:d.threads})))).then(results=>{
  for(const result of results){if(result.status!=='fulfilled')continue;const {p,threads}=result.value;for(const t of threads)if(!records.some(r=>r.chat===t.id))records.push({kind:'关联会话',chat:t.id,title:t.title,detail:p.name,search:p.name+' '+t.title+' '+t.id,go:async()=>{try{await api('/api/open-thread',{project_id:p.id,thread_id:t.id});toast('已请求打开关联会话');}catch(e){toast(e.message);}}});}
  if(input.isConnected)refresh();
 });
}
async function showHistory(){
 try{const h=await requestAPI('/api/v1/history');
 drawer(`<h2>修改记录</h2><p class="form-note">查看项目、任务和桌面的变更。撤销会检查目标内容是否又被修改；发生冲突时保留现状。</p><div class="history-list">${h.entries.length?h.entries.map(e=>`<article class="history-entry"><div><strong>${esc(e.label||e.store)}</strong><time>${esc(readableTime(e.at))}</time></div><details><summary>${(e.changes||[]).length} 项变更 · 查看详情</summary>${(e.changes||[]).map(c=>`<div class="history-change"><b>${esc(c.collection||e.store)} · ${esc(c.key||'')}</b><pre>之前：${esc(JSON.stringify(c.before,null,2))}\n之后：${esc(JSON.stringify(c.after,null,2))}</pre></div>`).join('')}</details>${e.undone_by?'<span class="detail-muted">已撤销</span>':`<button class="text-button" data-history-undo="${esc(e.id)}">撤销这次修改</button>`}</article>`).join(''):'<div class="empty">还没有记录。升级后通过工作台保存的变更会出现在这里。</div>'}</div>`);
 $$('[data-history-undo]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await requestAPI('/api/v1/history/'+encodeURIComponent(b.dataset.historyUndo)+'/undo','POST',{expected_revision:h.revision});data=await api('/api/overview');await boardInit();await loadTasks();render();setView(view);await showHistory();toast('已撤销所选修改');}catch(e){b.disabled=false;toast(e.message);}});
 }catch(e){toast(e.message);}
}
async function showDiagnostics(){
 try{const d=await requestAPI('/api/v1/diagnostics');
 drawer(`<h2>工作区诊断</h2><p class="detail-muted">检查时间：${esc(readableTime(d.checked_at))}</p><div class="diagnostic-checks">${d.checks.map(c=>`<article><strong>${esc(c.label)}</strong><span class="diagnostic-status ${esc(c.status)}">${esc(diagnosticNames[c.status]||c.status)}</span><p>${esc(c.detail)}</p></article>`).join('')}</div><h3>项目地址</h3><p class="form-note">本次只检查本机目录；服务器地址不自动连接。未验证不表示文件已丢失。</p><div class="diagnostic-locations">${d.locations.map(l=>`<article><strong>${esc(projectBy(l.project_id)?.name||l.project_id)} · ${esc(l.label||l.kind)}</strong><code>${esc(l.path)}</code><span>${esc(diagnosticNames[l.status]||l.status)}</span></article>`).join('')||'<p>尚未登记地址。</p>'}</div><h3>迁移后的路径映射</h3><p class="form-note">映射只改变工作台打开或显示的地址，不搬动研究文件。预览确认后保存。</p><form id="mapping-form" class="desk-form"><div id="mapping-rows"></div><button type="button" class="text-button" id="mapping-add">＋ 添加映射</button><div class="actions"><button type="submit" class="button secondary">预览映射</button><button type="button" class="button primary" id="mapping-save" disabled>保存映射</button></div></form><div id="mapping-preview"></div>`);
 const add=(m={host:'local',from:'',to:''})=>{const row=document.createElement('fieldset');row.className='mapping-row';row.innerHTML=`<label>位置类型<select data-map="host"><option value="local" ${m.host==='local'?'selected':''}>本地</option><option value="server" ${m.host==='server'?'selected':''}>服务器</option></select></label><label>原路径前缀<input data-map="from" required value="${esc(m.from)}"></label><label>新路径前缀<input data-map="to" required value="${esc(m.to)}"></label><button type="button" class="text-button danger">移除此映射</button>`;row.querySelector('button').onclick=()=>{row.remove();invalidate();};$('#mapping-rows').append(row);row.oninput=invalidate;row.onchange=invalidate;};
 let previewed=null;const invalidate=()=>{previewed=null;$('#mapping-save').disabled=true;$('#mapping-preview').textContent='';};
 d.path_mappings.forEach(add);$('#mapping-add').onclick=()=>{add();invalidate();};
 const values=()=>$$('.mapping-row').map(row=>Object.fromEntries([...row.querySelectorAll('[data-map]')].map(e=>[e.dataset.map,e.value.trim()])));
 $('#mapping-form').onsubmit=async e=>{e.preventDefault();try{const mappings=values(),p=await requestAPI('/api/v1/path-mappings/preview','POST',{mappings});previewed=mappings;$('#mapping-save').disabled=false;$('#mapping-preview').innerHTML='<h3>预览结果</h3>'+((p.changes||[]).length?(p.changes||[]).map(c=>`<article class="mapping-change"><strong>${esc(projectBy(c.project_id)?.name||c.project_id)} · ${esc(c.label)}</strong><p>原位置</p><code>${esc(c.before)}</code><p>映射后</p><code>${esc(c.after)}</code></article>`).join(''):'<p class="form-note">当前登记的项目地址没有变化；映射规则仍可保存供后续使用。</p>');}catch(error){invalidate();toast(error.message);}};
 $('#mapping-save').onclick=async()=>{if(!previewed)return;try{await requestAPI('/api/v1/path-mappings','PUT',{mappings:previewed,expected_revision:d.config_revision});data=await api('/api/overview');render();setView(view);await showDiagnostics();toast('路径映射已保存');}catch(e){toast(e.message);}};
 }catch(e){toast(e.message);}
}
async function exportResearchReport(){
 try{const r=await requestAPI('/api/v1/export?'+new URLSearchParams({format:'markdown',...(project?{project_id:project}:{})}));downloadText(r.content,r.filename,'text/markdown;charset=utf-8');toast('已导出已登记的工作简报');}catch(e){toast(e.message);}
}

async function reloadWorkspace(){data=await api('/api/overview');if(project&&!projectBy(project))project='';await boardInit();await loadTasks();render();setView(view);}
async function archiveProject(id){
 try{const current=await requestAPI('/api/v1/projects/'+encodeURIComponent(id));await requestAPI('/api/v1/projects/'+encodeURIComponent(id)+'/archive','POST',{expected_revision:current.revision});close();await reloadWorkspace();toast('项目已归档，文件、任务和卡片布局保留。可从“已归档项目”恢复。');}catch(e){toast(e.message);}
}
async function showArchivedProjects(){
 try{const saved=await requestAPI('/api/v1/projects?include_archived=true');archivedProjects=saved.projects.filter(p=>p.archived);
 drawer(`<h2>已归档项目</h2><p class="form-note">项目资料、任务与卡片布局均保留。恢复后会重新显示在项目列表和原桌面位置。</p>${archivedProjects.length?archivedProjects.map(p=>`<article class="review-card"><div><h3>${esc(p.name)}</h3><p>${esc(p.status||'')}</p><small>${taskItems.filter(t=>taskProject(t)===p.id).length} 项任务 · ${esc(p.current_version||'尚未登记版本')}</small></div><button class="button secondary" data-project-restore="${esc(p.id)}">恢复项目</button></article>`).join(''):'<div class="empty">没有已归档项目。</div>'}`);
 $$('[data-project-restore]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await requestAPI('/api/v1/projects/'+encodeURIComponent(b.dataset.projectRestore)+'/restore','POST',{expected_revision:saved.revision});await reloadWorkspace();await showArchivedProjects();toast('项目已恢复，原卡片安排保留');}catch(e){b.disabled=false;toast(e.message);}});
 }catch(e){toast(e.message);}
}
$('#archived-open').onclick=showArchivedProjects;
$('#global-search-open').onclick=globalSearch;$('#history-open').onclick=showHistory;$('#diagnostics-open').onclick=showDiagnostics;$('#report-export').onclick=exportResearchReport;
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(data)globalSearch();}});
// Only refresh shared state while idle; a changed revision must never be attached to stale cards.
setInterval(async()=>{if(!data||document.hidden||!$('#drawer').hidden||boardBusy||taskBusy||ganttDrag)return;try{const fresh=await api('/api/board-state');if(!$('#drawer').hidden||boardBusy||taskBusy||ganttDrag)return;if(boardReady&&fresh.revision!==board.revision){board=fresh;renderBoard();await loadTasks();}}catch{}},15000);
