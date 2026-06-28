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
  input[type=search] { min-width:220px; }
  .controls .count { color:var(--muted); font-size:12px; }
  .controls .sep { width:1px; align-self:stretch; background:var(--border); margin:2px 2px; }
  .controls .chk { display:flex; align-items:center; gap:5px; cursor:pointer; }
  .btn {
    background:var(--panel2); border:1px solid var(--border); color:var(--text);
    border-radius:6px; padding:6px 10px; font-size:13px; cursor:pointer;
  }
  .btn:hover { border-color:var(--accent); }
  .star { cursor:pointer; color:var(--border); font-size:15px; line-height:1; }
  .star:hover { color:var(--warn); }
  .star.on { color:var(--warn); }
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
  th.name, td.name { max-width:140px; overflow:hidden; text-overflow:ellipsis; }
  thead th.type, tbody td.type { text-align:left; }
  th.type, td.type { max-width:74px; overflow:hidden; text-overflow:ellipsis; color:var(--muted); }
  th.fav, td.fav { padding-left:8px; padding-right:2px; text-align:center; cursor:default; }
  th.var, td.var, th.narrow, td.narrow { padding-left:6px; padding-right:6px; }
  td.var, td.narrow { font-variant-numeric:tabular-nums; }
  thead th.runes, tbody td.runes { text-align:left; }
  th.runes, td.runes { max-width:200px; overflow:hidden; text-overflow:ellipsis; color:var(--muted); }
  /* Colonne runes des tables brisage : prend tout l'espace restant (greedy),
     les autres colonnes se réduisent à leur contenu. */
  thead th.runesb, tbody td.runesb { text-align:left; }
  th.runesb, td.runesb { width:100%; white-space:normal; color:var(--muted); padding-left:14px; }
  .notice { background:var(--panel); border:1px solid var(--border); border-radius:8px;
            padding:10px 14px; margin-bottom:14px; font-size:13px; display:flex; gap:16px; flex-wrap:wrap; }
  .notice b { color:var(--text); }
  h3.sec { margin:22px 0 8px; font-size:15px; }
  h3.sec .muted { font-weight:400; font-size:12px; }
  .tag { display:inline-block; padding:1px 8px; border-radius:10px; font-size:11px; border:1px solid var(--border); color:var(--muted); }
  .tag.ok { color:var(--accent2); border-color:#2ea04366; }
  .tag.warn { color:var(--warn); border-color:#d2992266; }
  td.good { color:var(--accent2); } td.bad { color:var(--bad); }
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
      <label class="muted">Type&nbsp;
        <select id="typeFilter"><option value="">Tous</option></select>
      </label>
      <span class="sep"></span>
      <label class="muted">Liste&nbsp;
        <select id="listSel"></select>
      </label>
      <button class="btn" id="listNew" title="Créer une liste">+ Liste</button>
      <button class="btn" id="listDel" title="Supprimer la liste active">🗑</button>
      <label class="muted chk"><input type="checkbox" id="favOnly"> ★ favoris seulement</label>
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
  <section class="tab" data-tab="craft"><div id="craft-root"></div></section>
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
// Code couleur DofusTradingView : une HAUSSE de prix est défavorable (acheteur)
// → ROUGE quand ça monte, VERT quand ça descend.
const UP="#f85149", DOWN="#3fb950";
const trendColor = d => d>0 ? UP : d<0 ? DOWN : "var(--muted)";
const dmy = ts => { const d=new Date(ts); return isNaN(d) ? "—"
  : String(d.getDate()).padStart(2,"0")+"/"+String(d.getMonth()+1).padStart(2,"0")+"/"+String(d.getFullYear()).slice(-2); };
const TIER_COLORS = { avg:"#2f81f7", x1:"#3fb950", x10:"#d29922", x100:"#a371f7", x1000:"#e85aad" };
const TIER_LABEL  = { avg:"Prix moyen", x1:"HDV x1", x10:"HDV x10", x100:"HDV x100", x1000:"HDV x1000" };
const HDV_IDX = { x1:1, x10:2, x100:3, x1000:4 };  // index dans la ligne hdv [ts,x1,x10,x100,x1000,nb]
const TIER_DIV = { avg:1, x1:1, x10:10, x100:100, x1000:1000 };  // diviseur prix unitaire

// Renvoie la série [[ts,price],...] d'un item pour une source donnée (filtre 0/null).
function seriesOf(item, source){
  if(source==="avg") return item.avg.filter(p=>p[1]!=null);
  const i = HDV_IDX[source];
  return item.hdv.map(r=>[r[0], r[i]]).filter(p=>p[1]!=null && p[1]>0);
}
// Idem mais prix ramené à l'UNITÉ (lot /10, /100, /1000) → comparable aux x1/moyen.
function unitSeriesOf(item, source){
  const d = TIER_DIV[source]; return seriesOf(item, source).map(p=>[p[0], p[1]/d]);
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

// ── Favoris / listes de suivi (persistés en localStorage) ──────────────────
// Le rapport est un fichier statique régénéré : les listes vivent côté
// navigateur (localStorage), donc elles survivent à une régénération du HTML.
const LS_KEY="dtv_lists", LS_ACT="dtv_active_list";
function loadLists(){ try{ return JSON.parse(localStorage.getItem(LS_KEY))||{}; }catch(e){ return {}; } }
function saveLists(){ try{ localStorage.setItem(LS_KEY, JSON.stringify(LISTS)); }catch(e){} }
let LISTS = loadLists();
if(!Object.keys(LISTS).length){ LISTS = {"Favoris": []}; saveLists(); }
let ACTIVE = localStorage.getItem(LS_ACT) || Object.keys(LISTS)[0];
if(!LISTS[ACTIVE]) ACTIVE = Object.keys(LISTS)[0];
function setActive(name){ ACTIVE=name; try{ localStorage.setItem(LS_ACT, name); }catch(e){} }
function isFav(gid){ return (LISTS[ACTIVE]||[]).includes(gid); }
function toggleFav(gid){
  const arr = LISTS[ACTIVE] || (LISTS[ACTIVE]=[]);
  const i = arr.indexOf(gid);
  if(i<0) arr.push(gid); else arr.splice(i,1);
  saveLists();
}
function renderListControls(){
  const sel = document.getElementById("listSel");
  sel.innerHTML = Object.keys(LISTS).map(n=>{
    const n2 = n.replace(/"/g,"&quot;");
    return `<option value="${n2}"${n===ACTIVE?" selected":""}>${n} (${LISTS[n].length})</option>`;
  }).join("");
}

// ── Onglet « Prix dans le temps » ──────────────────────────────────────────
// Var j/s/m et Tendance sont TOUJOURS basées sur le prix moyen marché ;
// Dernier/Min/Max/Moyen suivent la source sélectionnée.
const DAY = 86400000;
// Variation % du prix moyen entre maintenant et ~N jours en arrière (null si pas
// d'historique assez ancien).
function varOver(series, days){
  if(!series || series.length<2) return null;
  const lastT = Date.parse(series[series.length-1][0]), last = series[series.length-1][1];
  const target = lastT - days*DAY;
  let past=null;
  for(let i=series.length-1;i>=0;i--){ if(Date.parse(series[i][0])<=target){ past=series[i][1]; break; } }
  if(past==null || past===0) return null;
  return (last-past)/past*100;
}
// Tronque une série à ses N derniers jours (relatif au dernier point).
function lastDays(series, days){
  if(!series || !series.length) return series||[];
  const lastT = Date.parse(series[series.length-1][0]);
  const out = series.filter(p=>Date.parse(p[0]) >= lastT - days*DAY);
  return out.length>=2 ? out : series.slice(-2);
}
// Indice de VOLUME 0–10 : fréquence de changement du prix moyen sur les 10
// derniers jours. 10 = le prix bouge à chaque relevé, 0 = il ne bouge jamais.
function volumeIndex(series){
  const s = lastDays(series, 10);
  if(!s || s.length<2) return null;
  let changes=0;
  for(let i=1;i<s.length;i++){ if(s[i][1]!==s[i-1][1]) changes++; }
  return Math.round(changes/(s.length-1)*10);
}
const varCell = v => v==null ? '<span class="muted">—</span>'
  : `<span style="color:${trendColor(v)}">${pct(v)}</span>`;
// Échelle « jolie » : pas rond (1/2/2.5/5 ×10^k) et plafond arrondi au-dessus du
// max → axe Y lisible (0-20-40-60-80 plutôt que des valeurs biscornues).
function niceStep(rough){
  const p = Math.pow(10, Math.floor(Math.log10(rough)));
  const f = rough/p;
  const nf = f<=1?1 : f<=2?2 : f<=2.5?2.5 : f<=5?5 : 10;
  return nf*p;
}
function niceScale(max, target){
  if(!(max>0)) return {top:1, step:1};
  const step = niceStep(max/(target||5));
  return {top: Math.ceil(max/step)*step, step};
}
const COLS = [
  {k:"fav",   l:"★",      cls:"fav", title:"Ajouter à la liste active", sort:false, get:r=>0,
   fmt:r=>`<span class="star ${isFav(r.gid)?'on':''}" data-fav="${r.gid}">★</span>`},
  {k:"nom",   l:"Nom",    cls:"name", get:r=>r.nom, fmt:r=>r.nom},
  {k:"type",  l:"Type",   cls:"type", title:"Type d'objet", get:r=>r.type, fmt:r=>r.type||'<span class="muted">—</span>'},
  {k:"niv",   l:"Niv",    cls:"narrow", title:"Niveau de l'objet (ordre HDV)", get:r=>r.level, fmt:r=>r.level==null?'<span class="muted">—</span>':r.level},
  {k:"last",  l:"Dernier",title:"Dernier prix (source sélectionnée)", get:r=>r.st?r.st.last:null, fmt:r=>fmt(r.st&&r.st.last)},
  {k:"min",   l:"Min",    get:r=>r.st?r.st.min:null,  fmt:r=>fmt(r.st&&r.st.min)},
  {k:"max",   l:"Max",    get:r=>r.st?r.st.max:null,  fmt:r=>fmt(r.st&&r.st.max)},
  {k:"avg",   l:"Moyen",  get:r=>r.st?r.st.avg:null,  fmt:r=>fmt(r.st&&r.st.avg)},
  {k:"varj",  l:"Var j",  cls:"var", title:"Variation du prix moyen sur 24h", get:r=>r.varj, fmt:r=>varCell(r.varj)},
  {k:"vars",  l:"Var s",  cls:"var", title:"Variation du prix moyen sur 1 semaine", get:r=>r.vars, fmt:r=>varCell(r.vars)},
  {k:"varm",  l:"Var m",  cls:"var", title:"Variation du prix moyen sur 1 mois", get:r=>r.varm, fmt:r=>varCell(r.varm)},
  {k:"spark", l:"Tendance", title:"Prix moyen sur 7 jours (échelle 0→max)", get:r=>0, fmt:r=>sparkline(lastDays(r.avgS,7)), sort:false},
  {k:"vol",   l:"V",      cls:"narrow", title:"Indice de volume 0–10 : fréquence de changement du prix moyen sur 10 jours", get:r=>r.vol, fmt:r=>r.vol==null?'<span class="muted">—</span>':r.vol},
  {k:"hdvn",  l:"R",      cls:"narrow", title:"Nombre de relevés HDV réels", get:r=>r.hdvN, fmt:r=>r.hdvN||'<span class="muted">0</span>'},
  {k:"hdvlast",l:"Dernier",cls:"narrow", title:"Date du dernier relevé HDV", get:r=>r.hdvLastT, fmt:r=>r.hdvLast?dmy(r.hdvLast):'<span class="muted">—</span>'},
  {k:"gid",   l:"GID",    cls:"narrow", get:r=>r.gid, fmt:r=>r.gid},
];
// Tri par défaut : par niveau croissant (l'ordre HDV auquel Flo est habitué).
let SOURCE="avg", SORT={k:"niv",dir:1}, FILTER="", TYPEF="", FAVONLY=false, SELECTED=null;

function computeRows(){
  const q = FILTER.trim().toLowerCase();
  let rows = DTV.items.map(it=>{
    const s = seriesOf(it, SOURCE);
    const st = statsOf(s);
    const avgS = seriesOf(it, "avg");
    const hdvLast = it.hdv.length ? it.hdv[it.hdv.length-1][0] : null;
    return {gid:it.gid, nom:it.nom, type:it.type||"", level:(it.level==null?null:it.level),
            item:it, s, st, avgS,
            varj:varOver(avgS,1), vars:varOver(avgS,7), varm:varOver(avgS,30),
            vol:volumeIndex(avgS),
            hdvN:it.hdv.length, hdvLast, hdvLastT:hdvLast?Date.parse(hdvLast):-Infinity};
  }).filter(r=>r.st);   // n'affiche que les items qui ont des données pour cette source
  if(q) rows = rows.filter(r=>r.nom.toLowerCase().includes(q) || String(r.gid).includes(q));
  if(TYPEF) rows = rows.filter(r=>r.type===TYPEF);
  if(FAVONLY) rows = rows.filter(r=>isFav(r.gid));
  const col = COLS.find(c=>c.k===SORT.k) || COLS[4];
  rows.sort((a,b)=>{
    let va=col.get(a), vb=col.get(b);
    // null/undefined toujours en bas, quel que soit le sens du tri.
    const an=(va==null), bn=(vb==null);
    if(an && bn) return 0; if(an) return 1; if(bn) return -1;
    if(typeof va==="string"){ va=va.toLowerCase(); vb=vb.toLowerCase(); return va<vb?-SORT.dir:va>vb?SORT.dir:0; }
    return (va-vb)*SORT.dir;
  });
  return rows;
}
function renderHead(){
  document.getElementById("head").innerHTML = COLS.map(c=>{
    const arr = SORT.k===c.k ? `<span class="arrow">${SORT.dir<0?"▼":"▲"}</span>` : "";
    const tt = c.title ? ` title="${c.title}"` : "";
    return `<th class="${c.cls||''}"${tt} data-k="${c.k}" data-sort="${c.sort!==false}">${c.l} ${arr}</th>`;
  }).join("");
}
function renderRows(){
  const rows = computeRows();
  document.getElementById("count").textContent = rows.length + " items";
  const body = rows.map(r=>{   // tous les items, sans plafond
    const sel = SELECTED===r.gid ? ' class="sel"' : '';
    return `<tr data-gid="${r.gid}"${sel}>` +
      COLS.map(c=>{
        const ttl = c.k==="nom" ? ` title="${String(r.nom).replace(/"/g,"&quot;")}"` : "";
        return `<td class="${c.cls||''}"${ttl}>${c.fmt(r)}</td>`;
      }).join("") + `</tr>`;
  }).join("");
  document.getElementById("rows").innerHTML = body ||
    `<tr><td colspan="${COLS.length}"><div class="empty">Aucun item — lance d'abord <code>dtv ingest</code>.</div></td></tr>`;
}

// Mini sparkline SVG du prix moyen (7 derniers jours). Échelle Y 0→max, comme le
// graphe. Couleur inversée : rouge si ça monte, vert si ça descend.
function sparkline(s){
  if(!s || s.length<2) return '<span class="muted">—</span>';
  const v=s.map(p=>p[1]), mx=Math.max(...v)||1, W=46,H=16;
  const pts=v.map((y,i)=>`${(i/(v.length-1)*W).toFixed(1)},${(H-(y/mx)*H).toFixed(1)}`).join(" ");
  return `<svg class="spark" width="${W}" height="${H}"><polyline fill="none" stroke="${trendColor(v[v.length-1]-v[0])}" stroke-width="1.5" points="${pts}"/></svg>`;
}

// ── Graphe détaillé (SVG maison) ───────────────────────────────────────────
let DETAIL_ON = {avg:true, x1:true, x10:true, x100:true, x1000:true};
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
    `<div class="sub" style="margin-top:6px">Graphe en prix unitaire (lots ÷ 10/100/1000) — comparable au x1 et au prix moyen.</div>` +
    `<div class="legend" id="legend"></div>`;
  drawLegend(it, avail);
  drawChart(it);
  document.querySelectorAll("#rows tr").forEach(tr=>tr.classList.toggle("sel", +tr.dataset.gid===gid));
}
function statBlock(it){
  // Compact : prix actuel coloré + prix unitaire à côté (rien d'autre, pour
  // laisser la place au graphe).
  const blocks = ["avg","x1","x10","x100","x1000"].map(src=>{
    const st = statsOf(seriesOf(it,src)); if(!st) return "";
    const div = TIER_DIV[src];
    // prix actuel coloré + prix unitaire à côté ; en dessous, min/max PAR LOT.
    const unit = div>1 ? ` <span class="muted">= ${fmt(st.last/div)}/u</span>` : "";
    return `<div class="stat"><div class="v" style="color:${TIER_COLORS[src]}">${fmt(st.last)}${unit}</div>`+
           `<div class="l">${TIER_LABEL[src]} · min ${fmt(st.min)} / max ${fmt(st.max)}</div></div>`;
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
  // Prix ramené à l'UNITÉ (lot /10/100/1000) → les tiers se comparent au x1 / moyen.
  const series = sources.map(src=>({src, color:TIER_COLORS[src], pts:unitSeriesOf(it,src)
    .map(p=>[Date.parse(p[0]), p[1]]).filter(p=>!isNaN(p[0]))})).filter(s=>s.pts.length>0);
  if(!series.length){ host.innerHTML = '<div class="empty">Aucune série sélectionnée.</div>'; return; }
  const W=Math.max(host.clientWidth||520,320), H=240, P={l:54,r:12,t:12,b:24};
  let xs=[], ys=[];
  series.forEach(s=>s.pts.forEach(p=>{xs.push(p[0]); ys.push(p[1]);}));
  let x0=Math.min(...xs), x1=Math.max(...xs);
  // Axe Y : de 0 au prix unitaire le plus haut relevé.
  let y0=0, dataMax=Math.max(...ys); if(x1===x0){ x0-=1; x1+=1; } if(!(dataMax>0)){ dataMax=1; }
  // Axe Y : 0 → plafond ARRONDI au-dessus du max, paliers ronds.
  const sc = niceScale(dataMax, 5);
  let y1 = sc.top;
  const sx=v=>P.l+(v-x0)/(x1-x0)*(W-P.l-P.r);
  const sy=v=>H-P.b-(v-y0)/(y1-y0)*(H-P.t-P.b);
  // grille Y : subdivisions (demi-pas, pointillés bien visibles) puis paliers ronds.
  let grid="";
  for(let val=sc.step/2; val<y1; val+=sc.step){ const y=sy(val);
    grid+=`<line x1="${P.l}" y1="${y.toFixed(1)}" x2="${W-P.r}" y2="${y.toFixed(1)}" stroke="#5a6675" stroke-opacity="0.85" stroke-dasharray="2 4"/>`;
  }
  for(let val=0; val<=y1+1e-6; val+=sc.step){ const y=sy(val);
    grid+=`<line x1="${P.l}" y1="${y.toFixed(1)}" x2="${W-P.r}" y2="${y.toFixed(1)}" stroke="#48515e"/>`;
    grid+=`<text x="${P.l-6}" y="${(y+3).toFixed(1)}" text-anchor="end">${fmt(val)}</text>`;
  }
  // axes X (début, milieu, fin)
  [0,0.5,1].forEach(f=>{ const t=x0+(x1-x0)*f, x=sx(t);
    grid+=`<text x="${x.toFixed(1)}" y="${H-8}" text-anchor="${f===0?'start':f===1?'end':'middle'}">${new Date(t).toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'})}</text>`;
  });
  const paths = series.map(s=>{
    const div = TIER_DIV[s.src];
    const dots = s.pts.map(p=>`<circle cx="${sx(p[0]).toFixed(1)}" cy="${sy(p[1]).toFixed(1)}" r="2.5" fill="${s.color}" data-u="${p[1]}" data-lot="${p[1]*div}" data-src="${s.src}" data-t="${p[0]}"/>`).join("");
    const line = s.pts.length>1 ? `<polyline fill="none" stroke="${s.color}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" points="${s.pts.map(p=>`${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(" ")}"/>` : "";
    return line+dots;
  }).join("");
  host.innerHTML = `<svg width="100%" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="overflow:visible">${grid}${paths}</svg>`;
  // tooltip : prix du LOT + prix UNITAIRE côte à côte
  const tip=document.getElementById("tip");
  host.querySelectorAll("circle").forEach(c=>{
    c.addEventListener("mousemove",e=>{
      tip.style.display="block"; tip.style.left=(e.pageX+12)+"px"; tip.style.top=(e.pageY-10)+"px";
      const t=new Date(+c.dataset.t).toLocaleString('fr-FR'), src=c.dataset.src;
      const lot=fmt(+c.dataset.lot), u=fmt(+c.dataset.u);
      const line = TIER_DIV[src]>1 ? `lot <b>${lot}</b> · unité <b>${u}</b> k` : `<b>${u}</b> k`;
      tip.innerHTML=`<span style="color:${TIER_COLORS[src]}">${TIER_LABEL[src]}</span><br>${line}<br><span class="muted">${t}</span>`;
    });
    c.addEventListener("mouseleave",()=>tip.style.display="none");
  });
}

// ── Évènements ─────────────────────────────────────────────────────────────
document.getElementById("q").addEventListener("input", e=>{ FILTER=e.target.value; renderRows(); });
document.getElementById("source").addEventListener("change", e=>{ SOURCE=e.target.value; renderRows(); });
document.getElementById("typeFilter").addEventListener("change", e=>{ TYPEF=e.target.value; renderRows(); });
document.getElementById("favOnly").addEventListener("change", e=>{ FAVONLY=e.target.checked; renderRows(); });
document.getElementById("listSel").addEventListener("change", e=>{ setActive(e.target.value); renderRows(); });
document.getElementById("listNew").addEventListener("click", ()=>{
  const name=(prompt("Nom de la nouvelle liste ?")||"").trim();
  if(!name) return;
  if(!LISTS[name]) LISTS[name]=[];
  setActive(name); saveLists(); renderListControls(); renderRows();
});
document.getElementById("listDel").addEventListener("click", ()=>{
  if(Object.keys(LISTS).length<=1){ alert("Garde au moins une liste."); return; }
  if(!confirm(`Supprimer la liste « ${ACTIVE} » ?`)) return;
  delete LISTS[ACTIVE]; setActive(Object.keys(LISTS)[0]);
  saveLists(); renderListControls(); renderRows();
});
document.getElementById("head").addEventListener("click", e=>{
  const th=e.target.closest("th"); if(!th || th.dataset.sort==="false") return;
  const k=th.dataset.k;
  if(SORT.k===k) SORT.dir*=-1; else SORT={k, dir: (k==="nom"||k==="type"||k==="niv")?1:-1};
  renderHead(); renderRows();
});
document.getElementById("rows").addEventListener("click", e=>{
  // clic sur l'étoile favori : toggle sans ouvrir le détail
  const star=e.target.closest(".star");
  if(star){
    const gid=+star.dataset.fav; toggleFav(gid);
    star.classList.toggle("on", isFav(gid));
    renderListControls();                 // maj du compteur dans le sélecteur
    if(FAVONLY) renderRows();              // l'item peut sortir de la vue filtrée
    return;
  }
  const tr=e.target.closest("tr"); if(!tr || !tr.dataset.gid) return;
  showDetail(+tr.dataset.gid);
});

// ── Onglet « Craft & Brisage » ─────────────────────────────────────────────
const B = DTV.brisage || {available:false, reason:"(pas de données)"};
// Bénéfice : vert si positif (gain), rouge si négatif (perte).
const benFmt = v => v==null ? '<span class="muted">—</span>'
  : `<span style="color:${v>0?'var(--accent2)':v<0?'var(--bad)':'inherit'}">${(v>0?'+':'')+fmt(v)}</span>`;

function brisageCols(real){
  const cur = real ? {rev:"Revenu_reel", ben:"Benefice_reel", rent:"Rent_reel"}
                   : {rev:"Revenu_theo", ben:"Benefice_theo", rent:"Rent_theo"};
  const revLbl = real ? "Rev@réel" : `Rev@${B.coeff||100}%`;
  const cols = [];
  if(real) cols.push({k:"_mark", l:"", cls:"narrow", sort:false, get:r=>0,
    fmt:r=>(r.Benefice_reel||0)>0?'<span style="color:var(--accent2)">✓</span>':'<span style="color:var(--bad)">✗</span>'});
  cols.push(
    {k:"Nom", l:"Nom", cls:"name", get:r=>r.Nom||("GID "+r.GID), fmt:r=>r.Nom||("GID "+r.GID)},
    {k:"Type", l:"Type", cls:"type", get:r=>r.Type||"", fmt:r=>r.Type||'<span class="muted">—</span>'},
    {k:"Niveau", l:"Niv", cls:"narrow", get:r=>r.Niveau, fmt:r=>r.Niveau},
    {k:cur.rev, l:revLbl, cls:"narrow", title:"Valeur des runes obtenues", get:r=>r[cur.rev], fmt:r=>fmt(r[cur.rev])},
    {k:"Prix_Moyen", l:"Prix moy", cls:"narrow", title:"Prix moyen de l'item fini à l'HDV (achat direct, à comparer au coût de craft)", get:r=>r.Prix_Moyen, fmt:r=>r.Prix_Moyen==null?'<span class="muted">—</span>':fmt(r.Prix_Moyen)},
    {k:"Cout_HDV", l:"Craft", cls:"narrow", title:"Coût de craft (Σ ingrédients au meilleur tier)", get:r=>r.Cout_HDV, fmt:r=>r.Cout_HDV==null?'<span class="muted">—</span>':fmt(r.Cout_HDV)},
    {k:"Coeff_Min", l:"C.min", cls:"narrow", title:"Coeff serveur minimal pour être rentable (plus bas = plus sûr)", get:r=>r.Coeff_Min, fmt:r=>r.Coeff_Min==null?'<span class="muted">—</span>':fmt(r.Coeff_Min)+"%"},
    {k:cur.ben, l:"Bénéf", cls:"narrow", get:r=>r[cur.ben], fmt:r=>benFmt(r[cur.ben])},
    {k:cur.rent, l:"Rent", cls:"narrow", title:"Rentabilité = revenu / coût", get:r=>r[cur.rent], fmt:r=>r[cur.rent]==null?'<span class="muted">—</span>':r[cur.rent].toFixed(2)},
  );
  if(real) cols.push(
    {k:"Coeff_Reel", l:"C.réel", cls:"narrow", get:r=>r.Coeff_Reel, fmt:r=>r.Coeff_Reel==null?'—':fmt(r.Coeff_Reel)+"%"},
    {k:"Dernier_Brisage", l:"Brisé", cls:"narrow", get:r=>r.Dernier_Brisage||"", fmt:r=>r.Dernier_Brisage?dmy(r.Dernier_Brisage):'<span class="muted">—</span>'},
  );
  cols.push({k:"Runes", l:"Runes obtenues", cls:"runesb", sort:false, get:r=>r.Runes||"",
    fmt:r=>r.Runes||'<span class="muted">—</span>'});
  return cols;
}
const BSORT = {};
function renderBTable(hostId, rows, real, defaultSort){
  const cols = brisageCols(real);
  if(!BSORT[hostId]) BSORT[hostId] = defaultSort;
  const srt = BSORT[hostId];
  const col = cols.find(c=>c.k===srt.k) || cols[0];
  const sorted = rows.slice().sort((a,b)=>{
    let va=col.get(a), vb=col.get(b);
    const an=(va==null||va===""), bn=(vb==null||vb===""); if(an&&bn)return 0; if(an)return 1; if(bn)return -1;
    if(typeof va==="string"){va=va.toLowerCase();vb=vb.toLowerCase();return va<vb?-srt.dir:va>vb?srt.dir:0;}
    return (va-vb)*srt.dir;
  });
  const head = cols.map(c=>{
    const arr = srt.k===c.k?`<span class="arrow">${srt.dir<0?"▼":"▲"}</span>`:"";
    const tt=c.title?` title="${c.title}"`:"";
    return `<th class="${c.cls||''}"${tt} data-k="${c.k}" data-sort="${c.sort!==false}">${c.l} ${arr}</th>`;
  }).join("");
  const body = sorted.map(r=>"<tr>"+cols.map(c=>`<td class="${c.cls||''}">${c.fmt(r)}</td>`).join("")+"</tr>").join("");
  document.getElementById(hostId).innerHTML =
    `<div class="tablewrap"><table><thead><tr>${head}</tr></thead><tbody>${body||`<tr><td>—</td></tr>`}</tbody></table></div>`;
  document.querySelector(`#${hostId} thead`).addEventListener("click", e=>{
    const th=e.target.closest("th"); if(!th||th.dataset.sort==="false"||!th.dataset.k) return;
    const k=th.dataset.k;
    if(srt.k===k) srt.dir*=-1; else BSORT[hostId]={k, dir:(k==="Nom"||k==="Type")?1:-1};
    renderBTable(hostId, rows, real, defaultSort);
  });
}
function renderBrisage(){
  const root=document.getElementById("craft-root");
  if(!B.available){
    root.innerHTML=`<div class="soon"><div class="big">⚒️</div><p>${B.reason||'Pas de données de craft/brisage.'}</p></div>`;
    return;
  }
  const costTag = B.craft_mode ? '<span class="tag ok">coût = craft (tiers HDV optimisés)</span>'
                               : '<span class="tag warn">coût = craft (avgprices, sans optim. tiers)</span>';
  const runeTag = B.rune_live ? '<span class="tag ok">prix runes HDV</span>'
                              : '<span class="tag warn">prix runes = exemples</span>';
  const hasReal = B.real && B.real.length;
  root.innerHTML =
    `<div class="notice">`+
    `<span><b>${fmt(B.n_ranked)}</b> items chiffrables / ${fmt(B.n_catalog)} au catalogue</span>`+
    `<span>${costTag}</span><span>${runeTag}</span>`+
    `<span>coeff théorique <b>${B.coeff}%</b></span></div>`+
    // Brisages réels EN PREMIER (watchlist : ce qui est rentable maintenant).
    (hasReal
      ? `<h3 class="sec">🎯 Brisages réels <span class="muted">— coeff observé en jeu appliqué (${B.n_real})</span></h3><div id="breal"></div>`
      : `<h3 class="sec">🎯 Brisages réels</h3><div class="empty">Aucune observation de coefficient en jeu pour l'instant (capture en cours de remplissage).</div>`)+
    `<h3 class="sec">🏆 Top théorique <span class="muted">— ${B.sort_label}</span></h3><div id="btheo"></div>`;
  if(hasReal) renderBTable("breal", B.real, true, {k:"Benefice_reel", dir:-1});
  renderBTable("btheo", B.theo, false, {k:"Coeff_Min", dir:1});
}

// ── Boot ───────────────────────────────────────────────────────────────────
(function initTypeFilter(){
  const types = [...new Set(DTV.items.map(it=>it.type).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'fr'));
  document.getElementById("typeFilter").insertAdjacentHTML("beforeend",
    types.map(t=>`<option value="${t.replace(/"/g,"&quot;")}">${t}</option>`).join(""));
})();
renderListControls();
renderHead(); renderRows();
renderBrisage();
if(DTV.items.length){
  // sélectionne le 1er item de la vue (niveau le plus bas) pour montrer un graphe d'emblée
  const first = computeRows()[0];
  if(first) showDetail(first.gid);
}
</script>
</body>
</html>
"""
