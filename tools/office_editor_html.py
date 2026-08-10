#!/usr/bin/env python3
"""Self-contained human editor UI for Office documents.

This HTML is served by ``tools/office_preview_server.py`` at ``GET /editor``.
It talks to the editor_sdk exclusively through the same-origin ``/api/mcp``
proxy, so a human can manually type / edit / save Word, Excel and PowerPoint
documents without the Tencent-Docs cloud viewer (which is read-only when the
bare SDK is used directly).

The content is intentionally a single static string so the feature works even
if the on-disk copy is absent.

Notes on the editor model (verified against editor_sdk 0.0.0.286):
  * Word paragraphs are read via ``doc_resolve_document_structure`` with
    ``mode=full``. The SDK caps ``text_preview_length`` at 200 chars per node,
    so paragraphs whose preview hits that cap are treated as append-only
    (a full rewrite would silently drop the truncated tail).
  * Paragraph edits are applied last→first via ``doc_find`` (which returns the
    *current* range) + ``doc_replace_text``, so earlier paragraphs' coordinates
    stay valid. Empty paragraphs are filled with ``doc_insert_text``.
  * ``save_file`` writes the open editor back to ``file_path`` from the URL.
"""

EDITOR_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Office 人工编辑器</title>
<style>
  :root{
    --bg:#f5f6f8; --panel:#ffffff; --ink:#1f2329; --muted:#6b7280;
    --line:#e3e6eb; --accent:#2563eb; --accent2:#16a34a; --danger:#dc2626;
    --code:#0f172a;
  }
  *{box-sizing:border-box}
  body{margin:0;font:14px/1.5 -apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
       background:var(--bg);color:var(--ink)}
  header{padding:14px 20px;background:var(--panel);border-bottom:1px solid var(--line);
         display:flex;align-items:center;gap:14px;flex-wrap:wrap}
  header h1{font-size:16px;margin:0}
  .pill{font-size:12px;color:var(--muted);background:#eef2f7;padding:3px 9px;border-radius:999px}
  .pill b{color:var(--ink)}
  main{padding:18px 20px;max-width:1100px;margin:0 auto}
  .bar{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0;align-items:center}
  button{font:inherit;cursor:pointer;border:1px solid var(--line);background:#fff;color:var(--ink);
         padding:7px 14px;border-radius:8px;transition:.15s}
  button:hover{border-color:var(--accent);color:var(--accent)}
  button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
  button.primary:hover{filter:brightness(1.05);color:#fff}
  button.good{background:var(--accent2);border-color:var(--accent2);color:#fff}
  button.good:hover{filter:brightness(1.05);color:#fff}
  textarea,input[type=text],input[type=number]{font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
         border:1px solid var(--line);border-radius:8px;padding:8px;width:100%;background:#fff;color:var(--code)}
  textarea{resize:vertical;min-height:60px}
  textarea.truncated{background:#fafafa;color:var(--muted)}
  .grid{display:grid;gap:8px}
  table{border-collapse:collapse;width:100%;background:#fff}
  td,th{border:1px solid var(--line);padding:0}
  td input{border:0;width:100%;padding:6px;border-radius:0;font:13px ui-monospace,monospace}
  td input:focus{outline:2px solid var(--accent);outline-offset:-2px}
  .status{font-size:13px;color:var(--muted);min-height:20px}
  .status.ok{color:var(--accent2)} .status.err{color:var(--danger)}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px}
  .card h2{font-size:14px;margin:0 0 10px}
  .hint{font-size:12px;color:var(--muted);margin:6px 0}
  .para{border:1px solid var(--line);border-radius:8px;padding:8px;margin-bottom:8px;background:#fff}
  .para .idx{font-size:11px;color:var(--muted);margin-bottom:4px}
  .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .row > *{flex:0 0 auto}
  .grow{flex:1 1 auto}
  .tag{font-size:11px;background:#eef2f7;color:var(--muted);padding:2px 7px;border-radius:6px}
  .hidden{display:none}
</style>
</head>
<body>
<header>
  <h1>Office 人工编辑器</h1>
  <span class="pill">类型 <b id="dt"></b></span>
  <span class="pill">file_id <b id="fid" style="max-width:280px;overflow:hidden;text-overflow:ellipsis;display:inline-block;vertical-align:bottom"></b></span>
  <span class="pill" id="conn">连接中…</span>
</header>
<main>
  <div class="card">
    <div class="bar">
      <button class="good" onclick="saveAll()">保存文档</button>
      <span class="status" id="globalStatus"></span>
    </div>
    <div class="hint">修改都在内存中的编辑器实例里；点“保存文档”应用修改并写回磁盘。</div>
  </div>

  <!-- ===================== DOC ===================== -->
  <section id="docPanel" class="card hidden">
    <h2>Word 文档 — 人工编辑</h2>
    <div class="bar">
      <button class="primary" onclick="loadDoc()">重新加载</button>
      <button onclick="applyDoc()">应用段落修改</button>
    </div>
    <div class="hint">逐段修改；>200 字的长段落只读（重写会丢失截断部分），可追加新段或在对话中让 AI 编辑。</div>
    <div id="docList" class="grid"></div>

    <h2 style="margin-top:18px">追加段落</h2>
    <div class="hint">每行作为一段，附加到文档末尾。</div>
    <textarea id="docAppend" placeholder="第一行
第二行"></textarea>
    <div class="bar"><button class="primary" onclick="appendDoc()">追加为段落</button></div>
  </section>

  <!-- ===================== SHEET ===================== -->
  <section id="sheetPanel" class="card hidden">
    <h2>Excel 表格 — 人工编辑</h2>
    <div class="bar">
      <span class="tag">行</span><input type="number" id="rows" value="20" style="width:70px">
      <span class="tag">列</span><input type="number" id="cols" value="10" style="width:70px">
      <button class="primary" onclick="loadSheet()">加载表格</button>
      <button class="good" onclick="saveSheet()">保存表格</button>
    </div>
    <div class="hint">直接在单元格里打字，点“保存表格”一次性写回并落盘。</div>
    <div id="sheetWrap" style="overflow:auto"></div>
  </section>

  <!-- ===================== SLIDE ===================== -->
  <section id="slidePanel" class="card hidden">
    <h2>PPT 幻灯片 — 人工编辑</h2>
    <div class="bar"><button class="primary" onclick="loadSlide()">重新加载</button></div>
    <div class="hint">每个文本框可单独编辑，修改后点“保存文档”。</div>
    <div id="slideList" class="grid"></div>
  </section>

  <div class="status" id="log"></div>
</main>

<script>
const Q=new URLSearchParams(location.search);
const FILE_ID=Q.get('file_id')||'';
const DOC_TYPE=Q.get('doc_type')||'doc';
const FILE_PATH=Q.get('file_path')||'';
document.getElementById('dt').textContent=DOC_TYPE;
document.getElementById('fid').textContent=FILE_ID;

function showStatus(el,msg,kind){const e=document.getElementById(el);e.textContent=msg;e.className='status'+(kind?' '+kind:'');}
function log(msg){const e=document.getElementById('log');e.textContent=(e.textContent?e.textContent+'\n':'')+msg;}

// ---- MCP proxy helper (with light retry for transient "not ready" errors) ----
async function mcp(name,args,attempt){
  attempt=attempt||0;
  const body={jsonrpc:'2.0',id:1,method:'tools/call',
    params:{name, arguments:Object.assign({file_id:FILE_ID},args||{})}};
  let r,j;
  try{
    r=await fetch('/api/mcp',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)});
    j=await r.json();
  }catch(e){
    if(attempt<3){ await new Promise(s=>setTimeout(s,500)); return mcp(name,args,attempt+1); }
    throw new Error(name+' network: '+e.message);
  }
  if(j.error){
    const msg=JSON.stringify(j.error);
    // transient "No workbook open" right after create — back off and retry
    if(attempt<3 && /No workbook open|not ready|not open/i.test(msg)){
      await new Promise(s=>setTimeout(s,600)); return mcp(name,args,attempt+1);
    }
    throw new Error(name+' error: '+msg);
  }
  const txt=(j.result&&j.result.content&&j.result.content[0]&&j.result.content[0].text)||'';
  try{return txt?JSON.parse(txt):{};}catch(e){return txt;}
}

// ---- panel switching ----
const map={doc:'docPanel',sheet:'sheetPanel',slide:'slidePanel'};
if(map[DOC_TYPE]) document.getElementById(map[DOC_TYPE]).classList.remove('hidden');

// init connection + auto-load the active panel
(async()=>{
  try{ const r=await fetch('/api/health'); const ok=r.ok;
    document.getElementById('conn').textContent=ok?'已连接':'未连接';
    document.getElementById('conn').style.color=ok?'var(--accent2)':'var(--danger)';
  }catch(e){ document.getElementById('conn').textContent='未连接'; }
  if(DOC_TYPE==='doc') loadDoc();
  else if(DOC_TYPE==='sheet') loadSheet();
  else if(DOC_TYPE==='slide') loadSlide();
})();

// ===================== DOC =====================
let docParas=[]; // {start,end,origText,trunc} aligned with #docList textareas
const PREVIEW_CAP=200; // editor_sdk clamps text_preview_length to 200

async function loadDoc(){
  showStatus('globalStatus','加载中…');
  try{
    const data=await mcp('doc_resolve_document_structure',
      {mode:'full',limit:0,text_preview_length:PREVIEW_CAP});
    const nodes=(data&&data.nodes)||[];
    const box=document.getElementById('docList');box.innerHTML='';
    docParas=[];
    nodes.forEach((n,i)=>{
      if(/^table$/i.test(n.type||'')){
        const d=document.createElement('div');d.className='para';
        d.innerHTML='<div class="idx">表格 '+(n.row_count||'?')+'行 × '+(n.col_count||'?')+'列（只读，请让 AI 编辑）</div>';
        box.appendChild(d);return;
      }
      const txt=(n.text_preview!=null)?n.text_preview:'';
      const trunc=txt.length>=PREVIEW_CAP;
      const d=document.createElement('div');d.className='para';
      const lab=document.createElement('div');lab.className='idx';
      lab.textContent='#'+(i+1)+' · 段落 '+(n.paragraph_index!=null?n.paragraph_index:'')+(trunc?' · 长段落(仅显示前200字)':'');
      const ta=document.createElement('textarea');ta.value=txt;
      ta.rows=Math.max(2,Math.min(8,Math.ceil(txt.length/60)));
      if(trunc){ta.readOnly=true;ta.classList.add('truncated');}
      d.appendChild(lab);
      if(trunc){
        const h=document.createElement('div');h.className='hint';
        h.textContent='长段落无法整体重写（会丢失 200 字之后的内容），请追加段落或在对话中让 AI 编辑。';
        d.appendChild(h);
      }
      d.appendChild(ta);
      box.appendChild(d);
      docParas.push({start:n.start_index,end:n.end_index,origText:txt,trunc:trunc});
    });
    showStatus('globalStatus','已加载 '+docParas.length+' 个段落','ok');
  }catch(e){ showStatus('globalStatus',e.message,'err'); log(e.message); }
}

// Apply paragraph edits to the editor (not persisted until save_file).
// Uses doc_find (current ranges) + doc_replace_text, processing last→first so
// earlier paragraphs' coordinates stay valid; empty paragraphs use insert_text.
async function applyDoc(){
  const tas=[...document.querySelectorAll('#docList textarea')];
  const edits=[];
  tas.forEach((ta,i)=>{
    if(docParas[i].trunc) return; // read-only long paragraphs
    const oldT=docParas[i].origText, newT=ta.value;
    if(oldT===newT) return;
    edits.push({i,start:docParas[i].start,oldT,newT});
  });
  edits.sort((a,b)=>b.start-a.start); // last → first
  let done=0;
  for(const e of edits){
    try{
      if(e.oldT===''){
        await mcp('doc_insert_text',{idx:e.start,text:e.newT});
      }else{
        const f=await mcp('doc_find',{text:e.oldT});
        const locs=(f&&f.locations)||[];
        const loc=locs.find(l=>l.begin===e.start)||locs[0];
        if(!loc){log('未找到原文，跳过段落 #'+(e.i+1));continue;}
        await mcp('doc_replace_text',{text:e.newT,ranges:[{begin:loc.begin,end:loc.end}]});
      }
      done++;
    }catch(err){ log('段落修改失败 #'+(e.i+1)+': '+err.message); }
  }
  showStatus('globalStatus','已应用 '+done+' 处修改','ok');
  if(done) await loadDoc(); // coordinates shifted; refresh
}

async function appendDoc(){
  const lines=document.getElementById('docAppend').value.split('\n').map(s=>s.trimEnd()).filter(l=>l.length);
  if(!lines.length){showStatus('globalStatus','没有可追加的内容');return;}
  let n=0;
  try{
    for(const line of lines){
      const pos=await mcp('doc_get_last_operable_pos',{});
      const idx=(pos&&pos.position)||0;
      await mcp('doc_insert_paragraph_with_text',{idx:idx,text:line});
      n++;
    }
    document.getElementById('docAppend').value='';
    await loadDoc();
    showStatus('globalStatus','已追加 '+n+' 段','ok');
  }catch(e){ showStatus('globalStatus',e.message,'err'); log(e.message); }
}

// ===================== SHEET =====================
let SHEET_ID='';
async function loadSheet(){
  showStatus('globalStatus','加载中…');
  try{
    if(!SHEET_ID){
      const info=await mcp('sheet_get_sheet_info',{});
      const sheets=(info&&info.sheets)||(info&&info.sheet_list)||[];
      SHEET_ID=(sheets[0]&&(sheets[0].sheet_id||sheets[0].id))||'000001';
    }
    const R=parseInt(document.getElementById('rows').value)||20;
    const C=parseInt(document.getElementById('cols').value)||10;
    const data=await mcp('sheet_get_cell_data',{sheet_id:SHEET_ID,start_row:0,start_col:0,
      end_row:R-1,end_col:C-1,return_csv:true});
    const csv=(data&&data.csv_data)||'';
    const grid=parseCSV(csv,R,C);
    renderSheet(grid);
    showStatus('globalStatus','已加载 '+R+'×'+C+' 表格 (sheet '+SHEET_ID+')','ok');
  }catch(e){ showStatus('globalStatus',e.message,'err'); log(e.message); }
}
function parseCSV(csv,rows,cols){
  const out=[];let i=0,field='',row=[],inQ=false;
  csv=(csv||'').replace(/\r\n/g,'\n');
  while(i<csv.length){
    const c=csv[i];
    if(inQ){
      if(c==='"'){ if(csv[i+1]==='"'){field+='"';i++;} else inQ=false; }
      else field+=c;
    }else{
      if(c==='"') inQ=true;
      else if(c===','){row.push(field);field='';}
      else if(c==='\n'){row.push(field);out.push(row);row=[];field='';}
      else if(c==='\r'){}
      else field+=c;
    }
    i++;
  }
  if(field.length||row.length){row.push(field);out.push(row);}
  const grid=[];
  for(let r=0;r<rows;r++){const gr=[];for(let c=0;c<cols;c++){gr.push((out[r]&&out[r][c]!=null)?out[r][c]:'');}grid.push(gr);}
  return grid;
}
function renderSheet(grid){
  const wrap=document.getElementById('sheetWrap');
  const tbl=document.createElement('table');
  grid.forEach((gr,r)=>{
    const tr=document.createElement('tr');
    gr.forEach((v,c)=>{
      const td=document.createElement('td');
      const inp=document.createElement('input');inp.value=v;inp.dataset.r=r;inp.dataset.c=c;
      td.appendChild(inp);tr.appendChild(td);
    });
    tbl.appendChild(tr);
  });
  wrap.innerHTML='';wrap.appendChild(tbl);
}
function buildCSV(){
  const inputs=[...document.querySelectorAll('#sheetWrap input')];
  const grid={};let maxR=0,maxC=0;
  inputs.forEach(inp=>{const r=+inp.dataset.r,c=+inp.dataset.c;grid[r]=grid[r]||{};grid[r][c]=inp.value;if(r>maxR)maxR=r;if(c>maxC)maxC=c;});
  // trim trailing all-empty rows/cols so we don't inflate the used range
  while(maxR>0){let empty=true;for(let c=0;c<=maxC;c++){if(grid[maxR]&&grid[maxR][c]!==''&&grid[maxR][c]!=null){empty=false;break;}}if(!empty)break;maxR--;}
  while(maxC>0){let empty=true;for(let r=0;r<=maxR;r++){if(grid[r]&&grid[r][maxC]!==''&&grid[r][maxC]!=null){empty=false;break;}}if(!empty)break;maxC--;}
  let csv='';
  for(let r=0;r<=maxR;r++){const row=[];for(let c=0;c<=maxC;c++){let v=grid[r]&&grid[r][c]!=null?grid[r][c]:'';if(/[",\n]/.test(v))v='"'+v.replace(/"/g,'""')+'"';row.push(v);}csv+=row.join(',')+'\n';}
  return csv;
}
async function saveSheet(){
  showStatus('globalStatus','保存中…');
  try{
    const csv=buildCSV();
    await mcp('sheet_set_range_value_by_csv',{sheet_id:SHEET_ID,start_row:0,start_col:0,csv_data:csv});
    await saveFile();
    showStatus('globalStatus','表格已写回并保存','ok');
  }catch(e){ showStatus('globalStatus',e.message,'err'); log(e.message); }
}

// ===================== SLIDE =====================
async function loadSlide(){
  showStatus('globalStatus','加载中…');
  try{
    const info=await mcp('slide_get_info',{});
    const pages=(info&&info.slide_count)||0;
    const box=document.getElementById('slideList');box.innerHTML='';
    for(let p=0;p<pages;p++){
      const pinfo=await mcp('slide_get_page_info',{page_index:p});
      const shapes=(pinfo&&pinfo.shapes)||(pinfo&&pinfo.shape_list)||[];
      const card=document.createElement('div');card.className='card';card.style.marginBottom='10px';
      card.innerHTML='<div class="idx">第 '+(p+1)+' 页</div>';
      let any=false;
      shapes.forEach(sh=>{
        const txt=(sh.text!=null)?sh.text.replace(/\r$/,''):'';
        const sid=sh.shape_id||sh.id;
        if(sid==null) return;
        if(txt===''&&!(sh.type&&/text/i.test(sh.type||''))) return;
        any=true;
        const ta=document.createElement('textarea');ta.value=txt;ta.rows=2;
        ta.dataset.page=p;ta.dataset.sid=sid;ta.dataset.orig=txt;
        const lab=document.createElement('div');lab.className='idx';lab.textContent='shape '+sid;
        card.appendChild(lab);card.appendChild(ta);
      });
      if(!any) card.innerHTML+='<div class="hint">（无可编辑文本框）</div>';
      box.appendChild(card);
    }
    showStatus('globalStatus','已加载 '+pages+' 页','ok');
  }catch(e){ showStatus('globalStatus',e.message,'err'); log(e.message); }
}
async function saveSlide(){
  const tas=[...document.querySelectorAll('#slideList textarea')];
  let n=0;
  for(const ta of tas){
    if(ta.value===ta.dataset.orig) continue;
    try{ await mcp('slide_set_text',{page_index:+ta.dataset.page,shape_id:ta.dataset.sid,text:ta.value}); ta.dataset.orig=ta.value; n++; }
    catch(e){ log('幻灯片保存失败: '+e.message); }
  }
  showStatus('globalStatus','已应用 '+n+' 个文本框修改','ok');
}

// ===================== SAVE =====================
async function saveFile(){
  showStatus('globalStatus','保存文档中…');
  try{
    const args={};
    if(FILE_PATH) args.file_path=FILE_PATH;
    const r=await mcp('save_file',args);
    showStatus('globalStatus','已保存到磁盘','ok');
    log('save: '+JSON.stringify(r).slice(0,120));
  }catch(e){ showStatus('globalStatus',e.message,'err'); log(e.message); }
}

// Apply type-specific edits (if any) then persist to disk.
async function saveAll(){
  if(DOC_TYPE==='doc') await applyDoc();
  else if(DOC_TYPE==='sheet') await saveSheet();
  else if(DOC_TYPE==='slide'){ await saveSlide(); await saveFile(); }
  else await saveFile();
}
</script>
</body>
</html>
"""
