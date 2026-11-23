'use strict';
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=n=>Number(n||0).toLocaleString('zh-CN');
let data,project='',view='board',page=1,pages=1,bundleFilter='',requestNo=0,lastFocus=null;
const folderIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 7V5h7l2 3h9v11H3z"/><path d="M3 8h18"/></svg>';
const projectBy=id=>data.projects.find(p=>p.id===id);
const badge=c=>`<span class="badge ${esc(c)}">${esc(data.categories[c]||c)}</span>`;
async function api(url,body){const r=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json','X-Desk-Token':data.token},body:JSON.stringify(body)}:{});const d=await r.json();if(!r.ok)throw Error(d.error||'请求失败');return d;}
let toastTimer;function toast(s){$('#toast').textContent=s;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,4000);}
async function copy(s){try{await navigator.clipboard.writeText(s);toast('已复制');}catch{const t=document.createElement('textarea');t.value=s;document.body.append(t);t.select();const ok=document.execCommand('copy');t.remove();toast(ok?'已复制':'浏览器不允许自动复制，请选中路径复制');}}
function shellQuote(s){return "'"+s.replace(/'/g,"'\\''")+"'";}
function ssh(path,host){if(!host)throw Error('请先在项目中填写 SSH 主机别名');return 'ssh -t '+shellQuote(host)+' '+shellQuote('cd -- '+shellQuote(path)+' && exec bash');}
function basename(p){return p.replace(/\\/g,'/').split('/').pop();}
function shownPath(p){return p.replace(/\r/g,'\\r').replace(/\n/g,'\\n').replace(/\t/g,'\\t');}
function setView(v){view=v;document.body.classList.toggle('board-mode',v==='board');if(v==='board'){$('#crumb').textContent='我的桌面';$('#heading').textContent='AI4S工作台';$('#intro').textContent='';}else{const p=projectBy(project);$('#heading').textContent=p?p.name:'项目资料';$('#intro').textContent=p?p.status:'';}$$('.tab').forEach(t=>{t.classList.toggle('active',t.dataset.view===v);t.setAttribute('aria-selected',t.dataset.view===v);});for(const k of ['board','desk','files','tasks'])$('#'+k+'-view').hidden=k!==v;if(v==='files')loadFiles();history.replaceState(null,'','#'+new URLSearchParams({project,view}));}
function selectProject(id){if(view==='board')view='desk';project=id;bundleFilter='';page=1;render();setView(view);}
function render(){
 $('#refresh').hidden=!data.capabilities.refresh;
 $('[data-view=files]').disabled=!data.capabilities.file_index;
 $('.export').hidden=!data.capabilities.export_summary;
 $('#metrics').hidden=!data.capabilities.file_index;
 $('#scope-notice').hidden=!data.capabilities.file_index;
 document.querySelectorAll('a[href="/export/files.tsv"]').forEach(a=>a.hidden=!data.capabilities.export_files);
 $('#new-project').onclick=()=>editProject();
 const p=projectBy(project);$('#crumb').textContent=p?p.name:'全部项目';$('#heading').textContent=p?p.name:'项目资料';$('#intro').textContent=p?p.status+' · '+p.scope:'';
 $('#updated').textContent=data.updated_at.slice(0,19).replace('T',' ');$('#connection').textContent='';
 $('#all-projects').classList.toggle('active',!project);$('#project-count').textContent=data.projects.length;
 $('#project-nav').innerHTML=data.projects.map(p=>`<button class="nav ${p.id===project?'active':''}" data-project="${esc(p.id)}">${esc(p.name)}<span>${num(p.counts.paper)}</span></button>`).join('');
 $$('#project-nav button').forEach(b=>b.onclick=()=>selectProject(b.dataset.project));
 const counts=p?p.counts:data.counts;const notes={paper:'在列明范围内使用',exploratory:'保留假说与统计限定',intermediate:'保留复现和恢复用途',logs:'运行记录与质检依据'};
 $('#metrics').innerHTML=['paper','exploratory','intermediate','logs'].map(c=>`<button class="metric ${c}" data-category="${c}"><div class="metric-name">${esc(data.categories[c])}</div><div class="metric-value">${num(counts[c])}</div><div class="metric-note">${notes[c]} · 点击筛选</div></button>`).join('');
 $$('.metric').forEach(b=>b.onclick=()=>{$('#category').value=b.dataset.category;bundleFilter='';page=1;setView('files');});
 const ps=p?[p]:data.projects;$('#cards-title').textContent=p?'项目入口与进度':'项目入口';$('#desk-count').textContent=p?p.current_version:`${ps.length} 个项目 · 点击进入`;
 $('#project-cards').innerHTML=ps.map(p=>`<article class="project-card"><div class="card-top"><span class="folder-icon">${folderIcon}</span><span class="tiny-label">${p.remote?'本地 / 服务器':'本地'}</span></div><h3>${esc(p.name)}</h3><div class="status">${esc(p.status)}</div><div class="version">${esc(p.current_version)}</div><div class="card-bottom"><span class="small-count">文章结果 ${num(p.counts.paper)} · 待判 ${num(p.counts.pending)}</span><button class="text-button" data-project-open="${esc(p.id)}">查看项目</button></div></article>`).join('');
 $$('[data-project-open]').forEach(b=>b.onclick=()=>showProject(b.dataset.projectOpen));
 const bs=data.bundles.filter(b=>!project||b.project_id===project);
 $('#bundle-list').innerHTML=bs.length?bs.map(b=>`<div class="bundle-row" role="button" tabindex="0" data-bundle="${esc(b.id)}"><div><h3>${esc(b.name)}</h3><p>${esc(projectBy(b.project_id).name)} · ${num(b.file_count)} 个登记条目</p></div><span class="version">${esc(b.current_version)}</span>${badge(b.review_status==='reviewed'?b.category:'pending')}</div>`).join(''):'<div class="empty">尚未登记结果包，可先完善项目概述、结果目录和待完成事项。</div>';
 $$('[data-bundle]').forEach(b=>{b.onclick=()=>showBundle(b.dataset.bundle);b.onkeydown=e=>{if(e.key==='Enter')showBundle(b.dataset.bundle);};});
 $('#task-list').innerHTML=ps.map(p=>`<article class="task-card"><div><h3>${esc(p.name)}</h3><small>${esc(p.current_version)}</small></div><div><p>${esc(p.todo)}</p><small>${esc(p.scope)}</small></div></article>`).join('');
 $('#totals').textContent=`本地文件 ${num(data.local_files)} · 服务器条目 ${num(data.server_entries)} · 输入/代码 ${num(counts.support)} · 待判定 ${num(counts.pending)}`;
 if(data.stale_bundles.length)$('#scope-notice').innerHTML='<b>来源已变化</b><span>'+data.stale_bundles.length+' 个结果包需要复核；相关文件不再自动归入可用于文章。</span>';
}
async function loadFiles(){
 const no=++requestNo;$('#file-count').textContent='正在查询…';
 const params=new URLSearchParams({page,project_id:project,category:$('#category').value,host:$('#host').value,object_type:$('#object-type').value,q:$('#search').value,bundle_id:bundleFilter});
 try{const d=await api('/api/files?'+params);if(no!==requestNo)return;pages=d.pages;
 $('#file-count').textContent=`匹配 ${num(d.total)} 个条目${bundleFilter?' · 已限定结果包':''}`;
 $('#page-label').textContent=`${page} / ${num(pages)}`;$('#prev').disabled=page<=1;$('#next').disabled=page>=pages;
 $('#file-rows').innerHTML=d.rows.length?d.rows.map(r=>`<tr><td><span class="filename">${r.object_type==='directory'?'▱ ':''}${esc(basename(shownPath(r.path)))}</span><span class="filepath" title="${esc(shownPath(r.path))}">${esc(shownPath(r.path))}</span></td><td>${badge(r.category)}</td><td>${r.host==='local'?'本地':'服务器'}</td><td>${esc(r.current_version)}</td><td><button class="text-button" data-item="${r.id}">详情</button></td></tr>`).join(''):'<tr><td colspan="5" class="empty">没有匹配文件。试试更短的关键词，或重置筛选条件。</td></tr>';
 $$('[data-item]').forEach(b=>b.onclick=()=>showFile(b.dataset.item));
 }catch(e){$('#file-count').textContent='查询失败：'+e.message;toast(e.message);}
}
function drawer(html){lastFocus=document.activeElement;$('#details').innerHTML=html;$('#drawer').hidden=false;$('#scrim').hidden=false;document.body.style.overflow='hidden';$('#close-drawer').focus();wirePaths();}
function close(){if(typeof activeFolder!=='undefined')activeFolder='';if($('#drawer').hidden)return;$('#drawer').hidden=true;$('#scrim').hidden=true;document.body.style.overflow='';lastFocus?.focus();}
function pathHtml(loc,label=''){
 const alias=loc.ssh_alias||projectBy(loc.project_id)?.ssh_alias||data.workspace?.ssh_alias||'';
 const exists=['available','available_at_scan','observed_metadata'].includes(loc.availability);
 return `<div class="pathblock"><h3>${esc(label|| (loc.host==='local'?'本地位置':'服务器位置'))}</h3><code>${esc(shownPath(loc.path))}</code><div class="availability">${esc(exists?'路径已核验':loc.availability==='not_observed'?'本轮未观察到此精确路径':loc.availability==='unverified'?'已登记地址':loc.availability||'可达性未核验')}</div><div class="actions"><button class="button secondary" data-copy="${esc(loc.path)}">复制路径</button>${loc.host==='local'?`<button class="button primary" data-open="${esc(loc.id)}" ${exists?'':'disabled'}>打开所在目录</button>`:`<button class="button secondary" data-ssh="${esc(loc.path)}" data-ssh-host="${esc(alias)}" ${alias?'':'disabled title="未配置 SSH 主机别名"'}>复制 SSH 命令</button>`}</div></div>`;
}
function wirePaths(){$$('[data-copy]').forEach(b=>b.onclick=()=>copy(b.dataset.copy));$$('[data-ssh]').forEach(b=>b.onclick=()=>{try{copy(ssh(b.dataset.ssh,b.dataset.sshHost||data.workspace?.ssh_alias));}catch(e){toast(e.message);}});$$('[data-open]').forEach(b=>b.onclick=async()=>{try{await api('/api/open-folder',{id:b.dataset.open});toast('已在文件资源管理器中打开');}catch(e){toast(e.message);}});}
$('#close-drawer').onclick=close;$('#scrim').onclick=close;document.addEventListener('keydown',e=>{if(e.key==='Escape')close();if(e.key==='Tab'&&!$('#drawer').hidden){const fs=[...$('#drawer').querySelectorAll('button:not(:disabled),a,input,select')];const first=fs[0],last=fs[fs.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}});
$('#all-projects').onclick=()=>selectProject('');$$('.tab').forEach(t=>t.onclick=()=>setView(t.dataset.view));
for(const id of ['category','host','object-type'])$('#'+id).onchange=()=>{page=1;loadFiles();};
let debounce;$('#search').oninput=()=>{clearTimeout(debounce);debounce=setTimeout(()=>{page=1;loadFiles();},250);};
$('#clear-filters').onclick=()=>{for(const id of ['category','host','object-type','search'])$('#'+id).value='';bundleFilter='';page=1;loadFiles();};
$('#prev').onclick=()=>{page--;loadFiles();};$('#next').onclick=()=>{page++;loadFiles();};
let refreshTimer;$('#refresh').onclick=async()=>{try{await api('/api/refresh',{});$('#refresh').disabled=true;$('#refresh').textContent='正在刷新…';refreshTimer=setInterval(async()=>{try{const d=await api('/api/refresh-status');if(!d.running){clearInterval(refreshTimer);$('#refresh').disabled=false;$('#refresh').textContent='刷新文件位置';data=await api('/api/overview');render();setView(view);toast(d.exit_code===0?'文件位置与工作桌面已更新':'刷新存在异常，请查看管理目录中的更新日志');}}catch(e){clearInterval(refreshTimer);$('#refresh').disabled=false;toast(e.message);}},2500);}catch(e){toast(e.message);}};
async function boot(){try{data=await api('/api/overview');for(const [k,v]of Object.entries(data.categories))$('#category').add(new Option(v,k));const h=new URLSearchParams(location.hash.slice(1));project=data.projects.some(p=>p.id===h.get('project'))?h.get('project'):'';view=['board','desk','files','tasks'].includes(h.get('view'))?h.get('view'):'board';if(view==='files'&&!data.capabilities.file_index)view='board';render();setView(view);await boardInit();}catch(e){$('#intro').textContent='无法读取本地索引：'+e.message;toast(e.message);}}
boot();

// Follow completed file-index updates without changing personal arrangements.
setInterval(async()=>{if(!data||document.hidden)return;try{const fresh=await api('/api/overview');if(fresh.updated_at!==data.updated_at||JSON.stringify(fresh.projects)!==JSON.stringify(data.projects)){data=fresh;render();setView(view);toast('文件清单已有新位置，页面已更新；个人安排保留。');}}catch{}},60000);
