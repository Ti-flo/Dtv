"""
Gabarit HTML du rapport DTV (séparé de report.py pour la lisibilité).

`HTML_TEMPLATE` est une page complète et autonome. Le marqueur
`/*__DTV_DATA__*/` est remplacé par le JSON des données au moment du rendu
(voir report.render_html). Aucune dépendance externe : CSS + JS inline, graphe
SVG maison. Ouvrable hors-ligne par double-clic.
"""

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DTV — Rapport</title>
<style>
  :root {
    --bg:#0d1117; --panel:#161b22; --panel2:#1c2430; --border:#30363d;
    --text:#e6edf3; --muted:#8b949e; --accent:#2f81f7; --accent2:#3fb950;
    --warn:#d29922; --bad:#f85149; --grid:#21262d;
  }
  * { box-sizing:border-box; }
  body {
    margin:0; background:var(--bg); color:var(--text);
    font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  }
  header {
    padding:18px 24px; border-bottom:1px solid var(--border);
    display:flex; align-items:baseline; gap:16px; flex-wrap:wrap;
    background:linear-gradient(180deg,#11161d,#0d1117);
  }
  header h1 { margin:0; font-size:20px; letter-spacing:.5px; }
  header h1 .tv { color:var(--accent); }
  header .meta { color:var(--muted); font-size:12px; }
  .kpis { display:flex; gap:10px; flex-wrap:wrap; padding:14px 24px; }
  .kpi {
    background:var(--panel); border:1px solid var(--border); border-radius:8px;
    padding:8px 14px; min-width:120px;
  }
  .kpi .v { font-size:18px; font-weight:600; }
  .kpi .l { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.5px; }
  nav.tabs { display:flex; gap:4px; padding:0 24px; border-bottom:1px solid var(--border); flex-wrap:wrap; }
  nav.tabs button {
    background:none; border:none; color:var(--muted); padding:11px 16px;
    font-size:14px; cursor:pointer; border-bottom:2px solid transparent;
  }
  nav.tabs button:hover { color:var(--text); }
  nav.tabs button.active { color:var(--text); border-bottom-color:var(--accent); font-weight:600; }
  main { padding:18px 24px 60px; }
  .tab { display:none; }
  .tab.active { display:block; }
  .controls { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:14px; }
  input[type=search], select {
    background:var(--panel); border:1px solid var(--border); color:var(--text);
    border-radius:6px; padding:7px 10px; font-size:13px;
  }
  input[type=search] { min-width:240px; }
  .controls .count { color:var(--muted); font-size:12px; }
  .layout { display:grid; grid-template-columns:1fr; gap:18px; }
  @media(min-width:1100px){ .layout.with-detail { grid-template-columns:minmax(0,1.4fr) minmax(0,1fr); } }
  .tablewrap { overflow:auto; border:1px solid var(--border); border-radius:8px; max-height:70vh; }
  table { border-collapse:collapse; width:100%; font-size:13px; }
  thead th {
    position:sticky; top:0; background:var(--panel2); text-align:right;
    padding:8px 10px; border-bottom:1px solid var(--border); cursor:pointer;
    white-space:nowrap; user-select:none;
  }
  thead th:first-child, tbody td:first-child { text-align:left; }
  thead th.name, tbody td.name { text-align:left; }
  thead th .arrow { color:var(--accent); font-size:10px; }
  tbody td { padding:7px 10px; border-bottom:1px solid var(--grid); text-align:right; white-space:nowrap; }
  tbody tr { cursor:pointer; }
  tbody tr:hover { background:var(--panel); }
  tbody tr.sel { background:#1f6feb22; outline:1px solid var(--accent); }
  td.name { max-width:260px; overflow:hidden; text-overflow:ellipsis; }
  .muted { color:var(--muted); }
  .spark { display:block; }
  .detail {
    background:var(--panel); border:1px solid var(--border); border-radius:8px;
    padding:16px; position:sticky; top:12px; align-self:start;
  }
  .detail h3 { margin:0 0 2px; font-size:16px; }
  .detail .sub { color:var(--muted); font-size:12px; margin-bottom:12px; }
  .statgrid { display:flex; gap:10px; flex-wrap:wrap; margin:12px 0; }
  .stat { background:var(--panel2); border:1px solid var(--border); border-radius:6px; padding:6px 12px; }
  .stat .v { font-weight:600; } .stat .l { color:var(--muted); font-size:11px; }
  .legend { display:flex; gap:14px; flex-wrap:wrap; margin-top:10px; font-size:12px; }
  .legend label { display:flex; align-items:center; gap:6px; cursor:pointer; color:var(--muted); }
  .legend label.on { color:var(--text); }
  .legend .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
  .empty { color:var(--muted); padding:40px; text-align:center; border:1px dashed var(--border); border-radius:8px; }
  .soon { color:var(--muted); padding:60px 24px; text-align:center; }
  .soon .big { font-size:40px; opacity:.4; }
  svg text { fill:var(--muted); font-size:10px; }
  .chart-tip {
    position:absolute; pointer-events:none; background:#000c; border:1px solid var(--border);
    border-radius:5px; padding:5px 8px; font-size:11px; color:var(--text); white-space:nowrap; display:none;
  }
  code { background:var(--panel2); padding:1px 5px; border-radius:4px; }
</style>
</head>
<body>
<header>
  <h1>DTV <span class="tv">TradingView</span></h1>
  <span class="meta" id="hdr-meta"></span>
</header>
<div class="kpis" id="kpis"></div>
<nav class="tabs" id="tabs"></nav>
<main>
  <section class="tab active" data-tab="prix">
    <div class="controls">
      <input type="search" id="q" placeholder="Filtrer par nom ou GID…" autocomplete="off">
      <label class="muted">Source&nbsp;
        <select id="source">
          <option value="avg">Prix moyen (marché)</option>
          <option value="x1">HDV x1</option>
          <option value="x10">HDV x10</option>
          <option value="x100">HDV x100</option>
          <option value="x1000">HDV x1000</option>
        </select>
      </label>
      <span class="count" id="count"></span>
    </div>
    <div class="layout with-detail">
      <div class="tablewrap">
        <table id="tbl">
          <thead><tr id="head"></tr></thead>
          <tbody id="rows"></tbody>
        </table>
      </div>
      <div id="detail" class="detail"><div class="empty">Sélectionne un item pour voir le graphe.</div></div>
    </div>
  </section>
  <section class="tab" data-tab="achats"><div class="soon"><div class="big">🛒</div><p>Onglet « Ressources achetées » — à venir (dépend de <code>transactions_observations.csv</code>).</p></div></section>
  <section class="tab" data-tab="craft"><div class="soon"><div class="big">⚒️</div><p>Onglet « Craft &amp; Brisage » — à venir.</p></div></section>
  <section class="tab" data-tab="affaires"><div class="soon"><div class="big">💎</div><p>Onglet « Bonnes affaires du moment » — à venir.</p></div></section>
</main>
<div class="chart-tip" id="tip"></div>

<script id="dtv-data" type="application/json">/*__DTV_DATA__*/</script>
<script>
"use strict";
const DTV = JSON.parse(document.getElementById("dtv-data").textContent);

// ── Helpers ────────────────────────────────────────────────────────────────
const fmt = n => (n==null || isNaN(n)) ? "—"
  : Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
const pct = n => (n==null||isNaN(n)) ? "" : (n>=0?"+":"") + n.toFixed(1) + "%";
const TIER_COLORS = { avg:"#2f81f7", x1:"#3fb950", x10:"#d29922", x100:"#a371f7", x1000:"#f85149" };
const TIER_LABEL  = { avg:"Prix moyen", x1:"HDV x1", x10:"HDV x10", x100:"HDV x100", x1000:"HDV x1000" };
const HDV_IDX = { x1:1, x10:2, x100:3, x1000:4 };  // index dans la ligne hdv [ts,x1,x10,x100,x1000,nb]

// Renvoie la série [[ts,price],...] d'un item pour une source donnée (filtre 0/null).
function seriesOf(item, source){
  if(source==="avg") return item.avg.filter(p=>p[1]!=null);
  const i = HDV_IDX[source];
  return item.hdv.map(r=>[r[0], r[i]]).filter(p=>p[1]!=null && p[1]>0);
}
function statsOf(s){
  if(!s.length) return null;
  const v = s.map(p=>p[1]);
  return { min:Math.min(...v), max:Math.max(...v), avg:v.reduce((a,b)=>a+b,0)/v.length,
           last:v[v.length-1], n:v.length, first:v[0] };
}

// ── Header / KPIs / Tabs ───────────────────────────────────────────────────
document.getElementById("hdr-meta").textContent =
  "généré le " + DTV.generated_at.replace("T"," ") + "  ·  " + DTV.db_path;
(function(){
  const s = DTV.stats||{};
  const k = [
    ["Items suivis", fmt(s.avg_items)],
    ["Snapshots marché", fmt(s.avg_snapshots)],
    ["Relevés HDV", fmt(s.hdv_rows)],
    ["Brisages observés", fmt(s.brisage_rows)],
    ["Période", (s.first_ts||"—").slice(0,10) + " → " + (s.last_ts||"—").slice(0,10)],
  ];
  document.getElementById("kpis").innerHTML =
    k.map(([l,v])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
})();
const TABS = [["prix","📈 Prix dans le temps"],["achats","🛒 Ressources achetées"],
              ["craft","⚒️ Craft & Brisage"],["affaires","💎 Bonnes affaires"]];
document.getElementById("tabs").innerHTML =
  TABS.map(([id,l],i)=>`<button data-go="${id}"${i===0?' class="active"':''}>${l}</button>`).join("");
document.getElementById("tabs").addEventListener("click", e=>{
  const b = e.target.closest("button"); if(!b) return;
  const id = b.dataset.go;
  document.querySelectorAll("nav.tabs button").forEach(x=>x.classList.toggle("active", x===b));
  document.querySelectorAll(".tab").forEach(s=>s.classList.toggle("active", s.dataset.tab===id));
});

// ── Onglet « Prix dans le temps » ──────────────────────────────────────────
const COLS = [
  {k:"nom",   l:"Nom",    cls:"name", get:r=>r.nom, fmt:r=>r.nom},
  {k:"gid",   l:"GID",    get:r=>r.gid, fmt:r=>r.gid},
  {k:"last",  l:"Dernier",get:r=>r.st?r.st.last:null, fmt:r=>fmt(r.st&&r.st.last)},
  {k:"min",   l:"Min",    get:r=>r.st?r.st.min:null,  fmt:r=>fmt(r.st&&r.st.min)},
  {k:"max",   l:"Max",    get:r=>r.st?r.st.max:null,  fmt:r=>fmt(r.st&&r.st.max)},
  {k:"avg",   l:"Moyen",  get:r=>r.st?r.st.avg:null,  fmt:r=>fmt(r.st&&r.st.avg)},
  {k:"var",   l:"Var",    get:r=>r.varpct, fmt:r=>`<span style="color:${r.varpct>=0?'var(--accent2)':'var(--bad)'}">${pct(r.varpct)}</span>`},
  {k:"n",     l:"#pts",   get:r=>r.st?r.st.n:0, fmt:r=>r.st?r.st.n:0},
  {k:"spark", l:"Tendance", get:r=>0, fmt:r=>sparkline(r.s), sort:false},
];
let SOURCE="avg", SORT={k:"last",dir:-1}, FILTER="", SELECTED=null;

function computeRows(){
  const q = FILTER.trim().toLowerCase();
  let rows = DTV.items.map(it=>{
    const s = seriesOf(it, SOURCE);
    const st = statsOf(s);
    const varpct = st && st.first ? (st.last-st.first)/st.first*100 : null;
    return {gid:it.gid, nom:it.nom, item:it, s, st, varpct};
  }).filter(r=>r.st);   // n'affiche que les items qui ont des données pour cette source
  if(q) rows = rows.filter(r=>r.nom.toLowerCase().includes(q) || String(r.gid).includes(q));
  const col = COLS.find(c=>c.k===SORT.k) || COLS[2];
  rows.sort((a,b)=>{
    let va=col.get(a), vb=col.get(b);
    if(typeof va==="string"){ va=va.toLowerCase(); vb=vb.toLowerCase(); return va<vb?-SORT.dir:va>vb?SORT.dir:0; }
    va=va==null?-Infinity:va; vb=vb==null?-Infinity:vb;
    return (va-vb)*SORT.dir;
  });
  return rows;
}
function renderHead(){
  document.getElementById("head").innerHTML = COLS.map(c=>{
    const arr = SORT.k===c.k ? `<span class="arrow">${SORT.dir<0?"▼":"▲"}</span>` : "";
    return `<th class="${c.cls||''}" data-k="${c.k}" data-sort="${c.sort!==false}">${c.l} ${arr}</th>`;
  }).join("");
}
function renderRows(){
  const rows = computeRows();
  document.getElementById("count").textContent = rows.length + " items";
  const body = rows.slice(0, 600).map(r=>{
    const sel = SELECTED===r.gid ? ' class="sel"' : '';
    return `<tr data-gid="${r.gid}"${sel}>` +
      COLS.map(c=>`<td class="${c.cls||''}">${c.fmt(r)}</td>`).join("") + `</tr>`;
  }).join("");
  document.getElementById("rows").innerHTML = body ||
    `<tr><td colspan="${COLS.length}"><div class="empty">Aucun item — lance d'abord <code>dtv ingest</code>.</div></td></tr>`;
  if(rows.length>600) document.getElementById("count").textContent += " (600 affichés)";
}

// Mini sparkline SVG (40×16) de la série sélectionnée.
function sparkline(s){
  if(!s || s.length<2) return '<span class="muted">—</span>';
  const v=s.map(p=>p[1]), mn=Math.min(...v), mx=Math.max(...v), W=46,H=16,r=mx-mn||1;
  const pts=v.map((y,i)=>`${(i/(v.length-1)*W).toFixed(1)},${(H-(y-mn)/r*H).toFixed(1)}`).join(" ");
  const up=v[v.length-1]>=v[0];
  return `<svg class="spark" width="${W}" height="${H}"><polyline fill="none" stroke="${up?'var(--accent2)':'var(--bad)'}" stroke-width="1.5" points="${pts}"/></svg>`;
}

// ── Graphe détaillé (SVG maison) ───────────────────────────────────────────
let DETAIL_ON = {avg:true, x1:true, x10:false, x100:false, x1000:false};
function showDetail(gid){
  SELECTED = gid;
  const it = DTV.items.find(i=>i.gid===gid);
  if(!it){ return; }
  const avail = {};
  ["avg","x1","x10","x100","x1000"].forEach(src=>{ avail[src]=seriesOf(it,src).length>=1; });
  const cur = seriesOf(it, SOURCE.length?SOURCE:"avg");
  const st = statsOf(seriesOf(it, "avg")) || statsOf(cur);
  const d = document.getElementById("detail");
  d.innerHTML =
    `<h3>${it.nom}</h3><div class="sub">GID ${it.gid}</div>` +
    statBlock(it) +
    `<div id="chart"></div>` +
    `<div class="legend" id="legend"></div>`;
  drawLegend(it, avail);
  drawChart(it);
  document.querySelectorAll("#rows tr").forEach(tr=>tr.classList.toggle("sel", +tr.dataset.gid===gid));
}
function statBlock(it){
  const blocks = ["avg","x1","x10","x100","x1000"].map(src=>{
    const st = statsOf(seriesOf(it,src)); if(!st) return "";
    return `<div class="stat"><div class="v" style="color:${TIER_COLORS[src]}">${fmt(st.last)}</div>`+
           `<div class="l">${TIER_LABEL[src]} · min ${fmt(st.min)} / max ${fmt(st.max)} / moy ${fmt(st.avg)}</div></div>`;
  }).join("");
  return `<div class="statgrid">${blocks||'<span class="muted">aucune donnée</span>'}</div>`;
}
function drawLegend(it, avail){
  const lg = document.getElementById("legend");
  lg.innerHTML = ["avg","x1","x10","x100","x1000"].filter(s=>avail[s]).map(src=>
    `<label class="${DETAIL_ON[src]?'on':''}" data-src="${src}"><span class="dot" style="background:${TIER_COLORS[src]}"></span>${TIER_LABEL[src]}</label>`
  ).join("");
  lg.querySelectorAll("label").forEach(l=>l.onclick=()=>{
    const s=l.dataset.src; DETAIL_ON[s]=!DETAIL_ON[s];
    l.classList.toggle("on", DETAIL_ON[s]); drawChart(it);
  });
}
function drawChart(it){
  const host = document.getElementById("chart");
  const sources = ["avg","x1","x10","x100","x1000"].filter(s=>DETAIL_ON[s]);
  const series = sources.map(src=>({src, color:TIER_COLORS[src], pts:seriesOf(it,src)
    .map(p=>[Date.parse(p[0]), p[1]]).filter(p=>!isNaN(p[0]))})).filter(s=>s.pts.length>0);
  if(!series.length){ host.innerHTML = '<div class="empty">Aucune série sélectionnée.</div>'; return; }
  const W=Math.max(host.clientWidth||520,320), H=240, P={l:54,r:12,t:12,b:24};
  let xs=[], ys=[];
  series.forEach(s=>s.pts.forEach(p=>{xs.push(p[0]); ys.push(p[1]);}));
  let x0=Math.min(...xs), x1=Math.max(...xs), y0=Math.min(...ys), y1=Math.max(...ys);
  if(x1===x0){ x0-=1; x1+=1; } if(y1===y0){ y0=y0*0.9||0; y1=y1*1.1||1; }
  // échelle Y serrée sur [min,max] réels (pas d'ancrage à 0) pour lire les variations
  const sx=v=>P.l+(v-x0)/(x1-x0)*(W-P.l-P.r);
  const sy=v=>H-P.b-(v-y0)/(y1-y0)*(H-P.t-P.b);
  // grille + axes Y (4 paliers)
  let grid="", ny=4;
  for(let i=0;i<=ny;i++){ const val=y0+(y1-y0)*i/ny, y=sy(val);
    grid+=`<line x1="${P.l}" y1="${y.toFixed(1)}" x2="${W-P.r}" y2="${y.toFixed(1)}" stroke="var(--grid)"/>`;
    grid+=`<text x="${P.l-6}" y="${(y+3).toFixed(1)}" text-anchor="end">${fmt(val)}</text>`;
  }
  // axes X (début, milieu, fin)
  [0,0.5,1].forEach(f=>{ const t=x0+(x1-x0)*f, x=sx(t);
    grid+=`<text x="${x.toFixed(1)}" y="${H-8}" text-anchor="${f===0?'start':f===1?'end':'middle'}">${new Date(t).toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'})}</text>`;
  });
  const paths = series.map(s=>{
    const dots = s.pts.map(p=>`<circle cx="${sx(p[0]).toFixed(1)}" cy="${sy(p[1]).toFixed(1)}" r="2.5" fill="${s.color}" data-v="${p[1]}" data-t="${p[0]}"/>`).join("");
    const line = s.pts.length>1 ? `<polyline fill="none" stroke="${s.color}" stroke-width="1.8" points="${s.pts.map(p=>`${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(" ")}"/>` : "";
    return line+dots;
  }).join("");
  host.innerHTML = `<svg width="100%" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="overflow:visible">${grid}${paths}</svg>`;
  // tooltip
  const tip=document.getElementById("tip");
  host.querySelectorAll("circle").forEach(c=>{
    c.addEventListener("mousemove",e=>{
      tip.style.display="block"; tip.style.left=(e.pageX+12)+"px"; tip.style.top=(e.pageY-10)+"px";
      const t=new Date(+c.dataset.t).toLocaleString('fr-FR');
      tip.innerHTML=`<b>${fmt(+c.dataset.v)}</b> kamas<br><span class="muted">${t}</span>`;
    });
    c.addEventListener("mouseleave",()=>tip.style.display="none");
  });
}

// ── Évènements ─────────────────────────────────────────────────────────────
document.getElementById("q").addEventListener("input", e=>{ FILTER=e.target.value; renderRows(); });
document.getElementById("source").addEventListener("change", e=>{ SOURCE=e.target.value; renderRows(); });
document.getElementById("head").addEventListener("click", e=>{
  const th=e.target.closest("th"); if(!th || th.dataset.sort==="false") return;
  const k=th.dataset.k;
  if(SORT.k===k) SORT.dir*=-1; else SORT={k, dir: k==="nom"?1:-1};
  renderHead(); renderRows();
});
document.getElementById("rows").addEventListener("click", e=>{
  const tr=e.target.closest("tr"); if(!tr || !tr.dataset.gid) return;
  showDetail(+tr.dataset.gid);
});

// ── Boot ───────────────────────────────────────────────────────────────────
renderHead(); renderRows();
if(DTV.items.length){
  // sélectionne l'item le plus « cher » par défaut pour montrer un graphe d'emblée
  const first = computeRows()[0];
  if(first) showDetail(first.gid);
}
</script>
</body>
</html>
"""
