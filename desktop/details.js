'use strict';
// Project presentation is separate from the board and the optional file index.
const detailFields=items=>`<dl class="detail-fields">${items.filter(([,v])=>v).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>`;
const overviewSection=body=>`<section class="detail-section"><h3>项目概述</h3>${body}</section>`;
const addressSection=body=>`<section class="detail-section"><h3>项目地址</h3>${body}</section>`;
async function projectLocations(p){
 const ids=[p.local?p.local_id:'',p.remote?p.remote_id:''].filter(Boolean);
 return (await Promise.all(ids.map(id=>api('/api/item?id='+encodeURIComponent(id)).catch(()=>null)))).filter(Boolean);
}
function chatArea(){return '<div id="project-chats" class="project-chats"></div>';}
async function wireProjectChats(p){
 const target=$('#project-chats');if(!target)return;
 try{const links=await api('/api/project-links?project_id='+encodeURIComponent(p.id));if(!target.isConnected)return;
 target.innerHTML=`<div class="chat-heading"><h4>关联会话</h4><button class="text-button" id="manage-chats">管理关联</button></div>${links.threads.length?links.threads.map(t=>`<div class="chat-link"><span title="${esc(t.title)}">${esc(t.title||t.id)}</span><button class="button primary" data-chat-open="${esc(t.id)}">打开会话</button></div>`).join(''):'<p class="detail-muted">尚未关联会话</p>'}`;
 $('#manage-chats').onclick=()=>manageProjectChats(p.id);
 target.querySelectorAll('[data-chat-open]').forEach(b=>b.onclick=async()=>{try{await api('/api/open-thread',{project_id:p.id,thread_id:b.dataset.chatOpen});toast('已请求 Codex 打开会话');}catch(e){toast(e.message);}});
 }catch(e){target.textContent=e.message;}
}
async function showProject(id){try{
 const p=projectBy(id),locations=await projectLocations(p);
 drawer(`<h2>${esc(p.name)}</h2>${overviewSection(detailFields([['研究内容',p.summary],['当前进度',p.status],['采用版本',p.current_version],['结果适用范围',p.scope],['待完成事项',p.todo]])+`<div class="actions"><button class="button secondary" id="edit-project">编辑概述与地址</button>${data.capabilities.file_index?'<button class="button secondary" id="project-files">查看文件</button>':''}<button class="button secondary" id="enter-project">查看结果</button>${boardReady&&!board.cards.some(c=>c.type==='project'&&c.target===id)?'<button class="button secondary" id="add-project-card">加入桌面</button>':''}</div>`)}${addressSection(locations.map(l=>pathHtml(l,l.host==='server'?'服务器目录':'本地目录')).join('')+(!locations.length?'<p class="detail-muted">尚未登记目录</p>':'')+chatArea())}`);
 $('#edit-project').onclick=()=>editProject(id);
 $('#enter-project').onclick=()=>{close();selectProject(id);setView('desk');};
 if($('#project-files'))$('#project-files').onclick=()=>{close();selectProject(id);$('#category').value='';setView('files');};
 if($('#add-project-card'))$('#add-project-card').onclick=async()=>{if(await addProjectCard(p)){close();setView('board');}};
 await wireProjectChats(p);
}catch(e){toast(e.message);}}
async function showBundle(id){try{
 const b=data.bundles.find(b=>b.id===id),p=projectBy(b.project_id);
 const locations=[...b.locations];
 if(!b.remote.length&&p.remote){const roots=await projectLocations(p);locations.push(...roots.filter(r=>r.host==='server'));}
 drawer(`<h2>${esc(b.name)}</h2><p class="detail-muted">${esc(p.name)}</p>${overviewSection(badge(b.review_status==='reviewed'?b.category:'pending')+detailFields([['采用版本',b.current_version],['结果适用范围',b.scope],['待完成事项',b.todo]])+`<details class="provenance"><summary>来源与审核依据</summary>${b.evidence.map(x=>`<code>${esc(x)}</code>`).join('')}<p>${esc(b.reviewed_at)} · ${b.review_status==='reviewed'?'来源指纹一致':'需要复核'}</p></details>${data.capabilities.file_index?'<button class="button secondary" id="bundle-files">查看结果文件</button>':''}`)}${addressSection(locations.map(l=>pathHtml(l)).join('')+chatArea())}`);
 if($('#bundle-files'))$('#bundle-files').onclick=()=>{close();project=b.project_id;bundleFilter=id;page=1;for(const key of ['category','host','object-type','search'])$('#'+key).value='';render();setView('files');};
 await wireProjectChats(p);
}catch(e){toast(e.message);}}
async function showFile(id){try{
 const r=await api('/api/item?id='+encodeURIComponent(id)),p=projectBy(r.project_id);
 drawer(`<h2>${esc(basename(shownPath(r.path)))}</h2><p class="detail-muted">${esc(p?.name||'外部资料')}</p>${overviewSection(badge(r.category)+detailFields([['采用版本',r.current_version],['采用状态',r.version_state],['分类依据',r.basis],['结果适用范围',r.scope],['待完成事项',r.todo]])+`<details class="provenance"><summary>来源与观察记录</summary><code>${esc(r.evidence)}</code><p>位置观察：${esc(r.observed_at)}<br>用途登记：${esc(r.reviewed_at)}</p></details>`)}${addressSection(pathHtml(r)+(p?chatArea():'')+(r.host==='local'&&/\.(md|txt|tsv|csv|json)$/i.test(r.path)?'<button id="preview-text" class="button secondary">预览文本</button><pre class="preview" id="preview" hidden></pre>':''))}`);
 const b=$('#preview-text');if(b)b.onclick=async()=>{try{const d=await api('/api/preview?id='+encodeURIComponent(id));$('#preview').textContent=d.text+(d.truncated?'\n…仅展示前64 KB':'');$('#preview').hidden=false;}catch(e){toast(e.message);}};
 if(p)await wireProjectChats(p);
}catch(e){toast(e.message);}}
async function manageProjectChats(id){try{
 const p=projectBy(id),links=await api('/api/project-links?project_id='+encodeURIComponent(id)),all=await api('/api/threads');
 const known=new Map((all.threads||[]).map(t=>[t.id,t]));if(boardReady)for(const c of board.cards.filter(c=>c.type==='thread'))if(!known.has(c.target))known.set(c.target,{id:c.target,title:c.title});
 drawer(`<h2>关联会话</h2><p>${esc(p.name)}</p><div class="linked-list">${links.threads.map(t=>`<div class="chat-link"><span>${esc(t.title||t.id)}</span><button class="text-button" data-unlink="${t.id}">解除关联</button></div>`).join('')}</div><form id="chat-form" class="desk-form"><label>已有会话<select name="known"><option value="">手动填写会话链接</option>${[...known.values()].map(t=>`<option value="${t.id}">${esc(t.title)}</option>`).join('')}</select></label><label>会话 UUID 或 Codex 链接<input name="thread" required placeholder="codex://threads/…"></label><label>显示名称<input name="title" maxlength="12000" placeholder="例如：数据质控分析"></label><div class="actions"><button class="button primary" type="submit">保存关联</button><button class="button secondary" type="button" id="chats-back">返回项目</button></div></form>`);
 $('#chats-back').onclick=()=>showProject(id);
 const f=$('#chat-form');f.elements.known.onchange=()=>{const t=known.get(f.elements.known.value);if(t){f.elements.thread.value=t.id;f.elements.title.value=t.title;}};
 f.onsubmit=async e=>{e.preventDefault();const m=f.elements.thread.value.trim().match(/(?:^|\/)([a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})(?:[?/#].*)?$/i);if(!m){toast('会话链接或 UUID 无效');return;}try{await api('/api/project-links',{...links,threads:[...links.threads,{id:m[1],title:f.elements.title.value.trim()||known.get(m[1])?.title||m[1]}]});await showProject(id);}catch(e){toast(e.message);}};
 $$('[data-unlink]').forEach(b=>b.onclick=async()=>{try{await api('/api/project-links',{...links,threads:links.threads.filter(t=>t.id!==b.dataset.unlink)});await manageProjectChats(id);}catch(e){toast(e.message);}});
}catch(e){toast(e.message);}}
async function addProjectCard(p){
 if(!boardReady)return false;
 return changeBoard(()=>{if(!board.cards.some(c=>c.type==='project'&&c.target===p.id))board.cards.unshift({id:'p-'+p.id,type:'project',target:p.id,title:p.name,folder:'',zone:'inbox',x:0,y:0});});
}
async function editProject(id=''){try{
 const existing=projectBy(id),p=existing||{id:'project-'+crypto.randomUUID()},saved=await api('/api/projects');
 const input=(key,label,area=false)=>`<label>${label}${area?`<textarea name="${key}" rows="3">${esc(p[key]||'')}</textarea>`:`<input name="${key}" value="${esc(p[key]||'')}" ${key==='name'?'required':''}>`}</label>`;
 drawer(`<h2>${existing?'编辑项目':'新建项目'}</h2><form id="project-form" class="desk-form"><h3>项目概述</h3>${input('name','项目名称')}${input('summary','研究内容',true)}${input('status','当前进度')}${input('current_version','采用版本')}${input('scope','结果适用范围',true)}${input('todo','待完成事项',true)}<h3>项目地址</h3>${input('local','本地目录（可留空或使用工作区相对路径）')}${input('remote','服务器目录（可留空）')}${input('ssh_alias','SSH 主机别名（可留空）')}<div class="actions"><button class="button primary" type="submit">保存项目</button><button class="button secondary" type="button" id="project-cancel">取消</button></div></form>`);
 $('#project-cancel').onclick=()=>existing?showProject(id):close();
 $('#project-form').onsubmit=async e=>{e.preventDefault();const values=Object.fromEntries(new FormData(e.target));try{await api('/api/projects',{revision:saved.revision,project:{id:p.id,...values}});data=await api('/api/overview');render();setView(view);if(!existing)await addProjectCard(projectBy(p.id));await showProject(p.id);}catch(e){toast(e.message);}};
}catch(e){toast(e.message);}}
