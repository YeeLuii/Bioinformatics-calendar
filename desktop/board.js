'use strict';
let board,threadSources=[],boardBusy=false,boardReady=false,boardFilter='',boardKind='',activeFolder='';
const zoneNames={inbox:'待安排',do:'重要且紧急',plan:'重要不紧急',delegate:'紧急不重要',later:'不紧急不重要'};
const typeNames={project:'研究项目',thread:'Codex 会话',folder:'桌面文件夹',directory:'目录快捷方式'};
const typeIcons={project:'▧',thread:'✦',folder:'▰',directory:'↗'};
const localDate=d=>[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
let selectedDay=localDate(new Date()),calendarMonth=new Date(new Date().getFullYear(),new Date().getMonth(),1);
const cardBy=id=>board.cards.find(c=>c.id===id);
const visibleCards=()=>board.cards.filter(c=>c.type!=='project'||projectBy(c.target));
const newId=prefix=>prefix+'-'+crypto.randomUUID();
async function boardInit(){
 try{[board,threadSources]=await Promise.all([api('/api/board-state'),api('/api/threads')]);threadSources=threadSources.threads;boardReady=true;renderBoard();renderCalendar();}catch(e){$('#board-save').textContent='桌面加载失败：'+e.message;}
}
async function changeBoard(fn){
 if(boardBusy){toast('正在保存，请稍候');return false;}
 const previous=structuredClone(board);fn();boardBusy=true;$('#board-save').textContent='正在保存…';
 try{board=await api('/api/board-state',board);renderBoard();renderCalendar();return true;}catch(e){board=previous;renderBoard();toast('未保存：'+e.message);return false;}finally{boardBusy=false;}
}
function cardHTML(c,positioned=false){
 const children=visibleCards().filter(x=>x.folder===c.id).length;
 const style=positioned?` style="left:${c.x*100}%;top:${c.y*100}%;translate:-${c.x*100}% -${c.y*100}%"`:'';
 return `<article class="desk-item ${c.type}" draggable="true" data-card="${esc(c.id)}"${style}><button class="card-face" data-card-go="${esc(c.id)}" title="${esc(c.title)}"><span class="desk-icon">${typeIcons[c.type]}</span><span class="desk-title">${esc(c.title)}</span><span class="desk-type">${c.type==='folder'?children+' 个项目 / 会话':typeNames[c.type]}</span></button><button class="card-more" data-card-edit="${esc(c.id)}" aria-label="安排 ${esc(c.title)}" title="安排、关联待办或修改">···</button></article>`;
}
function wireCards(root){
 root.querySelectorAll('[data-card-go]').forEach(b=>b.onclick=()=>openCard(b.dataset.cardGo));
 root.querySelectorAll('[data-card-edit]').forEach(b=>b.onclick=()=>cardEditor(b.dataset.cardEdit));
 root.querySelectorAll('[data-card]').forEach(el=>{
  el.ondragstart=e=>{e.dataTransfer.setData('text/plain',el.dataset.card);e.dataTransfer.effectAllowed='move';el.classList.add('dragging');};
  el.ondragend=()=>el.classList.remove('dragging');
  if(cardBy(el.dataset.card).type==='folder'){
   el.ondragover=e=>{e.preventDefault();e.stopPropagation();el.classList.add('drop-folder');};
   el.ondragleave=()=>el.classList.remove('drop-folder');
   el.ondrop=e=>{e.preventDefault();e.stopPropagation();el.classList.remove('drop-folder');const id=e.dataTransfer.getData('text/plain'),c=cardBy(id);if(!c)return;if(c.type==='folder'){toast('文件夹暂不支持嵌套');return;}changeBoard(()=>{c.folder=el.dataset.card;}).then(ok=>{if(ok)toast('已收进桌面文件夹');});};
  }
 });
}
function renderBoard(){
 if(!boardReady)return;
 const pool=visibleCards().filter(c=>!c.folder&&c.zone==='inbox').filter(c=>(!boardKind||c.type===boardKind)&&(!boardFilter||(c.title+' '+c.target).toLowerCase().includes(boardFilter.toLowerCase())));
 $('#inbox-cards').innerHTML=pool.map(c=>cardHTML(c)).join('')||'<div class="board-empty">这里没有匹配的卡片。</div>';
 $('#inbox-count').textContent=visibleCards().filter(c=>!c.folder&&c.zone==='inbox').length;
 for(const zone of ['do','plan','delegate','later']){
  const cs=visibleCards().filter(c=>!c.folder&&c.zone===zone);
  $('#zone-'+zone).innerHTML=cs.map(c=>cardHTML(c,true)).join('')||'';

 }
 $('#board-save').textContent=board.saved_at?'已保存 · '+board.saved_at.slice(11,19):'安排会自动保存到本机';
 wireCards($('#board-view'));
 if(activeFolder&&!$('#drawer').hidden)folderView(activeFolder);
}
async function openCard(id){
 const c=cardBy(id);if(!c)return;
 if(c.type==='folder')return folderView(id);
 if(c.type==='project')return showProject(c.target);
 try{
  // Persist initial imported cards once so navigation targets are registered on disk.
  if(board.revision===0&&!await changeBoard(()=>{}))return;
  await api('/api/open-card',{id});toast(c.type==='thread'?'已请求 Codex 打开会话；如果没有切换，请在卡片菜单复制会话链接。':'已打开目录');
 }catch(e){toast(e.message);}
}
function folderView(id){
 const c=cardBy(id);if(!c)return;activeFolder=id;
 const cs=visibleCards().filter(x=>x.folder===id);
 drawer(`<h2>▰ ${esc(c.title)}</h2><p>这是桌面上的会话分组，不会移动磁盘文件，也不会修改 Codex 的项目归属。</p><div class="actions"><button class="button secondary" id="folder-edit">重命名 / 安排</button><button class="button secondary" id="folder-add">添加会话快捷方式</button></div><div class="folder-grid">${cs.map(x=>cardHTML(x)).join('')||'<p class="board-empty">把桌面卡片拖到文件夹上，或在卡片菜单选择此文件夹。</p>'}</div>`);
 wireCards($('#details'));$('#folder-edit').onclick=()=>cardEditor(id);$('#folder-add').onclick=()=>cardEditor('', 'thread',id);
}
function locationOptions(c){return Object.entries(zoneNames).map(([k,v])=>`<option value="${k}" ${c.zone===k?'selected':''}>${v}</option>`).join('');}
function cardEditor(id='',type='folder',parent=''){
 activeFolder='';const existing=cardBy(id),c=existing||{id:newId('c'),type,title:'',target:'',folder:parent,zone:'inbox',x:0,y:0};
 const isNew=!existing;
 drawer(`<h2>${isNew?'添加'+typeNames[c.type]:'安排卡片'}</h2><form id="card-form" class="desk-form"><label>显示名称<input name="title" required maxlength="12000" value="${esc(c.title)}" placeholder="例如：样本质控"></label>${c.type==='thread'?`<label>Codex 会话 ID 或链接<input name="target" required value="${esc(c.target)}" placeholder="codex://threads/会话UUID"></label><p class="form-note">点击卡片将打开已有会话。继续提问、重命名或归档，请在 Codex 中完成。</p>`:c.type==='directory'?`<label>本机目录的完整路径<input name="target" required value="${esc(c.target)}" placeholder="D:\\项目目录"></label><p class="form-note">此处添加目录入口，不会移动目录。</p>`:''}<label>摆放区域<select name="zone">${locationOptions(c)}</select></label>${c.type!=='folder'?`<label>收进文件夹<select name="folder"><option value="">直接显示在桌面</option>${board.cards.filter(x=>x.type==='folder').map(f=>`<option value="${f.id}" ${c.folder===f.id?'selected':''}>${esc(f.title)}</option>`).join('')}</select></label>`:''}<div class="actions"><button class="button primary" type="submit">保存安排</button><button class="button secondary" type="button" id="card-cancel">取消</button></div></form>${existing?`<div class="actions"><button class="button secondary" id="card-task">为这张卡片添加待办</button>${c.type==='thread'?'<button class="button secondary" id="card-link">复制会话链接</button><button class="button secondary" id="card-resume">复制 CLI 续接命令</button>':''}<button class="text-button danger" id="card-remove">移除桌面快捷方式</button></div><p class="form-note">移除快捷方式保留真实会话和源文件；文件夹内的卡片将返回待安排区。</p>`:''}`);
 $('#card-cancel').onclick=close;
 $('#card-form').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.target);let target=String(fd.get('target')??c.target).trim();if(c.type==='thread'){const m=target.match(/(?:^|\/)([a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})(?:[?/#].*)?$/i);if(!m){toast('请填写有效的会话 UUID 或 codex://threads/ 链接');return;}target=m[1];}
 const value={...c,title:String(fd.get('title')).trim(),target,zone:String(fd.get('zone')),folder:String(fd.get('folder')||'')};if(value.zone!==c.zone&&value.zone!=='inbox'&&!value.folder){const occupied=board.cards.filter(x=>!x.folder&&x.zone===value.zone&&x.id!==c.id).length;value.x=(occupied%2)*0.9;value.y=(Math.floor(occupied/2)%3)*0.45;}
 if(await changeBoard(()=>{if(existing)Object.assign(existing,value);else board.cards.unshift(value);})){close();if(isNew){boardFilter='';boardKind='';$('#board-search').value='';$('#board-kind').value='';renderBoard();$('#inbox-cards').scrollTop=0;}toast('安排已保存');}
 };
 if(existing){$('#card-task').onclick=()=>todoEditor('',c.id);$('#card-remove').onclick=async()=>{if(await changeBoard(()=>{board.cards=board.cards.filter(x=>x.id!==id);visibleCards().filter(x=>x.folder===id).forEach(x=>{x.folder='';x.zone='inbox';});board.todos.filter(x=>x.card===id).forEach(x=>x.card='');})){close();toast('已移除快捷方式，源会话与文件保留');}};
 if(c.type==='thread'){$('#card-link').onclick=()=>copy('codex://threads/'+c.target);$('#card-resume').onclick=()=>copy('codex resume '+c.target);}}
}
function renderCalendar(){
 if(!boardReady)return;const year=calendarMonth.getFullYear(),month=calendarMonth.getMonth();
 $('#month-label').textContent=`${year} 年 ${month+1} 月`;const start=(new Date(year,month,1).getDay()+6)%7,days=new Date(year,month+1,0).getDate();
 let html=Array.from({length:start},()=>'<span></span>').join('');
 for(let d=1;d<=days;d++){const date=localDate(new Date(year,month,d)),tasks=board.todos.filter(t=>t.date===date),pending=tasks.filter(t=>!t.done).length;html+=`<button class="calendar-day ${date===selectedDay?'selected':''} ${date===localDate(new Date())?'today':''}" data-day="${date}" aria-label="${date}，${pending} 项未完成" aria-pressed="${date===selectedDay}"><span>${d}</span>${tasks.length?`<i class="${pending?'':'complete'}"></i>`:''}</button>`;}
 $('#calendar-grid').innerHTML=html;$$('[data-day]').forEach(b=>b.onclick=()=>{selectedDay=b.dataset.day;renderCalendar();});
 const due=board.todos.filter(t=>t.date===selectedDay);$('#selected-day').textContent=selectedDay.slice(5).replace('-',' 月 ')+' 日';
 $('#todo-list').innerHTML=due.map(t=>`<div class="todo-row ${t.done?'done':''}"><input type="checkbox" data-toggle-task="${t.id}" ${t.done?'checked':''} aria-label="完成 ${esc(t.title)}"><button data-edit-task="${t.id}"><span>${esc(t.title)}</span><small>${esc(cardBy(t.card)?.title||'未关联卡片')}</small></button></div>`).join('')||'<p class="calendar-empty">暂无待办</p>';
 $$('[data-toggle-task]').forEach(b=>b.onchange=()=>changeBoard(()=>{board.todos.find(t=>t.id===b.dataset.toggleTask).done=b.checked;}));
 $$('[data-edit-task]').forEach(b=>b.onclick=()=>todoEditor(b.dataset.editTask));
 const overdue=board.todos.filter(t=>!t.done&&t.date<localDate(new Date()));$('#overdue').textContent=overdue.length?`${overdue.length} 项待办已过期 · 点击查看`:'';$('#overdue').hidden=!overdue.length;
}
function todoEditor(id='',card=''){
 activeFolder='';const existing=board.todos.find(t=>t.id===id),t=existing||{id:newId('todo'),title:'',date:selectedDay,card,done:false};
 drawer(`<h2>${existing?'编辑待办':'添加待办'}</h2><form id="todo-form" class="desk-form"><label>要完成的事<input name="title" required maxlength="1000" value="${esc(t.title)}" placeholder="写下一个具体、可完成的小步骤"></label><label>计划日期<input type="date" name="date" required value="${t.date}"></label><label>关联项目 / 会话<select name="card"><option value="">不关联</option>${board.cards.map(c=>`<option value="${c.id}" ${c.id===t.card?'selected':''}>${esc(c.title)}</option>`).join('')}</select></label><label class="check-label"><input type="checkbox" name="done" ${t.done?'checked':''}> 已完成</label><div class="actions"><button type="submit" class="button primary">保存待办</button><button type="button" class="button secondary" id="todo-cancel">取消</button>${existing?'<button type="button" class="text-button danger" id="todo-remove">删除此待办</button>':''}</div></form>${t.card?'<button id="todo-card" class="button secondary">打开关联卡片</button>':''}`);
 $('#todo-cancel').onclick=close;
 $('#todo-form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target),v={...t,title:String(f.get('title')).trim(),date:String(f.get('date')),card:String(f.get('card')),done:f.has('done')};if(await changeBoard(()=>{if(existing)Object.assign(existing,v);else board.todos.push(v);})){selectedDay=v.date;calendarMonth=new Date(v.date+'T12:00:00');calendarMonth.setDate(1);renderCalendar();close();toast('待办已保存');}};
 if(existing)$('#todo-remove').onclick=async()=>{if(await changeBoard(()=>board.todos=board.todos.filter(x=>x.id!==id)))close();};
 if(t.card)$('#todo-card').onclick=()=>{close();openCard(t.card);};
}
function wireBoard(){
 for(const id of ['do','plan','delegate','later','inbox']){
  const el=id==='inbox'?$('#inbox-cards'):$('#zone-'+id);
  el.ondragover=e=>{e.preventDefault();e.dataTransfer.dropEffect='move';el.classList.add('drop-active');};
  el.ondragleave=e=>{if(!el.contains(e.relatedTarget))el.classList.remove('drop-active');};
  el.ondrop=e=>{e.preventDefault();el.classList.remove('drop-active');const c=cardBy(e.dataTransfer.getData('text/plain'));if(!c)return;const r=el.getBoundingClientRect(),style=getComputedStyle(el),w=parseFloat(style.getPropertyValue('--desk-card-width'))||148,h=parseFloat(style.getPropertyValue('--desk-card-height'))||62;changeBoard(()=>{c.zone=id;c.folder='';c.x=Math.max(0,Math.min(1,(e.clientX-r.left-w/2)/Math.max(1,r.width-w)));c.y=Math.max(0,Math.min(1,(e.clientY-r.top-h/2)/Math.max(1,r.height-h)));});};
 }
 $('#new-folder').onclick=()=>cardEditor();$('#new-thread').onclick=()=>cardEditor('','thread');$('#new-directory').onclick=()=>cardEditor('','directory');
 $('#board-search').oninput=e=>{boardFilter=e.target.value;renderBoard();};$('#board-kind').onchange=e=>{boardKind=e.target.value;renderBoard();};
 $('#add-todo').onclick=()=>todoEditor();$('#month-prev').onclick=()=>{calendarMonth.setMonth(calendarMonth.getMonth()-1);renderCalendar();};$('#month-next').onclick=()=>{calendarMonth.setMonth(calendarMonth.getMonth()+1);renderCalendar();};
 $('#calendar-today').onclick=()=>{selectedDay=localDate(new Date());calendarMonth=new Date();calendarMonth.setDate(1);renderCalendar();};
 $('#overdue').onclick=()=>{const tasks=board.todos.filter(t=>!t.done&&t.date<localDate(new Date())).sort((a,b)=>a.date.localeCompare(b.date));drawer('<h2>已过期的待办</h2>'+tasks.map(t=>`<button class="overdue-task" data-overdue-task="${t.id}">${esc(t.date)} · ${esc(t.title)}</button>`).join(''));$$('[data-overdue-task]').forEach(b=>b.onclick=()=>todoEditor(b.dataset.overdueTask));};
 $('#board-backup').onclick=()=>{const blob=new Blob([JSON.stringify(board,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='research-desk-'+localDate(new Date())+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 $('#board-help').onclick=()=>drawer('<h2>使用说明</h2><p>从“待安排”拖出卡片，放进四象限。卡片在同一个象限内也能自由摆放。拖到文件夹上就能收进去；点卡片右上角的 ··· 可以用菜单调整位置、移出文件夹、关联待办。</p><h3>点击卡片会发生什么</h3><p>项目卡片打开结果、版本与目录详情；会话卡片调用本机 Codex；目录卡片打开文件资源管理器；文件夹展示里面的卡片。桌面上的文件夹只是视觉分组。</p><h3>日历与保存</h3><p>点击日期，再添加待办。勾选可标记完成，点击文字可编辑日期和关联会话。日期按本机时间显示。这是计划日历，不会自动启动分析或弹出定时提醒。</p><p>安排保存在工作区数据目录的 desktop_board_state.json；前一次保存为 desktop_board_state.previous.json。文件清单更新不会覆盖你的安排。</p><h3>会话导入范围</h3><p>会话目录来自工作区已有登记。可以用“添加会话”补充链接。登记信息不代表会话当前的运行状态。</p>');
}
wireBoard();
