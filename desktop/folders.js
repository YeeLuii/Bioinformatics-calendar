'use strict';
// Folder presentation and organization; saves through the shared board transaction.
let folderUI={id:'',query:'',kind:'',layout:'list',selected:new Set()};
function orderedFolderCards(id,visible=false){
 const cards=(visible?visibleCards():board.cards).filter(c=>c.folder===id);
 return cards.map((card,index)=>({card,index})).sort((a,b)=>(a.card.order??Number.MAX_SAFE_INTEGER)-(b.card.order??Number.MAX_SAFE_INTEGER)||a.index-b.index).map(x=>x.card);
}
function setFolderOrder(cards){cards.forEach((c,index)=>{c.order=index;});}
async function reorderFolder(id,source,target,after=false){
 const cards=orderedFolderCards(id),from=cards.findIndex(c=>c.id===source);
 if(from<0||source===target)return;
 const [moved]=cards.splice(from,1),to=cards.findIndex(c=>c.id===target);
 if(to<0)return;
 cards.splice(to+(after?1:0),0,moved);
 if(await changeBoard(()=>setFolderOrder(cards)))toast('顺序已保存');
}
function folderView(id){
 const folder=cardBy(id);if(!folder||folder.type!=='folder')return;activeFolder=id;
 const all=orderedFolderCards(id),visible=orderedFolderCards(id,true);
 if(folderUI.id!==id)folderUI={id,query:'',kind:'',layout:visible.length>12?'list':'grid',selected:new Set()};
 folderUI.selected=new Set([...folderUI.selected].filter(key=>visible.some(c=>c.id===key)));
 drawer(`<h2>▰ ${esc(folder.title)}</h2><p class="form-note">${visible.length} 张卡片。排序自动保存；可在“修改记录”撤销。</p>
 <div class="actions"><button class="button secondary" id="folder-edit">重命名 / 安排</button><button class="button secondary" id="folder-add">添加会话快捷方式</button></div>
 <div class="folder-toolbar"><input id="folder-search" type="search" placeholder="查找此文件夹" aria-label="查找此文件夹" value="${esc(folderUI.query)}"><select id="folder-kind" aria-label="筛选卡片类型"><option value="">全部类型</option>${['project','thread','directory'].map(k=>`<option value="${k}" ${folderUI.kind===k?'selected':''}>${typeNames[k]}</option>`).join('')}</select><button class="button secondary" id="folder-layout">${folderUI.layout==='list'?'卡片视图':'列表视图'}</button></div>
 <div class="actions folder-sort"><button class="button secondary" id="folder-sort-name">按名称整理</button><button class="button secondary" id="folder-sort-kind">按类型整理</button></div>
 <p class="form-note" id="folder-order-help"></p>
 <div class="folder-bulk"><label><input type="checkbox" id="folder-select-all"> 选择当前显示</label><span id="folder-selected" aria-live="polite"></span><select id="folder-destination" aria-label="移到哪个文件夹"><option value="">待安排</option>${board.cards.filter(c=>c.type==='folder'&&c.id!==id).map(c=>`<option value="${esc(c.id)}">${esc(c.title)}</option>`).join('')}<option value="__new">新建桌面文件夹…</option></select><input id="folder-new-name" hidden maxlength="12000" placeholder="新文件夹名称" aria-label="新文件夹名称"><button class="button secondary" id="folder-move">移入</button></div>
 <div id="folder-items"></div>`);
 const filtered=()=>!!(folderUI.query.trim()||folderUI.kind);
 function updateSelection(){
  const checks=[...$('#folder-items').querySelectorAll('[data-folder-select]')];
  checks.forEach(c=>{c.checked=folderUI.selected.has(c.dataset.folderSelect);});
  const count=checks.filter(c=>c.checked).length,select=$('#folder-select-all');
  select.checked=checks.length>0&&count===checks.length;select.indeterminate=count>0&&count<checks.length;
  $('#folder-selected').textContent=`已选 ${folderUI.selected.size} 项`;
  $('#folder-move').disabled=!folderUI.selected.size||boardBusy;
 }
 function renderItems(){
  const cs=visible.filter(c=>(!folderUI.kind||c.type===folderUI.kind)&&(!folderUI.query.trim()||(c.title+' '+c.target).toLocaleLowerCase().includes(folderUI.query.trim().toLocaleLowerCase())));
  const locked=filtered();
  $('#folder-order-help').textContent=locked?'筛选时可批量移动；清除筛选后可调整完整顺序。':'拖动卡片或使用置顶、上移、下移。选中多项后可移入另一个桌面文件夹。';
  $('#folder-sort-name').disabled=locked;$('#folder-sort-kind').disabled=locked;
  const host=$('#folder-items');host.className='folder-items '+folderUI.layout;
  host.innerHTML=cs.map(c=>{const index=all.findIndex(x=>x.id===c.id);return `<article class="folder-item" draggable="${!locked}" data-folder-card="${esc(c.id)}"><div class="folder-item-main"><input type="checkbox" data-folder-select="${esc(c.id)}" aria-label="选择 ${esc(c.title)}"><button class="folder-open" data-card-go="${esc(c.id)}" title="${esc(c.title)}"><span>${typeIcons[c.type]}</span><span class="folder-item-title">${esc(c.title)}<small>${typeNames[c.type]}</small></span></button><button class="text-button" data-card-edit="${esc(c.id)}" aria-label="安排 ${esc(c.title)}">···</button></div><div class="folder-order-actions"><button data-order="top" ${locked||index===0?'disabled':''} aria-label="置顶 ${esc(c.title)}">置顶</button><button data-order="up" ${locked||index===0?'disabled':''} aria-label="上移 ${esc(c.title)}">↑ 上移</button><button data-order="down" ${locked||index===all.length-1?'disabled':''} aria-label="下移 ${esc(c.title)}">↓ 下移</button></div></article>`;}).join('')||'<p class="board-empty">没有匹配的卡片。可以清除筛选，或把桌面卡片收进此文件夹。</p>';
  wireCards(host);
  host.querySelectorAll('[data-folder-select]').forEach(el=>el.onchange=()=>{if(el.checked)folderUI.selected.add(el.dataset.folderSelect);else folderUI.selected.delete(el.dataset.folderSelect);updateSelection();});
  host.querySelectorAll('[data-folder-card]').forEach(el=>{
   const key=el.dataset.folderCard,index=all.findIndex(c=>c.id===key);
   el.querySelectorAll('[data-order]').forEach(b=>b.onclick=()=>reorderFolder(id,key,all[b.dataset.order==='top'?0:b.dataset.order==='up'?index-1:index+1]?.id,b.dataset.order==='down'));
   el.ondragstart=e=>{if(locked){e.preventDefault();return;}e.dataTransfer.setData('text/plain',key);e.dataTransfer.effectAllowed='move';el.classList.add('dragging');};
   el.ondragend=()=>host.querySelectorAll('.dragging,.folder-drop-before,.folder-drop-after').forEach(x=>x.classList.remove('dragging','folder-drop-before','folder-drop-after'));
   const isAfter=e=>{const r=el.getBoundingClientRect();return folderUI.layout==='list'?e.clientY>r.top+r.height/2:e.clientX>r.left+r.width/2;};
   el.ondragover=e=>{if(locked)return;e.preventDefault();e.stopPropagation();el.classList.toggle('folder-drop-after',isAfter(e));el.classList.toggle('folder-drop-before',!isAfter(e));};
   el.ondragleave=()=>el.classList.remove('folder-drop-before','folder-drop-after');
   el.ondrop=e=>{e.preventDefault();e.stopPropagation();el.classList.remove('folder-drop-before','folder-drop-after');if(!locked)reorderFolder(id,e.dataTransfer.getData('text/plain'),key,isAfter(e));};
  });
  updateSelection();
 }
 $('#folder-search').oninput=e=>{folderUI.query=e.target.value;folderUI.selected.clear();renderItems();};
 $('#folder-kind').onchange=e=>{folderUI.kind=e.target.value;folderUI.selected.clear();renderItems();};
 $('#folder-layout').onclick=()=>{folderUI.layout=folderUI.layout==='list'?'grid':'list';folderView(id);};
 $('#folder-select-all').onchange=e=>{folderUI.selected.clear();if(e.target.checked)$('#folder-items').querySelectorAll('[data-folder-select]').forEach(x=>folderUI.selected.add(x.dataset.folderSelect));updateSelection();};
 $('#folder-sort-name').onclick=()=>changeBoard(()=>setFolderOrder([...all].sort((a,b)=>a.title.localeCompare(b.title,'zh-CN',{numeric:true}))));
 $('#folder-sort-kind').onclick=()=>changeBoard(()=>setFolderOrder([...all].sort((a,b)=>['project','thread','directory'].indexOf(a.type)-['project','thread','directory'].indexOf(b.type)||a.title.localeCompare(b.title,'zh-CN',{numeric:true}))));
 $('#folder-destination').onchange=e=>{$('#folder-new-name').hidden=e.target.value!=='__new';};
 $('#folder-move').onclick=async()=>{
  let target=$('#folder-destination').value;const title=$('#folder-new-name').value.trim(),selected=new Set(folderUI.selected);
  if(!selected.size)return;
  if(target==='__new'&&!title){toast('请填写新文件夹名称');$('#folder-new-name').focus();return;}
  const create=target==='__new';if(create)target=newId('f');
  if(await changeBoard(()=>{
   if(create)board.cards.push({id:target,title,type:'folder',target:'',folder:'',zone:'inbox',x:0,y:0});
   const moved=all.filter(c=>selected.has(c.id)),existing=target?orderedFolderCards(target):[];
   moved.forEach(c=>{c.folder=target;delete c.order;if(!target)c.zone='inbox';});
   if(target)setFolderOrder([...existing,...moved]);
  })){folderUI.selected.clear();folderView(id);toast(`已移动 ${selected.size} 张桌面卡片`);}
 };
 $('#folder-edit').onclick=()=>cardEditor(id);$('#folder-add').onclick=()=>cardEditor('','thread',id);
 renderItems();
}
