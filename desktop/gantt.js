'use strict';
// Calendar arithmetic uses UTC day numbers; labels represent local calendar dates.
let ganttZoom='day',ganttStart='',ganttShowDone=true,ganttSuppressClick=false,ganttDrag=null;
function ganttTodayLookback(){const label=window.innerWidth<760?150:240,cell=ganttZoom==='day'?34:12,viewport=$('#gantt-chart').clientWidth||(window.innerWidth<760?window.innerWidth-24:800);return Math.max(1,Math.min(7,Math.floor(Math.max(cell,viewport-label)*0.35/cell)));}
function renderGantt(){
 if(!tasksReady){$('#gantt-chart').innerHTML='<div class="empty">正在读取任务…</div>';return;}
 const today=localDate(new Date()),tasks=taskItems.filter(t=>(!project||taskProject(t)===project)&&(ganttShowDone||taskState(t)!=='done'));
 if(!ganttStart)ganttStart=shiftDate(today,-ganttTodayLookback());
 const labelWidth=window.innerWidth<760?150:240;
 const days=ganttZoom==='day'?90:365,cell=ganttZoom==='day'?34:12,width=days*cell,end=shiftDate(ganttStart,days-1);
 $('#gantt-count').textContent=`${tasks.length} 项任务 · ${ganttStart} 至 ${end}`;
 if(!$('#gantt-range-start')){
  const nav=document.createElement('div');nav.className='gantt-range';nav.innerHTML='<button class="button secondary" id="gantt-prev" aria-label="前一时间范围">‹</button><label>从 <input type="date" id="gantt-range-start" aria-label="甘特图开始日期"></label><button class="button secondary" id="gantt-next" aria-label="后一时间范围">›</button>';
  $('.gantt-filters').prepend(nav);
  $('#gantt-range-start').onchange=e=>{if(e.target.value){ganttStart=e.target.value;renderGantt();}};
  $('#gantt-prev').onclick=()=>{ganttStart=shiftDate(ganttStart,ganttZoom==='day'?-30:-90);renderGantt();};
  $('#gantt-next').onclick=()=>{ganttStart=shiftDate(ganttStart,ganttZoom==='day'?30:90);renderGantt();};
 }
 $('#gantt-range-start').value=ganttStart;
 if(!tasks.length){$('#gantt-chart').innerHTML='<div class="empty">为项目添加带开始和截止日期的任务，即可在这里安排时间。<br><button class="button primary" id="gantt-empty-add">新增第一项任务</button></div>';$('#gantt-empty-add').onclick=()=>taskEditor();$('#gantt-warning').hidden=true;return;}
 const groups=new Map();for(const t of tasks){const id=taskProject(t);if(!groups.has(id))groups.set(id,[]);groups.get(id).push(t);}
 const rangeStart=dayNumber(ganttStart),coords=new Map(),warnings=[];let y=54;
 const header=Array.from({length:days},(_,i)=>{const d=shiftDate(ganttStart,i),m=new Date(d+'T12:00:00').getDay(),visible=ganttZoom==='day'||m===1||i===0;return `<span class="gantt-tick ${m===0||m===6?'weekend':''} ${d===today?'today':''}" style="left:${i*cell}px;width:${cell}px">${visible?`<b>${d.slice(5).replace('-','/')}</b>${ganttZoom==='day'?'<small>'+['日','一','二','三','四','五','六'][m]+'</small>':''}`:''}</span>`;}).join('');
 let rows='';
 for(const [pid,items]of groups){
  const p=knownProjectBy(pid);rows+=`<div class="gantt-group"><div class="gantt-label">${esc(taskProjectLabel(pid))}<span>${items.length}</span></div><div class="gantt-group-track" style="width:${width}px"></div></div>`;y+=34;
  for(const t of items.sort((a,b)=>taskStart(a).localeCompare(taskStart(b))||a.date.localeCompare(b.date))){
   const start=dayNumber(taskStart(t))-rangeStart,finish=dayNumber(t.date)-rangeStart+1,left=Math.max(0,start)*cell,right=Math.min(days,finish)*cell,visible=finish>0&&start<days;
   const state=taskState(t);coords.set(t.id,{start:start*cell,end:finish*cell,y:y+23,visible});
   const depWarnings=(t.dependencies||[]).filter(id=>taskBy(id)&&taskBy(id).date>=taskStart(t));if(depWarnings.length)warnings.push(t.title+' 的开始日期未晚于前置任务截止日期');
   rows+=`<div class="gantt-row"><button class="gantt-label" data-gantt-edit="${esc(t.id)}" title="编辑 ${esc(t.title)}"><span class="task-state-dot ${state}"></span><span>${esc(t.title)}</span>${t.milestone?'<small>◆</small>':''}</button><div class="gantt-track" style="width:${width}px;--day-width:${cell}px">${visible?`<button class="gantt-bar ${state} ${t.milestone?'milestone':''} ${depWarnings.length?'dependency-conflict':''}" data-gantt-task="${esc(t.id)}" style="left:${left}px;width:${t.milestone?20:Math.max(22,right-left-3)}px" aria-label="${esc(t.title)}，${taskStart(t)} 至 ${t.date}，进度 ${Number(t.progress)||0}%，点击编辑" title="${esc(t.title)} · ${taskStart(t)} 至 ${t.date}${depWarnings.length?' · 前置日期冲突':''}">${t.milestone?'<span>◆</span>':`<i class="gantt-bar-progress" style="width:${Number(t.progress)||0}%"></i><span class="gantt-resize start" data-resize="start" aria-hidden="true"></span><span class="gantt-bar-title">${esc(t.title)} · ${Number(t.progress)||0}%</span><span class="gantt-resize end" data-resize="end" aria-hidden="true"></span>`}</button>`:`<button class="gantt-outside" data-gantt-locate="${esc(t.id)}">${taskStart(t)} → ${t.date} · 定位任务</button>`}</div></div>`;y+=46;
  }
 }
 const connectors=[];
 for(const t of tasks)for(const id of t.dependencies||[]){const a=coords.get(id),b=coords.get(t.id);if(!a||!b||!a.visible||!b.visible)continue;const x1=Math.min(width,a.end),x2=Math.max(0,b.start),bend=Math.max(x1+12,x2-12),bad=taskBy(id).date>=taskStart(t);connectors.push(`<path d="M ${x1} ${a.y} H ${bend} V ${b.y} H ${x2}" class="${bad?'conflict':''}" marker-end="url(#gantt-arrow${bad?'-bad':''})"/>`);}
 const todayX=(dayNumber(today)-rangeStart)*cell;
 const html=`<div class="gantt-canvas" style="width:${width+labelWidth}px;--gantt-label-width:${labelWidth}px;--timeline-width:${width}px;--day-width:${cell}px"><div class="gantt-header"><div class="gantt-label">项目 / 任务</div><div class="gantt-dates" style="width:${width}px">${header}</div></div>${rows}<svg class="gantt-dependencies" style="left:${labelWidth}px;width:${width}px;height:${y}px" viewBox="0 0 ${width} ${y}" aria-hidden="true"><defs><marker id="gantt-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7" fill="#91a6ad"/></marker><marker id="gantt-arrow-bad" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7" fill="#ba775d"/></marker></defs>${connectors.join('')}</svg>${todayX>=0&&todayX<width?`<div class="gantt-today-line" style="left:${todayX+labelWidth}px;top:54px;height:${y-54}px"><span>今天</span></div>`:''}</div>`;
 const viewport=$('#gantt-chart'),scroll=viewport.scrollLeft;viewport.innerHTML=html;viewport.scrollLeft=scroll;
 $('#gantt-warning').hidden=!warnings.length;$('#gantt-warning').textContent=warnings.length?`${warnings.length} 项前置日期冲突：${warnings.slice(0,3).join('；')}${warnings.length>3?'…':''}。请检查日期或依赖；原安排已保留。`:'';
 $$('[data-gantt-edit]').forEach(b=>b.onclick=()=>taskEditor(b.dataset.ganttEdit));
 $$('[data-gantt-locate]').forEach(b=>b.onclick=()=>{ganttStart=shiftDate(taskStart(taskBy(b.dataset.ganttLocate)),-3);viewport.scrollLeft=0;renderGantt();});
 $$('[data-gantt-task]').forEach(b=>{
  b.onclick=()=>{if(ganttSuppressClick){ganttSuppressClick=false;return;}taskEditor(b.dataset.ganttTask);};
  b.onpointerdown=e=>{
   if(e.button!==0||taskBusy)return;
   const t=taskBy(b.dataset.ganttTask);ganttDrag={id:t.id,element:b,x:e.clientX,delta:0,start:taskStart(t),end:t.date,mode:e.target.dataset.resize||'move',cell,moved:false};b.setPointerCapture(e.pointerId);
  };
  b.onpointermove=e=>{
   if(!ganttDrag||ganttDrag.element!==b)return;const d=ganttDrag;d.delta=Math.round((e.clientX-d.x)/d.cell);if(Math.abs(e.clientX-d.x)>5)d.moved=true;
   if(d.moved){b.classList.add('dragging');b.style.transform=`translateX(${d.delta*d.cell}px)`;b.title=(d.mode==='end'?d.start:shiftDate(d.start,d.delta))+' → '+(d.mode==='start'?d.end:shiftDate(d.end,d.delta));}
  };
  b.onpointercancel=()=>{ganttDrag=null;renderGantt();};
  b.onpointerup=async()=>{
   const d=ganttDrag;if(!d||d.element!==b)return;ganttDrag=null;
   if(!d.moved){b.classList.remove('dragging');return;}ganttSuppressClick=true;setTimeout(()=>ganttSuppressClick=false,250);
   if(!d.delta){renderGantt();return;}
   const start=d.mode==='end'?d.start:shiftDate(d.start,d.delta),end=d.mode==='start'?d.end:shiftDate(d.end,d.delta);
   if(start>end){toast('截止日期不能早于开始日期');renderGantt();return;}
   const ok=await mutateTask(d.id,{start_date:start,date:end});if(ok)toast(`已改期：${start} → ${end}`);else renderGantt();
  };
 });
}
$('#gantt-zoom').onchange=e=>{ganttZoom=e.target.value;renderGantt();};
$('#gantt-show-done').onchange=e=>{ganttShowDone=e.target.checked;renderGantt();};
$('#gantt-today').onclick=()=>{ganttStart=shiftDate(localDate(new Date()),-ganttTodayLookback());$('#gantt-chart').scrollLeft=0;renderGantt();};
$('#gantt-add').onclick=()=>taskEditor();
