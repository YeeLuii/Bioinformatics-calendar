'use strict';
// Tasks are domain records. Cards are optional shortcuts and never own tasks.
let archivedProjects=[],lastTaskWarnings=[];
const knownProjectBy=id=>projectBy(id)||archivedProjects.find(p=>p.id===id);
const taskProjectLabel=id=>{const p=knownProjectBy(id);return p?p.name+(p.archived?'（已归档）':''):id?'项目 '+id:'未关联项目';};
let tasksReady=false,taskRevision=0,taskItems=[],taskMode='today',taskSearch='',taskStatus='',taskBusy=false;
const taskStates={todo:'待开始',doing:'进行中',blocked:'受阻',done:'已完成'};
const repeatNames={none:'不重复',daily:'每天',weekly:'每周',monthly:'每月'};
const dayNumber=s=>Math.floor(Date.parse(s+'T00:00:00Z')/86400000);
const shiftDate=(s,n)=>new Date((dayNumber(s)+n)*86400000).toISOString().slice(0,10);
const taskProject=t=>t.project_id||((boardReady&&cardBy(t.card)?.type==='project')?cardBy(t.card).target:'');
const taskState=t=>t.status||(t.done?'done':'todo');
const taskStart=t=>t.start_date||t.date;
const taskBy=id=>taskItems.find(t=>t.id===id);
async function requestAPI(url,method='GET',body){
 const r=await fetch(url,{method,headers:{'Content-Type':'application/json',...(body?{'X-Desk-Token':data.token}:{})},...(body?{body:JSON.stringify(body)}:{})});
 const d=await r.json();if(!r.ok){const e=Error(d.error||d.message||'操作失败');e.status=r.status;throw e;}return d;
}
async function loadTasks({idleOnly=false}={}){
 const [fresh,projects]=await Promise.all([requestAPI('/api/v1/tasks'),requestAPI('/api/v1/projects?include_archived=true')]);
 const currentBoard=boardReady?await api('/api/board-state'):null;
 if(idleOnly&&(!$('#drawer').hidden||boardBusy||taskBusy||ganttDrag))return fresh;
 archivedProjects=projects.projects.filter(p=>p.archived);taskItems=currentBoard?structuredClone(currentBoard.todos):fresh.tasks;taskRevision=currentBoard?currentBoard.revision:fresh.revision;tasksReady=true;
 if(currentBoard){board=currentBoard;renderBoard();renderCalendar();}
 renderTasks();if(view==='gantt')renderGantt();return fresh;
}

async function mutateTask(id,patch,remove=false){
 if(taskBusy){toast('正在保存任务，请稍候');return false;}taskBusy=true;
 try{
  const result=await requestAPI('/api/v1/tasks'+(id?'/'+encodeURIComponent(id)+(remove?'/remove':''):''),id&&!remove?'PATCH':'POST',{expected_revision:taskRevision,...(remove?{}:id?{patch}:{task:patch})});
  taskItems=result.tasks;taskRevision=result.revision;tasksReady=true;
  if(boardReady){try{board=await api('/api/board-state');taskItems=structuredClone(board.todos);taskRevision=board.revision;renderBoard();renderCalendar();}catch(e){toast('任务已保存，但桌面同步失败，请刷新页面。');}}
  renderTasks();if(view==='gantt')renderGantt();
  lastTaskWarnings=result.warnings||[];if(result.warnings?.length)toast('已保存；'+result.warnings.map(w=>typeof w==='string'?w:w.message||JSON.stringify(w)).join('；'));
  return true;
 }catch(e){if(e.status===409){await loadTasks();toast('其他页面或 Agent 已更新任务。已读取最新记录，请检查后再保存。');}else toast(e.message);return false;}
 finally{taskBusy=false;}
}
async function toggleTask(id,done){await mutateTask(id,{status:done?'done':'todo',progress:done?100:0,done});}
function reviewReasons(p){
 const reasons=[];if(!p.source)reasons.push('尚未登记来源');
 if(!p.observed_at)reasons.push('观察时间待补充');else if(Number.isFinite(Date.parse(p.observed_at))&&Date.now()-Date.parse(p.observed_at)>14*86400000)reasons.push('超过 14 天未观察');
 if(!p.reviewed_at)reasons.push('尚未登记复核');
 if(p.adoption_status==='pending')reasons.push('采用状态待确认');
 if(data.bundles.some(b=>b.project_id===p.id&&b.review_status!=='reviewed'))reasons.push('有结果需要复核');
 return reasons;
}
function filteredTasks(mode=taskMode){
 const today=localDate(new Date()),end=shiftDate(today,6),q=taskSearch.trim().toLocaleLowerCase();
 return taskItems.filter(t=>!project||taskProject(t)===project).filter(t=>!taskStatus||taskState(t)===taskStatus)
  .filter(t=>!q||[t.title,t.notes,taskProjectLabel(taskProject(t))].join(' ').toLocaleLowerCase().includes(q))
  .filter(t=>mode==='today'?(taskState(t)!=='done'&&(t.date<=today||taskStart(t)<=today&&t.date>=today)):mode==='week'?(taskState(t)!=='done'&&taskStart(t)<=end&&(t.date>=today||t.date<today)):true)
  .sort((a,b)=>a.date.localeCompare(b.date)||a.title.localeCompare(b.title));
}
function taskRow(t){
 const p=knownProjectBy(taskProject(t)),state=taskState(t),overdue=state!=='done'&&t.date<localDate(new Date());
 return `<article class="task-line ${state}"><input type="checkbox" data-task-toggle="${esc(t.id)}" ${state==='done'?'checked':''} aria-label="完成 ${esc(t.title)}"><button class="task-main" data-task-edit="${esc(t.id)}"><strong>${t.milestone?'◆ ':''}${esc(t.title)}</strong><span>${esc(taskProjectLabel(taskProject(t)))} · ${esc(taskStart(t)===t.date?t.date:taskStart(t)+' → '+t.date)}${overdue?' · 已逾期':''}${t.repeat&&t.repeat!=='none'?' · '+repeatNames[t.repeat]:''}</span></button><span class="task-state ${state}">${taskStates[state]}</span><div class="task-progress" aria-label="完成进度 ${Number(t.progress)||0}%"><i style="width:${Number(t.progress)||0}%"></i></div><span class="task-percent">${Number(t.progress)||0}%</span></article>`;
}
function wireTaskRows(root){
 root.querySelectorAll('[data-task-edit]').forEach(b=>b.onclick=()=>taskEditor(b.dataset.taskEdit));
 root.querySelectorAll('[data-task-toggle]').forEach(b=>b.onchange=()=>toggleTask(b.dataset.taskToggle,b.checked));
}
function renderTasks(){
 if(!data||!$('#tasks-content'))return;
 $$('[data-task-mode]').forEach(b=>{b.classList.toggle('active',b.dataset.taskMode===taskMode);b.setAttribute('aria-pressed',b.dataset.taskMode===taskMode);});
 if(!tasksReady){$('#tasks-content').innerHTML='<p class="empty">正在读取任务…</p>';return;}
 if(taskMode==='review'){
  const q=taskSearch.toLocaleLowerCase(),ps=data.projects.filter(p=>(!project||p.id===project)&&reviewReasons(p).length&&(!q||[p.name,p.summary,p.source].join(' ').toLocaleLowerCase().includes(q)));
  $('#task-summary').textContent=`${ps.length} 个项目需要检查资料`;
  $('#tasks-content').innerHTML=ps.length?ps.map(p=>`<article class="review-card"><div><h3>${esc(p.name)}</h3><p>${esc(reviewReasons(p).join(' · '))}</p><small>上次观察：${esc(p.observed_at||'未登记')} · 此提示不表示分析失败</small></div><button class="button secondary" data-review-project="${esc(p.id)}">查看项目</button></article>`).join(''):'<div class="empty">当前筛选下没有需要复核的项目。</div>';
  $$('[data-review-project]').forEach(b=>b.onclick=()=>showProject(b.dataset.reviewProject));return;
 }
 const tasks=filteredTasks();$('#task-summary').textContent=`${tasks.length} 项任务${taskMode==='today'?' · 包含今天进行中及逾期待办':taskMode==='week'?' · 未来七天与逾期待办':''}`;
 $('#tasks-content').innerHTML=tasks.length?tasks.map(taskRow).join(''):'<div class="empty">这里还没有任务。添加一个具体的下一步，或切换到“全部任务”。</div>';wireTaskRows($('#tasks-content'));
}
async function taskEditor(id='',defaults={}){
 activeFolder='';if(!tasksReady)try{await loadTasks();}catch(e){toast(e.message);return;}
 const existing=taskBy(id),t=existing||{id:newId('task'),title:'',project_id:project,start_date:selectedDay,date:selectedDay,status:'todo',progress:0,dependencies:[],milestone:false,repeat:'none',notes:'',card:'',...defaults};
 const projectId=taskProject(t),currentState=taskState(t);
 drawer(`<h2>${existing?'编辑任务':'新增任务'}</h2><form id="task-form" class="desk-form"><label>任务名称<input name="title" required maxlength="1000" value="${esc(t.title)}" placeholder="例如：复核样本质量报告"></label><label>所属项目<select name="project_id"><option value="">不关联项目</option>${data.projects.map(p=>`<option value="${esc(p.id)}" ${p.id===projectId?'selected':''}>${esc(p.name)}</option>`).join('')}${projectId&&!projectBy(projectId)?`<option value="${esc(projectId)}" selected>${esc(taskProjectLabel(projectId))}</option>`:''}</select></label><div class="form-columns"><label>开始日期<input type="date" name="start_date" required value="${esc(taskStart(t))}"></label><label>截止日期<input type="date" name="date" required value="${esc(t.date)}"></label></div><div class="form-columns"><label>任务状态<select name="status">${Object.entries(taskStates).map(([k,v])=>`<option value="${k}" ${currentState===k?'selected':''}>${v}</option>`).join('')}</select></label><label>完成进度（%）<input type="number" name="progress" min="0" max="100" step="1" required value="${Number(t.progress)||0}"></label></div><label class="check-label"><input type="checkbox" name="milestone" ${t.milestone?'checked':''}> 里程碑（开始与截止为同一天）</label><label>重复安排<select name="repeat">${Object.entries(repeatNames).map(([k,v])=>`<option value="${k}" ${t.repeat===k?'selected':''}>${v}</option>`).join('')}</select></label><label>前置任务<select name="dependencies" multiple size="${Math.min(5,Math.max(2,taskItems.length-1))}" aria-describedby="dependency-help">${taskItems.filter(x=>x.id!==id).map(x=>`<option value="${esc(x.id)}" ${(t.dependencies||[]).includes(x.id)?'selected':''}>${esc(x.title)} · ${esc(taskProjectLabel(taskProject(x)))}</option>`).join('')}</select></label><p id="dependency-help" class="form-note">可按 Ctrl / Command 选择多项。前置任务变动时显示日期冲突，不会自动改动后续安排。</p><label>备注<textarea name="notes" rows="3" maxlength="12000">${esc(t.notes||'')}</textarea></label><label>关联会话或目录快捷方式（可选）<select name="card"><option value="">不关联快捷方式</option>${(boardReady?board.cards:[]).map(c=>`<option value="${esc(c.id)}" ${t.card===c.id?'selected':''}>${esc(c.title)}</option>`).join('')}</select></label><p class="form-note">任务会直接保存所属项目。移除桌面快捷方式不会解除项目关联。重复任务在本次完成后生成下一次安排。</p><div id="task-form-error" class="inline-error" role="alert" hidden></div><div class="actions"><button class="button primary" type="submit">保存任务</button><button class="button secondary" type="button" id="task-cancel">取消</button>${existing?'<button class="text-button danger" type="button" id="task-remove">删除任务</button>':''}</div></form>${projectId?'<button class="text-button" id="task-open-project">查看所属项目</button>':''}`);
 const form=$('#task-form');$('#task-cancel').onclick=close;
 form.elements.status.onchange=()=>{if(form.elements.status.value==='done')form.elements.progress.value=100;else if(form.elements.progress.value==='100')form.elements.progress.value=0;};
 form.elements.milestone.onchange=()=>{if(form.elements.milestone.checked)form.elements.date.value=form.elements.start_date.value;};
 form.elements.start_date.onchange=()=>{if(form.elements.milestone.checked)form.elements.date.value=form.elements.start_date.value;};
 form.onsubmit=async e=>{
  e.preventDefault();const f=new FormData(form),v={title:String(f.get('title')).trim(),project_id:String(f.get('project_id')),start_date:String(f.get('start_date')),date:String(f.get('date')),status:String(f.get('status')),progress:Number(f.get('progress')),dependencies:f.getAll('dependencies'),milestone:f.has('milestone'),repeat:String(f.get('repeat')),notes:String(f.get('notes')),card:String(f.get('card'))};
  v.done=v.status==='done';if(v.done)v.progress=100;
  const err=$('#task-form-error');err.hidden=true;
  if(v.start_date>v.date||v.milestone&&v.start_date!==v.date){err.textContent='截止日期不能早于开始日期；里程碑须安排在同一天。';err.hidden=false;return;}
  if(!existing)v.id=t.id;
  form.querySelector('[type=submit]').disabled=true;
  const ok=await mutateTask(id,v);if(ok){selectedDay=v.date;calendarMonth=new Date(v.date+'T12:00:00');calendarMonth.setDate(1);renderCalendar();close();toast(lastTaskWarnings.length?'任务已保存，有 '+lastTaskWarnings.length+' 项依赖提醒，请在甘特图检查。':'任务已保存');}else form.querySelector('[type=submit]').disabled=false;
 };
 if(existing)$('#task-remove').onclick=async()=>{if(await mutateTask(id,{},true)){close();toast('任务已删除，可在修改记录中撤销');}};
 if(projectId)$('#task-open-project').onclick=()=>projectBy(projectId)?showProject(projectId):showArchivedProjects();
}
function downloadText(text,name,type='text/plain;charset=utf-8'){
 const url=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function exportCalendar(){
 try{const r=await requestAPI('/api/v1/export?'+new URLSearchParams({format:'ics',...(project?{project_id:project}:{})}));downloadText(r.content,r.filename,'text/calendar;charset=utf-8');toast('已导出已生成任务的快照；提醒由导入的日历应用设置');}catch(e){toast(e.message);}
}

function wireTasks(){
 $$('[data-task-mode]').forEach(b=>b.onclick=()=>{taskMode=b.dataset.taskMode;renderTasks();});
 $('#task-search').oninput=e=>{taskSearch=e.target.value;renderTasks();};$('#task-status').onchange=e=>{taskStatus=e.target.value;renderTasks();};
 $('#task-new').onclick=()=>taskEditor();$('#task-export').onclick=exportCalendar;
}
wireTasks();
