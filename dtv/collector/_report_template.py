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
  /* Repère visuel : coeff de brisage et rentabilité en doré léger */
  td.gold, th.gold { color:#d8b978; }
  /* Coloration rentabilité des lignes (triage visuel) */
  tr.prof-pos { background:#2ea04314; } tr.prof-pos:hover { background:#2ea04322; }
  tr.prof-neg { background:#f8514910; } tr.prof-neg:hover { background:#f8514920; }
  .help { background:var(--panel2); border:1px solid var(--border); border-left:3px solid var(--accent);
          border-radius:6px; padding:8px 12px; margin:0 0 12px; font-size:12.5px; color:var(--muted); }
  .help b { color:var(--text); }
  .modal-bg { position:fixed; inset:0; background:#000a; display:flex; align-items:center;
              justify-content:center; z-index:50; padding:24px; }
  .modal { background:var(--panel); border:1px solid var(--border); border-radius:10px;
           max-width:760px; width:100%; max-height:88vh; overflow:auto; padding:20px 22px; }
  /* Mode double : concassage à gauche, graphe à droite, côte à côte */
  .modal-bg.dual-left { justify-content:flex-start; }
  .modal-bg.dual-right { justify-content:flex-end; background:transparent; pointer-events:none; }
  .modal-bg.dual-left .modal, .modal-bg.dual-right .modal { max-width:48vw; }
  .modal-bg.dual-right .modal { pointer-events:auto; }
  #closeboth { position:fixed; top:12px; left:50%; transform:translateX(-50%); z-index:70;
    background:var(--bad); color:#fff; border:none; border-radius:6px; padding:7px 16px;
    font-size:13px; font-weight:600; cursor:pointer; box-shadow:0 2px 8px #0008; }
  #closeboth:hover { filter:brightness(1.1); }
  .modtitle { cursor:pointer; } .modtitle:hover { text-decoration:underline; }
  .goicon { font-size:14px; opacity:.65; } .modtitle:hover .goicon { opacity:1; }
  .usedchips { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0; }
  .chip { background:var(--panel2); border:1px solid var(--border); border-radius:12px; padding:3px 10px; font-size:12px; }
  .chip:not(.muted) { cursor:pointer; } .chip:not(.muted):hover { border-color:var(--accent); }
  .modal h3 { margin:0 0 2px; font-size:18px; }
  .modal .x { float:right; cursor:pointer; color:var(--muted); font-size:20px; line-height:1; }
  .modal .x:hover { color:var(--text); }
  .modal table { margin-top:6px; }
  .modal td, .modal th { padding:5px 8px; }
  .kv { display:flex; gap:14px; flex-wrap:wrap; margin:10px 0; }
  .kv .b { background:var(--panel2); border:1px solid var(--border); border-radius:6px; padding:6px 12px; }
  .kv .b .l { color:var(--muted); font-size:11px; } .kv .b .v { font-weight:600; }
  .verdict { padding:8px 12px; border-radius:6px; margin:10px 0; font-size:13px; }
  .verdict.buy { background:#1f6feb22; border:1px solid var(--accent); }
  .verdict.craft { background:#2ea04322; border:1px solid #2ea04366; }
  .batchsel { display:inline-flex; gap:4px; }
  .batchsel button { background:var(--panel2); border:1px solid var(--border); color:var(--muted);
                     border-radius:5px; padding:4px 9px; font-size:12px; cursor:pointer; }
  .batchsel button.on { color:var(--text); border-color:var(--accent); }
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
    z-index:60;   /* au-dessus des modales (z-index:50) — sinon le tooltip passe derrière */
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
  <section class="tab" data-tab="craftsell"><div id="craftsell-root"></div></section>
  <section class="tab" data-tab="affaires"><div id="affaires-root"></div></section>
  <section class="tab" data-tab="arbitrage"><div id="arb-root"></div></section>
  <section class="tab" data-tab="runes"><div id="runes-root"></div></section>
  <section class="tab" data-tab="liste"><div id="liste-root"></div></section>
  <section class="tab" data-tab="favoris"><div id="favoris-root"></div></section>
  <section class="tab" data-tab="archives"><div id="archives-root"></div></section>
</main>
<div class="chart-tip" id="tip"></div>
<div class="modal-bg" id="bmodal" style="display:none"><div class="modal" id="bmodal-box"></div></div>
<div class="modal-bg" id="pmodal" style="display:none"><div class="modal" id="pmodal-box"></div></div>
<button id="closeboth" style="display:none">✕ Tout fermer</button>

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
// Normalisation de nom (miroir simple de brisage.normalize_name) pour croiser
// recettes ↔ items (sous-crafts, ressources utilisées, affaires).
const normName = s => (s||"").toLowerCase().replace(/\s+/g," ").trim();
// ── Archives (items/types exclus de tous les tableaux, mais toujours relevés) ─
const GIDTYPE = (()=>{ const m={}; DTV.items.forEach(it=>{ m[it.gid]=it.type||""; }); return m; })();
let ARCHIVE = (()=>{ try{ const a=JSON.parse(localStorage.getItem("dtv_archive"))||{}; return {items:a.items||[], types:a.types||[]}; }catch(e){ return {items:[], types:[]}; } })();
function saveArch(){ try{ localStorage.setItem("dtv_archive", JSON.stringify(ARCHIVE)); }catch(e){} }
function isArchived(gid){ return ARCHIVE.items.includes(gid) || ARCHIVE.types.includes(GIDTYPE[gid]); }
function archiveItem(gid){ if(!ARCHIVE.items.includes(gid)) ARCHIVE.items.push(gid); saveArch(); }
function unarchiveItem(gid){ ARCHIVE.items=ARCHIVE.items.filter(g=>g!==gid); saveArch(); }
function archiveType(t){ if(t && !ARCHIVE.types.includes(t)) ARCHIVE.types.push(t); saveArch(); }
function unarchiveType(t){ ARCHIVE.types=ARCHIVE.types.filter(x=>x!==t); saveArch(); }
// ── Métadonnées de favoris : intention + note par item ──────────────────────
let FAVMETA = (()=>{ try{ return JSON.parse(localStorage.getItem("dtv_favmeta"))||{}; }catch(e){ return {}; } })();
function saveFavMeta(){ try{ localStorage.setItem("dtv_favmeta", JSON.stringify(FAVMETA)); }catch(e){} }
function favMeta(gid){ return FAVMETA[gid] || (FAVMETA[gid]={intent:"prix", note:""}); }
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
  "généré le " + DTV.generated_at.replace("T"," ") + "  ·  compte " + ((DTV.stats&&DTV.stats.account)||"?") + "  ·  " + DTV.db_path;
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
// ── Filtres globaux : capital max par opération + bénéfice minimum ──────────
let MAX_INVEST=null, MIN_BENEF=0;
(function(){
  const d=document.createElement("div");
  d.style.cssText="margin-left:auto;display:flex;gap:12px;align-items:flex-end";
  d.innerHTML =
    `<label class="kpi" style="cursor:auto"><div class="l">💰 Invest. max (capital/op.)</div>`+
      `<input id="maxInvest" type="text" inputmode="numeric" placeholder="∞ (ex: 1M)" style="width:110px"></label>`+
    `<label class="kpi" style="cursor:auto"><div class="l">📈 Bénéf. min /batch</div>`+
      `<input id="minBenef" type="text" inputmode="numeric" value="0" style="width:90px"></label>`+
    `<button class="btn" id="filtApply" style="align-self:center">Appliquer ✓</button>`;
  document.getElementById("kpis").appendChild(d);
  // Parse tolérant : « 20 000 », « 1 000 000 », « 1.5M » → nombre (espaces/séparateurs OK).
  const parseAmount = s=>{ s=(s||"").toLowerCase().replace(/[\s,]/g,"");
    let mult=1; if(s.endsWith("m")){mult=1e6;s=s.slice(0,-1);} else if(s.endsWith("k")){mult=1e3;s=s.slice(0,-1);}
    const n=parseFloat(s); return isFinite(n)?n*mult:null; };
  const applyFilters=()=>{ MAX_INVEST=parseAmount(document.getElementById("maxInvest").value);
    MIN_BENEF=parseAmount(document.getElementById("minBenef").value)||0; refreshAll(); };
  document.getElementById("filtApply").onclick=applyFilters;
  document.getElementById("maxInvest").addEventListener("change", applyFilters);
  document.getElementById("minBenef").addEventListener("change", applyFilters);
})();
// Filtre une ligne par capital investi et bénéfice minimal (null = inconnu → on garde si pas de seuil).
function passInvestBenef(invest, benef){
  if(MAX_INVEST!=null && invest!=null && invest>MAX_INVEST) return false;
  if(MIN_BENEF>0 && (benef==null || benef<MIN_BENEF)) return false;
  return true;
}
// Re-render UNIQUEMENT l'onglet concerné (perf : éviter de redessiner 2000+
// lignes des autres onglets à chaque changement de batch/filtre dans un popup).
function renderTab(id){ switch(id){
  case "craft": if(B.available) renderBrisage(); break;
  case "craftsell": if(CR.available) renderCraft(); break;
  case "affaires": renderAffaires(); break;
  case "arbitrage": renderArbitrage(); break;
  case "runes": renderRunes(); break;
  case "liste": renderCraftList(); break;
  case "favoris": renderFavoris(); break;
  case "archives": renderArchives(); break;
} }
function refreshActiveTab(){ const s=document.querySelector(".tab.active"); if(s) renderTab(s.dataset.tab); }
// Les filtres globaux ne re-rendent que l'onglet visible ; les autres se
// rafraîchissent à l'affichage (renderTab au clic d'onglet).
function refreshAll(){ refreshActiveTab(); }
const TABS = [["prix","📈 Prix dans le temps"],["favoris","⭐ Favoris"],["achats","🛒 Ressources achetées"],
              ["craft","⚒️ Craft & Brisage"],["craftsell","🛠️ Craft (revente)"],
              ["affaires","💎 Bonnes affaires"],
              ["arbitrage","💱 Achat / Vente"],["runes","🔮 Runes"],["liste","🧺 Ma liste"],
              ["archives","🗄 Archives"]];
document.getElementById("tabs").innerHTML =
  TABS.map(([id,l],i)=>`<button data-go="${id}"${i===0?' class="active"':''}>${l}</button>`).join("");
document.getElementById("tabs").addEventListener("click", e=>{
  const b = e.target.closest("button"); if(!b) return;
  const id = b.dataset.go;
  document.querySelectorAll("nav.tabs button").forEach(x=>x.classList.toggle("active", x===b));
  document.querySelectorAll(".tab").forEach(s=>s.classList.toggle("active", s.dataset.tab===id));
  renderTab(id);   // rafraîchit l'onglet avec l'état global courant (batch/filtres)
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
// ── Lots de vente réalistes par item (persistés) ───────────────────────────
// Pour chaque item : quels lots (x1/x10/x100) on revend vraiment. Sert à
// filtrer le concassage et l'arbitrage (ex : une Pa Fo ne se vend que par 100).
const LS_SELL="dtv_selllots";
const DEFAULT_SELL=["x10","x100"];   // défaut : pas de x1 (exception : ga pa, pa do cri…)
const LOTSIZE={x1:1, x10:10, x100:100, x1000:1000};
let SELLLOTS = (()=>{ try{ return JSON.parse(localStorage.getItem(LS_SELL))||{}; }catch(e){ return {}; } })();
function saveSell(){ try{ localStorage.setItem(LS_SELL, JSON.stringify(SELLLOTS)); }catch(e){} }
function sellLots(gid){ return SELLLOTS[gid] || DEFAULT_SELL; }
function isSellOn(gid, lot){ return sellLots(gid).includes(lot); }
function toggleSell(gid, lot){
  const arr = (SELLLOTS[gid] || DEFAULT_SELL).slice();
  const i = arr.indexOf(lot);
  if(i<0) arr.push(lot); else arr.splice(i,1);
  SELLLOTS[gid] = arr; saveSell();
}
function sellLotCtrlHTML(gid){
  return `<div class="sub" style="margin:6px 0"><span class="muted">Lots de vente réalistes :</span> `+
    ["x1","x10","x100"].map(l=>`<label class="chk" style="margin-right:8px"><input type="checkbox" data-sell="${l}" data-gid="${gid}"${isSellOn(gid,l)?' checked':''}> ${l}</label>`).join("")+
    `</div>`;
}
// Re-render des vues dépendantes quand les lots de vente changent.
function refreshSellViews(gid, root){
  showDetail(gid, root);
  if(typeof refreshActiveTab==="function") refreshActiveTab();
}
// ── Prix de vente avec règle de fraîcheur (relevé HDV < 3 j sinon prix moyen) ─
const DATA_NOW = (DTV.generated_at ? Date.parse(DTV.generated_at) : Date.now());
// Prix unitaire d'un tier SI son dernier relevé date de < 3 jours, sinon null.
function tierFreshUnit(it, src){
  const s = seriesOf(it, src); if(!s.length) return null;
  if(DATA_NOW - Date.parse(s[s.length-1][0]) >= 3*DAY) return null;
  const st = statsOf(s); return st ? st.last/LOTSIZE[src] : null;
}
function avgUnit(it){ const st = statsOf(seriesOf(it,"avg")); return st ? st.last : null; }
// Prix de vente unitaire effectif d'un tier : relevé frais (<3j) sinon prix moyen.
function effUnit(it, src){ const f = tierFreshUnit(it, src); return f!=null ? f : avgUnit(it); }
// Meilleur lot de vente autorisé (prix unitaire le + haut = meilleur ratio, coût fixe).
function bestSell(it, gid){
  let best=null;
  ["x1","x10","x100"].forEach(src=>{ if(!isSellOn(gid,src)) return;
    const u=effUnit(it,src); if(u==null) return;
    if(best==null || u>best.unit) best={src, unit:u}; });
  return best;   // {src,unit} ou null
}
// ── Fraîcheur (F) : ancienneté du dernier relevé ───────────────────────────
// Deux fraîcheurs existent : HDV (relevés réels) et moyenne (prix moyen marché).
// Seule la fraîcheur HDV est affichée ; la moyenne sert de repli (Bonnes affaires).
function seriesFreshDays(s){ return (s&&s.length) ? (DATA_NOW - Date.parse(s[s.length-1][0]))/DAY : null; }
function hdvFreshDays(it){ return (it && it.hdv && it.hdv.length) ? (DATA_NOW - Date.parse(it.hdv[it.hdv.length-1][0]))/DAY : null; }
const _fColor = d => d<3 ? 'var(--accent2)' : d<10 ? 'var(--warn)' : 'var(--bad)';
const _fDays  = d => d<10 ? d.toFixed(1) : Math.round(d);
function freshCell(d, tag){
  if(d==null) return '<span class="muted">—</span>';
  const t = tag ? ` <span class="muted">${tag}</span>` : '';
  return `<span title="dernier relevé ${tag==='moy'?'(prix moyen) ':'HDV '}il y a ${d.toFixed(1)} j" style="color:${_fColor(d)}">● ${_fDays(d)}j${t}</span>`;
}
// Fraîcheur d'item : HDV par défaut ; si pas de HDV récent, repli sur la moyenne (taggé « moy »).
function hdvFreshCell(it){ return freshCell(hdvFreshDays(it)); }
// Couleur dégradée vert (bas marché) → rouge (cher) selon le ratio prix/médiane.
function gradColor(ratio){ if(ratio==null||!isFinite(ratio)) return "var(--muted)";
  const t=Math.max(0,Math.min(1,(ratio-0.6)/0.8)); return `hsl(${(120*(1-t)).toFixed(0)},65%,58%)`; }
// Cellule « prix unitaire d'un tier » colorée selon la médiane (prix moyen).
function tierUnitCell(it, src){
  const st=statsOf(seriesOf(it,src)); if(!st||!(st.last>0)) return _md;
  const u=st.last/LOTSIZE[src], med=avgUnit(it);
  return `<span style="color:${gradColor(med?u/med:null)}" title="lot ${fmt(st.last)}">${fmt(u)}</span>`;
}
function dealFreshCell(it){
  const h = hdvFreshDays(it);
  if(h!=null && h<10) return freshCell(h);
  const a = seriesFreshDays(seriesOf(it,"avg"));
  return a!=null ? freshCell(a, 'moy') : freshCell(h);
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
  // Trouve le point le plus proche de target (hors dernier point) pour éviter
  // de comparer contre un point trop ancien quand les captures sont irrégulières.
  let past=null, bestDist=Infinity;
  for(let i=0;i<series.length-1;i++){
    const dist=Math.abs(Date.parse(series[i][0])-target);
    if(dist<bestDist){ bestDist=dist; past=series[i][1]; }
  }
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
  return Math.round(changes/(s.length-1)*100)/10;
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
  {k:"nom",   l:"Nom",    cls:"name", title:"Nom de l'item", get:r=>r.nom, fmt:r=>r.nom},
  {k:"type",  l:"Type",   cls:"type", title:"Type d'objet", get:r=>r.type, fmt:r=>r.type||'<span class="muted">—</span>'},
  {k:"niv",   l:"Niv",    cls:"narrow", title:"Niveau de l'objet (ordre HDV)", get:r=>r.level, fmt:r=>r.level==null?'<span class="muted">—</span>':r.level},
  {k:"last",  l:"Moyen",  title:"Prix moyen le plus récent (source sélectionnée)", get:r=>r.st?r.st.last:null, fmt:r=>fmt(r.st&&r.st.last)},
  {k:"min",   l:"Min",    title:"Prix minimum observé (source sélectionnée)", get:r=>r.st?r.st.min:null,  fmt:r=>fmt(r.st&&r.st.min)},
  {k:"max",   l:"Max",    title:"Prix maximum observé (source sélectionnée)", get:r=>r.st?r.st.max:null,  fmt:r=>fmt(r.st&&r.st.max)},
  {k:"avg",   l:"Médian", title:"Prix médian historique (moyenne de tous les relevés, source sélectionnée)", get:r=>r.st?r.st.avg:null,  fmt:r=>fmt(r.st&&r.st.avg)},
  {k:"varj",  l:"Var j",  cls:"var", title:"Variation du prix moyen sur 24h", get:r=>r.varj, fmt:r=>varCell(r.varj)},
  {k:"vars",  l:"Var s",  cls:"var", title:"Variation du prix moyen sur 1 semaine", get:r=>r.vars, fmt:r=>varCell(r.vars)},
  {k:"varm",  l:"Var m",  cls:"var", title:"Variation du prix moyen sur 1 mois", get:r=>r.varm, fmt:r=>varCell(r.varm)},
  {k:"spark", l:"Tendance", title:"Prix moyen sur 7 jours (échelle 0→max)", get:r=>0, fmt:r=>sparkline(lastDays(r.avgS,7)), sort:false},
  {k:"vol",   l:"V",      cls:"narrow", title:"Indice de volume 0–10 : fréquence de changement du prix moyen sur 10 jours (avec décimale)", get:r=>r.vol, fmt:r=>r.vol==null?'<span class="muted">—</span>':(+r.vol).toFixed(1)},
  {k:"fresh", l:"F",      cls:"narrow", title:"Fraîcheur HDV : ancienneté du dernier relevé HDV réel. ● vert <3j · orange <10j · rouge au-delà", get:r=>hdvFreshDays(r.item), fmt:r=>hdvFreshCell(r.item)},
  {k:"hdvn",  l:"R",      cls:"narrow", title:"Nombre de relevés HDV réels", get:r=>r.hdvN, fmt:r=>r.hdvN||'<span class="muted">0</span>'},
  {k:"hdvlast",l:"Dernier",cls:"narrow", title:"Date du dernier relevé HDV", get:r=>r.hdvLastT, fmt:r=>r.hdvLast?dmy(r.hdvLast):'<span class="muted">—</span>'},
  {k:"gid",   l:"GID",    cls:"narrow", title:"Identifiant unique de l'item dans le jeu", get:r=>r.gid, fmt:r=>r.gid},
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
  rows = rows.filter(r=>!isArchived(r.gid));
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
function showDetail(gid, root){
  const it = DTV.items.find(i=>i.gid===gid);
  if(!it){ return; }
  root = root || document.getElementById("detail");
  const inPriceTab = root.id === "detail";
  if(inPriceTab) SELECTED = gid;
  const avail = {};
  ["avg","x1","x10","x100","x1000"].forEach(src=>{ avail[src]=seriesOf(it,src).length>=1; });
  const vol = volumeIndex(seriesOf(it,"avg"));
  // Lien vers le craft/brisage de l'item (icône ⚒️) s'il en a un.
  const craftRow = (typeof BRISMAP!=="undefined" && BRISMAP[gid])
                || (typeof CRAFTMAP!=="undefined" && CRAFTMAP[gid])
                || ((typeof RD!=="undefined" && RD.concassage) ? RD.concassage.find(x=>x.GID===gid) : null);
  root.innerHTML =
    `<h3${craftRow?' class="modtitle" title="Voir le craft / brisage"':''}>${it.nom}${craftRow?' <span class="goicon">⚒️</span>':''}</h3>`+
    `<div class="sub">GID ${it.gid}${it.type?' · '+it.type:''}${it.level!=null?' · niv '+it.level:''} · `+
      `<span title="Indice de volume 0–10 : fréquence de changement du prix moyen sur 10 jours">Volume V ${vol==null?'—':(+vol).toFixed(1)}</span></div>` +
    `<div class="controls" style="gap:6px;margin:6px 0">`+
      `<button class="btn" data-favit="${it.gid}">${isFav(it.gid)?'★ Favori ✓':'☆ Favori'}</button>`+
      (it.type?`<button class="btn" data-favtype="${it.type.replace(/"/g,'&quot;')}">★ Favori le type</button>`:'')+
      `<button class="btn" data-archit="${it.gid}">🗄 ${isArchived(it.gid)?'Désarchiver':'Archiver'}</button>`+
      (it.type?`<button class="btn" data-archtype="${it.type.replace(/"/g,'&quot;')}">🗄 Archiver le type</button>`:'')+
    `</div>`+
    sellLotCtrlHTML(it.gid) +
    statBlock(it) +
    `<div class="chart"></div>` +
    `<div class="sub" style="margin-top:6px">Graphe en prix unitaire (lots ÷ 10/100/1000) — comparable au x1 et au prix moyen.</div>` +
    `<div class="legend"></div>` +
    `<div class="recipein"></div>`+
    `<div class="usedin"></div>`+
    `<div class="concin"></div>`;
  drawLegend(it, avail, root);
  drawChart(it, root);
  renderRecipe(it, root.querySelector(".recipein"));
  renderUsedIn(it, root.querySelector(".usedin"));
  renderConcIn(it, root.querySelector(".concin"));
  root.querySelectorAll("input[data-sell]").forEach(cb=>cb.onchange=()=>{
    toggleSell(+cb.dataset.gid, cb.dataset.sell); refreshSellViews(gid, root);
  });
  const dc=root.querySelector(".modtitle");
  if(dc && craftRow) dc.onclick=()=>openBModal(craftRow, false);   // ⚒️ → popup craft (à gauche)
  const bFav=root.querySelector("[data-favit]");
  if(bFav) bFav.onclick=()=>{ toggleFav(gid); renderListControls(); showDetail(gid, root); if(typeof renderFavoris==="function") renderFavoris(); };
  const bFavT=root.querySelector("[data-favtype]");
  if(bFavT) bFavT.onclick=()=>{ const t=bFavT.dataset.favtype;
    DTV.items.forEach(x=>{ if((x.type||"")===t && !isFav(x.gid)) toggleFav(x.gid); }); renderListControls(); showDetail(gid, root); };
  const bArch=root.querySelector("[data-archit]");
  if(bArch) bArch.onclick=()=>{ isArchived(gid)?unarchiveItem(gid):archiveItem(gid); showDetail(gid, root); refreshActiveTab(); if(typeof renderArchives==="function") renderArchives(); };
  const bArchT=root.querySelector("[data-archtype]");
  if(bArchT) bArchT.onclick=()=>{ archiveType(bArchT.dataset.archtype); showDetail(gid, root); refreshActiveTab(); if(typeof renderArchives==="function") renderArchives(); };
  if(inPriceTab)
    document.querySelectorAll("#rows tr").forEach(tr=>tr.classList.toggle("sel", +tr.dataset.gid===gid));
}
function statBlock(it){
  // Compact : prix actuel coloré + prix unitaire à côté (rien d'autre, pour
  // laisser la place au graphe).
  const blocks = ["avg","x1","x10","x100","x1000"].map(src=>{
    const st = statsOf(seriesOf(it,src)); if(!st) return "";
    const div = TIER_DIV[src];
    // prix actuel coloré + prix unitaire à côté ; en dessous, min/max PAR LOT + Volume V du tier.
    const unit = div>1 ? ` <span class="muted">= ${fmt(st.last/div)}/u</span>` : "";
    const v = volumeIndex(seriesOf(it,src));
    const vTag = v==null ? "" : ` · <span title="Volume V de ce tier (0–10)">V ${(+v).toFixed(1)}</span>`;
    return `<div class="stat"><div class="v" style="color:${TIER_COLORS[src]}">${fmt(st.last)}${unit}</div>`+
           `<div class="l">${TIER_LABEL[src]} · min ${fmt(st.min)} / max ${fmt(st.max)}${vTag}</div></div>`;
  }).join("");
  return `<div class="statgrid">${blocks||'<span class="muted">aucune donnée</span>'}</div>`;
}
function drawLegend(it, avail, root){
  const lg = (root||document).querySelector(".legend");
  lg.innerHTML = ["avg","x1","x10","x100","x1000"].filter(s=>avail[s]).map(src=>
    `<label class="${DETAIL_ON[src]?'on':''}" data-src="${src}"><span class="dot" style="background:${TIER_COLORS[src]}"></span>${TIER_LABEL[src]}</label>`
  ).join("");
  lg.querySelectorAll("label").forEach(l=>l.onclick=()=>{
    const s=l.dataset.src; DETAIL_ON[s]=!DETAIL_ON[s];
    l.classList.toggle("on", DETAIL_ON[s]); drawChart(it, root);
  });
}
function drawChart(it, root){
  const host = (root||document).querySelector(".chart");
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
let BATCH = "auto";   // taille de lot de craft : "auto" | "10" | "100" | "1000"
// x1 retiré : on ne vend/craft jamais à l'unité, c'est du bruit.
const BATCHES = ["budget","smart","auto","10","100","1000"];
let BFAVONLY=false, RUNETARGET="";   // favoris seulement / rune ciblée (code)
let BRIS_DETAIL=false;               // false = vue essentielle, true = toutes les colonnes
// Bénéfice : vert si positif (gain), rouge si négatif (perte).
const benFmt = v => v==null ? '<span class="muted">—</span>'
  : `<span style="color:${v>0?'var(--accent2)':v<0?'var(--bad)':'inherit'}">${(v>0?'+':'')+fmt(v)}</span>`;

// Moteur de choix de tier porté de craft.py (best_tier) — pour le détail au clic.
const MAX_PURCHASES = 30;
function bestTier(tiers, totalNeeded){
  if(!tiers) return null;
  const avail = {}; [1,10,100,1000].forEach(t=>{ if(tiers[t]) avail[t]=tiers[t]; });
  const keys = Object.keys(avail).map(Number);
  if(!keys.length) return null;
  const usable = keys.filter(t=>t<=totalNeeded);
  if(!usable.length){ const t=Math.min(...keys); return {tier:t, unit:avail[t]/t}; }
  const practical = usable.filter(t=>Math.ceil(totalNeeded/t)<=MAX_PURCHASES);
  const pool = practical.length ? practical : [Math.max(...usable)];
  const t = pool.reduce((a,b)=> (avail[a]/a <= avail[b]/b ? a : b));
  return {tier:t, unit:avail[t]/t};
}

// Mode « smart » : batch (parmi x1/x10/x100/x1000) au coût de craft le + bas
// → revenu fixe ⇒ coût mini = bénéfice maxi pour l'item.
// Lots réalistes selon l'item. Seules les lignes de l'onglet Craft portent
// is_equip → un équipement/arme ne se craft que par 1 ou 10.
// (brisage/concassage n'ont pas is_equip → comportement inchangé.)
function allowedBatches(r){ return r.is_equip ? ["1","10"] : ["10","100","1000"]; }
function smartBatch(r){
  if(!r.craft) return null;
  // Smart = meilleure marge (cpc le + bas) qui RESPECTE le plafond d'investissement.
  // Ex : plafond 20k → on descend de x100 (180k) à x10 (19k) au lieu d'exclure l'item.
  let best=null, fallback=null;
  for(const b of allowedBatches(r)){
    const c=r.craft.cpc[b]; if(c==null) continue;
    if(fallback==null || c<fallback.cost) fallback={batch:b, cost:c};
    if(MAX_INVEST!=null && c*Number(b) > MAX_INVEST) continue;   // dépasse le capital max
    if(best==null || c<best.cost) best={batch:b, cost:c};
  }
  return best || fallback;   // si rien ne tient sous le plafond, le + petit (sera filtré)
}
// Mode « budget » : contrairement à smart (qui vise la meilleure marge unitaire,
// donc le + gros lot), budget choisit le batch qui MAXIMISE le bénéfice TOTAL
// réalisable SOUS le plafond d'investissement. C'est ce qu'on veut vraiment :
// « gagne-moi le plus possible avec le capital que j'ai ».
function budgetBatch(r, rev){
  if(!r.craft) return null;
  let best=null, fb=null;
  for(const b of allowedBatches(r)){
    const c=r.craft.cpc[b]; if(c==null) continue;
    const invest=c*Number(b);
    if(fb==null || invest<fb.invest) fb={batch:Number(b), cost:c, invest};   // repli : + petit capital
    if(MAX_INVEST!=null && invest>MAX_INVEST) continue;
    const benef = rev==null ? null : (rev-c)*Number(b);
    const score = benef==null ? -Infinity : benef;
    if(best==null || score>best.score) best={batch:Number(b), cost:c, score};
  }
  return best || fb;
}
// Coût de craft (cpc précalculé par Python). `batch` optionnel = force un mode
// (ex : tableau équipement en x1/x10) ; sinon le batch global.
function bCost(r, batch){
  batch = batch===undefined ? BATCH : batch;
  if(!r.craft) return r.Cout_HDV;
  if(batch==="smart"){ const s=smartBatch(r); return s?s.cost:null; }
  if(batch==="budget"){ const s=budgetBatch(r, r.Revenu_theo); return s?s.cost:null; }
  return r.craft.cpc[batch] ?? null;
}
function bBatchN(r, batch){
  batch = batch===undefined ? BATCH : batch;
  if(batch==="smart"){ const s=r.craft?smartBatch(r):null; return s?Number(s.batch):null; }
  if(batch==="budget"){ const s=r.craft?budgetBatch(r,r.Revenu_theo):null; return s?s.batch:null; }
  if(batch==="auto") return r.craft ? (r.craft.n_auto ?? null) : null;
  return Number(batch);
}
// Runes : qté d'une rune ciblée, total de runes prédites par craft.
function runeQty(r, code){ const x=(r.runes_detail||[]).find(u=>u.code===code); return x?x.qty:null; }
function totalRunes(r){ const d=r.runes_detail||[]; return d.length?d.reduce((a,u)=>a+u.qty,0):null; }
// Coeff appliqué à une ligne : réel s'il existe, sinon théorique.
function bCoeff(r){ return r.Coeff_Reel!=null ? r.Coeff_Reel : B.coeff; }
// Métriques recalculées pour le batch courant (revenu indépendant du batch).
// `batch` optionnel force un mode (tableau équipement) ; sinon batch global.
function deriveB(r, real, batch){
  const rev = real ? r.Revenu_reel : r.Revenu_theo;
  const cost = bCost(r, batch), base = r.Base_coeff100;
  return {
    rev, cost,
    benef: (rev==null||cost==null) ? null : rev-cost,
    rent:  (cost) ? rev/cost : null,
    cmin:  (cost!=null && base>0) ? cost/base*100 : null,
    rmoy:  (r.Prix_Moyen) ? rev/r.Prix_Moyen : null,
    batchN: bBatchN(r),
  };
}
const num = (v,suf="") => v==null ? '<span class="muted">—</span>' : fmt(v)+suf;
const dec2 = v => v==null ? '<span class="muted">—</span>' : (Math.round(v*100)/100).toFixed(2);
// CA (chiffre d'affaires) : prix de vente / revenu, en blanc gras pour repérer vite.
const caFmt = v => v==null ? '<span class="muted">—</span>' : `<b style="color:#fff">${fmt(v)}</b>`;
// Runes distinctes (pour le ciblage) et index ressource→crafts (pour « utilisé dans »).
const RUNES_AVAIL = (()=>{ const m={};
  (B.theo||[]).concat(B.real||[]).forEach(r=>(r.runes_detail||[]).forEach(u=>{ m[u.code]=u.nom; }));
  return Object.entries(m).sort((a,b)=>a[1].localeCompare(b[1],'fr')); })();
const USEDIN = (()=>{ const m={};
  (B.theo||[]).forEach(r=>{ if(r.craft&&r.craft.recipe) r.craft.recipe.forEach(ing=>{
    const k=normName(ing.nom); (m[k]=m[k]||[]).push(r); }); });
  return m; })();

// Recette de craft de l'item. Utilise la recette OPTIMISÉE de la ligne craft
// (tiers HDV + sous-crafts) quand elle existe → le total colle exactement au
// popup craft. Repli sur la recette catalogue (prix moyen) sinon.
function renderRecipe(it, host){
  if(!host) return;
  const row = (typeof craftRowOf==="function")?craftRowOf(it.gid):null;
  const rec = (row&&row.craft&&row.craft.recipe&&row.craft.recipe.length)
    ? row.craft.recipe
    : (it.recipe? it.recipe.map(([q,n])=>({nom:n,qty:q,tiers:null,craft_unit:null})) : null);
  if(!rec || !rec.length){ host.innerHTML=""; return; }
  let totOpt=0, totBuy=0, known=true;
  const body = rec.map(ing=>{
    const gid=NAMEGID[normName(ing.nom)];
    const it2=gid!=null?DTV.items.find(x=>x.gid===gid):null;
    const st=it2?statsOf(seriesOf(it2,"avg")):null;
    const bt = ing.tiers? bestTier(ing.tiers, ing.qty) : null;
    const buyUnit = bt? bt.unit : (st? st.last : null);
    const craftUnit = ing.craft_unit;
    let unit, mode='achat', gain=null;
    if(craftUnit!=null && (buyUnit==null || craftUnit<buyUnit)){ unit=craftUnit; mode='craft'; if(buyUnit!=null) gain=(buyUnit-craftUnit)*ing.qty; }
    else unit=buyUnit;
    const lineOpt = unit!=null? unit*ing.qty : null;
    const lineBuy = buyUnit!=null? buyUnit*ing.qty : lineOpt;
    if(lineOpt==null) known=false; else totOpt+=lineOpt;
    if(lineBuy!=null) totBuy+=lineBuy;
    const modeTag = mode==='craft'?'<span style="color:var(--accent2)">craft</span>':'<span class="muted">achat</span>';
    const attr=gid!=null?` style="cursor:pointer" data-ing="${gid}"`:'';
    return `<tr${attr}><td class="name">${ing.nom}</td><td class="narrow">${ing.qty}</td>`+
           `<td class="narrow">${st?fmt(st.last):_md}</td>`+
           `<td class="narrow">${unit!=null?fmt(unit):_md} ${modeTag}</td>`+
           `<td class="narrow">${lineOpt!=null?fmt(lineOpt):_md}</td>`+
           `<td class="narrow">${gain!=null?'<span style="color:var(--accent2)">+'+fmt(Math.round(gain))+'</span>':''}</td></tr>`;
  }).join("");
  host.innerHTML =
    `<h3 class="sec">🧪 Recette de ${it.nom}</h3>`+
    `<table><thead><tr><th class="name">Ingrédient</th><th class="narrow">Qté</th><th class="narrow" title="Dernier prix moyen">Moyen</th><th class="narrow" title="Prix unitaire retenu (achat ou sous-craft)">PU retenu</th><th class="narrow">Coût ligne</th><th class="narrow" title="Économie si on craft l'ingrédient au lieu de l'acheter">Gain craft</th></tr></thead><tbody>`+
    body+
    `<tr><td class="name"><b>Total optimisé</b></td><td></td><td></td><td></td><td class="narrow"><b style="color:#fff">${fmt(Math.round(totOpt))}${known?'':' ≈'}</b></td><td></td></tr>`+
    (Math.round(totBuy)!==Math.round(totOpt)?`<tr><td class="name muted">Total sans sous-craft (tout acheté)</td><td></td><td></td><td></td><td class="narrow muted">${fmt(Math.round(totBuy))}</td><td></td></tr>`:'')+
    `</tbody></table>`;
  host.querySelectorAll("tr[data-ing]").forEach(tr=>tr.onclick=()=>openPriceModal(+tr.dataset.ing));
}

// « Utilisé dans » : liste complète du catalogue (Utilise_dans) en chips
// cliquables ; repli sur l'index brisage si la donnée catalogue manque.
function renderUsedIn(it, host){
  if(!host) return;
  if(it.used_in && it.used_in.length){
    host.innerHTML =
      `<h3 class="sec">🔧 Utilisé dans <span class="muted">(${it.used_in.length})</span></h3>`+
      `<div class="usedchips">`+it.used_in.map(nom=>{ const gid=NAMEGID[normName(nom)];
        return gid!=null ? `<span class="chip" data-ing="${gid}">${nom}</span>` : `<span class="chip muted">${nom}</span>`;
      }).join("")+`</div>`;
    host.querySelectorAll("[data-ing]").forEach(el=>el.onclick=()=>openPriceModal(+el.dataset.ing));
    return;
  }
  const users = USEDIN[normName(it.nom)] || [];
  if(!users.length){ host.innerHTML=""; return; }
  const rows = users.map(r=>({r, d:deriveB(r, false)}))
    .filter(x=>x.d.cost!=null)
    .sort((a,b)=>(b.d.benef==null?-1e18:b.d.benef)-(a.d.benef==null?-1e18:a.d.benef))
    .slice(0, 6);
  if(!rows.length){ host.innerHTML=""; return; }
  host.innerHTML =
    `<h3 class="sec">⚒️ Crafts qui utilisent ${it.nom} <span class="muted">— les + rentables à briser</span></h3>`+
    `<table><thead><tr><th class="name">Item</th><th class="narrow">Bénéf</th><th class="narrow">C.min</th><th class="narrow">Rent</th></tr></thead><tbody>`+
    rows.map(x=>`<tr class="op" data-gid="${x.r.GID}" style="cursor:pointer"><td class="name">${x.r.Nom}</td>`+
      `<td class="narrow">${benFmt(x.d.benef)}</td><td class="narrow">${x.d.cmin==null?'—':fmt(x.d.cmin)+'%'}</td>`+
      `<td class="narrow">${x.d.rent==null?'—':x.d.rent.toFixed(2)}</td></tr>`).join("")+
    `</tbody></table>`;
  host.querySelectorAll("tr.op").forEach(tr=>tr.onclick=()=>{
    const r=B.theo.find(x=>x.GID==tr.dataset.gid); if(r) openBModal(r, false);
  });
}

function renderConcIn(it, host){
  if(!host) return;
  const rows = (typeof _CONC_ING_MAP!=="undefined" ? _CONC_ING_MAP : {})[it.gid] || [];
  if(!rows.length){ host.innerHTML=""; return; }
  host.innerHTML =
    `<h3 class="sec">🔨 Concassage utilisant ${it.nom}</h3>`+
    `<table><thead><tr><th class="name">Opération</th><th class="narrow">Bénéf/u</th><th class="narrow">Ratio</th></tr></thead><tbody>`+
    rows.map(r=>{ const d=deriveB(r,false);
      return `<tr class="op" style="cursor:pointer" data-gid="${r.GID}">`+
        `<td class="name">3 × ${r.from_nom} → 1 × ${r.Nom}</td>`+
        `<td class="narrow">${benFmt(d.benef)}</td>`+
        `<td class="narrow">${d.rent==null?'—':d.rent.toFixed(2)}</td></tr>`;
    }).join("")+
    `</tbody></table>`;
  host.querySelectorAll("tr.op").forEach(tr=>tr.onclick=()=>{
    const r=(RD.concassage||[]).find(x=>x.GID==tr.dataset.gid); if(r) openBModal(r,false);
  });
}

function brisageCols(real){
  const revLbl = real ? "Rev@réel" : `Rev@${B.coeff||100}%`;
  const bItem = r => DTV.items.find(it=>it.gid===r.GID);
  const cols = [];
  cols.push({k:"fav", l:"★", cls:"fav", sort:false, get:r=>0,
    fmt:r=>`<span class="star ${isFav(r.GID)?'on':''}" data-fav="${r.GID}">★</span>`});
  if(real) cols.push({k:"_mark", l:"", cls:"narrow", sort:false, get:r=>0,
    fmt:r=>(r._d.benef||0)>0?'<span style="color:var(--accent2)">✓</span>':'<span style="color:var(--bad)">✗</span>'});
  cols.push(
    {k:"Nom", l:"Nom", cls:"name", get:r=>r.Nom||("GID "+r.GID), fmt:r=>r.Nom||("GID "+r.GID)},
    {k:"Type", l:"Type", cls:"type", get:r=>r.Type||"", fmt:r=>r.Type||'<span class="muted">—</span>'},
    {k:"Niveau", l:"Niv", cls:"narrow", get:r=>r.Niveau, fmt:r=>r.Niveau},
    {k:"vol", l:"V", cls:"narrow", title:"Volume V : activité marché de l'item (0–10)",
      get:r=>{ const it=bItem(r); return it?volumeIndex(seriesOf(it,"avg")):null; },
      fmt:r=>{ const it=bItem(r); if(!it) return'<span class="muted">—</span>'; const v=volumeIndex(seriesOf(it,"avg")); return v==null?'<span class="muted">—</span>':(+v).toFixed(1); }},
    {k:"fresh", l:"F", cls:"narrow", title:"Fraîcheur HDV du dernier relevé réel de l'item. ● vert <3j · orange <10j · rouge",
      get:r=>{ const it=bItem(r); return hdvFreshDays(it); },
      fmt:r=>hdvFreshCell(bItem(r))},
    {k:"rev", l:revLbl, cls:"narrow", title:"Valeur des runes obtenues", get:r=>r._d.rev, fmt:r=>num(r._d.rev)},
    {k:"Prix_Moyen", l:"Prix moy", cls:"narrow", title:"Prix moyen de l'item fini à l'HDV (achat direct)", get:r=>r.Prix_Moyen, fmt:r=>num(r.Prix_Moyen)},
    {k:"cost", l:"Craft", cls:"narrow", title:"Coût de craft au batch courant (Σ ingrédients au meilleur tier)", get:r=>r._d.cost, fmt:r=>num(r._d.cost)},
    {k:"batchN", l:"Batch", cls:"narrow", title:"Nombre de crafts utilisé pour le coût (auto = estimé selon le coût)", get:r=>r._d.batchN, fmt:r=>r._d.batchN==null?'<span class="muted">—</span>':fmt(r._d.batchN)},
    {k:"cbatch", l:"C/Batch", cls:"narrow", title:"Coût total du batch (Craft × Batch) — capital à avancer", get:r=>r._d.cost==null||r._d.batchN==null?null:r._d.cost*r._d.batchN, fmt:r=>r._d.cost==null||r._d.batchN==null?'<span class="muted">—</span>':num(r._d.cost*r._d.batchN)},
    {k:"ca", l:"CA", cls:"narrow", title:"Chiffre d'affaires : valeur totale des runes du batch (revenu × Batch) — ce que tu encaisses", get:r=>r._d.rev==null||r._d.batchN==null?null:r._d.rev*r._d.batchN, fmt:r=>caFmt(r._d.rev==null||r._d.batchN==null?null:r._d.rev*r._d.batchN)},
    {k:"cmin", l:"C.min", cls:"narrow gold", title:"Coeff serveur minimal pour être rentable (plus bas = plus sûr)", get:r=>r._d.cmin, fmt:r=>r._d.cmin==null?'<span class="muted">—</span>':fmt(r._d.cmin)+"%"},
    {k:"benef", l:"Bénéf", cls:"narrow", title:"Bénéfice par unité (revenu runes − coût craft)", get:r=>r._d.benef, fmt:r=>benFmt(r._d.benef)},
    {k:"bbatch", l:"B×Batch", cls:"narrow", title:"Bénéfice total du batch (Bénéf × Batch)", get:r=>r._d.benef==null||r._d.batchN==null?null:r._d.benef*r._d.batchN, fmt:r=>benFmt(r._d.benef==null||r._d.batchN==null?null:r._d.benef*r._d.batchN)},
    {k:"rent", l:"Rent", cls:"narrow gold", title:"Rentabilité = revenu / coût de craft", get:r=>r._d.rent, fmt:r=>r._d.rent==null?'<span class="muted">—</span>':r._d.rent.toFixed(2)},
    {k:"rmoy", l:"R/moy", cls:"narrow gold", title:"Rentabilité si on ACHÈTE l'item au prix moyen et qu'on le brise (revenu / prix moyen)", get:r=>r._d.rmoy, fmt:r=>r._d.rmoy==null?'<span class="muted">—</span>':r._d.rmoy.toFixed(2)},
  );
  if(real) cols.push(
    {k:"Coeff_Reel", l:"C.réel", cls:"narrow gold", get:r=>r.Coeff_Reel, fmt:r=>r.Coeff_Reel==null?'—':fmt(r.Coeff_Reel)+"%"},
    {k:"Dernier_Brisage", l:"Brisé", cls:"narrow", get:r=>r.Dernier_Brisage||"", fmt:r=>r.Dernier_Brisage?dmy(r.Dernier_Brisage):'<span class="muted">—</span>'},
  );
  if(RUNETARGET){
    const lbl = (RUNES_AVAIL.find(x=>x[0]===RUNETARGET)||[,RUNETARGET])[1];
    cols.push({k:"runeq", l:lbl, cls:"narrow", title:"Quantité de la rune ciblée par craft (à 100%)",
      get:r=>runeQty(r,RUNETARGET), fmt:r=>dec2(runeQty(r,RUNETARGET))});
  }
  cols.push({k:"Runes", l:"Runes obtenues", cls:"runesb", sort:false, get:r=>r.Runes||"",
    fmt:r=>r.Runes||'<span class="muted">—</span>'});
  // Vue simplifiée : on masque les colonnes de référence/diagnostic (on garde
  // cmin, qui est aussi le tri par défaut).
  if(!BRIS_DETAIL){
    const HIDE = new Set(["Prix_Moyen","rmoy","Coeff_Reel","Dernier_Brisage"]);
    return cols.filter(c=>!HIDE.has(c.k));
  }
  return cols;
}
const BSORT = {};
// Batch forcé par tableau (ex : équipement en x1/x10 indépendant du global).
const BATCH_BY_HOST = {};
// colsFn optionnel : si fourni, remplace brisageCols (et désactive RUNETARGET filter).
function renderBTable(hostId, allRows, real, defaultSort, colsFn){
  const customCols = colsFn != null;
  colsFn = colsFn || brisageCols;
  let rows = allRows.filter(r=>!isArchived(r.GID));
  if(BFAVONLY) rows = rows.filter(r=>isFav(r.GID));
  if(RUNETARGET && !customCols) rows = rows.filter(r=>runeQty(r,RUNETARGET)!=null);
  const effBatch = BATCH_BY_HOST[hostId];   // undefined = batch global
  rows.forEach(r=>{ r._d = deriveB(r, real, effBatch); });   // recalcul au batch (forcé ou global)
  // Filtres globaux capital max / bénéfice min (par batch).
  rows = rows.filter(r=>{
    const invest = (r._d.cost!=null&&r._d.batchN!=null) ? r._d.cost*r._d.batchN : null;
    let benefB;
    if(r.is_concassage){ const it=DTV.items.find(x=>x.gid===r.GID), b=it?bestSell(it,r.GID):null;
      benefB = (b&&r._d.cost!=null&&r._d.batchN!=null) ? (b.unit-r._d.cost)*r._d.batchN : null; }
    else benefB = (r._d.benef!=null&&r._d.batchN!=null) ? r._d.benef*r._d.batchN : null;
    return passInvestBenef(invest, benefB);
  });
  const cols = colsFn(real);
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
  // Coloration rentabilité : concassage = meilleur lot autorisé, brisage = bénéf courant.
  const profOf = r=>{
    if(r.is_concassage){ const it=DTV.items.find(x=>x.gid===r.GID), b=it?bestSell(it,r.GID):null;
      return (b&&r._d.cost!=null)?b.unit-r._d.cost:null; }
    return r._d.benef;
  };
  const body = sorted.map(r=>{
    const p=profOf(r), pc=p==null?'':(p>0?'prof-pos':p<0?'prof-neg':'');
    return `<tr class="${pc}" data-gid="${r.GID}" data-real="${real?1:0}">`+
      cols.map(c=>`<td class="${c.cls||''}">${c.fmt(r)}</td>`).join("")+"</tr>";
  }).join("");
  document.getElementById(hostId).innerHTML =
    `<div class="tablewrap"><table><thead><tr>${head}</tr></thead><tbody>${body||`<tr><td>—</td></tr>`}</tbody></table></div>`;
  const _rerender = ()=>renderBTable(hostId, allRows, real, defaultSort, customCols?colsFn:undefined);
  document.querySelector(`#${hostId} thead`).addEventListener("click", e=>{
    const th=e.target.closest("th"); if(!th||th.dataset.sort==="false"||!th.dataset.k) return;
    const k=th.dataset.k;
    if(srt.k===k) srt.dir*=-1; else BSORT[hostId]={k, dir:(k==="Nom"||k==="Type")?1:-1};
    _rerender();
  });
  document.querySelector(`#${hostId} tbody`).addEventListener("click", e=>{
    const star=e.target.closest(".star");
    if(star){ const gid=+star.dataset.fav; toggleFav(gid); star.classList.toggle("on",isFav(gid));
      renderListControls(); if(BFAVONLY) _rerender(); return; }
    const tr=e.target.closest("tr"); if(!tr||!tr.dataset.gid) return;
    const row=allRows.find(x=>x.GID==tr.dataset.gid);
    if(row) openItemDetail(row, real);
  });
}
let MODAL_CTX = null;
function batchSelectorHTML(){
  const lbl = b => b==="auto" ? "auto" : b==="smart" ? "🧠 smart" : b==="budget" ? "💰 budget" : "x"+b;
  const tip = b => b==='smart' ? 'meilleure marge unitaire (gros lot)'
    : b==='budget' ? 'bénéfice total maxi sous le plafond d\'investissement' : '';
  return '<span class="batchsel">'+BATCHES.map(b=>
    `<button data-b="${b}" class="${b===BATCH?'on':''}" title="${tip(b)}">${lbl(b)}</button>`).join("")+'</span>';
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
  const runeOpts = `<option value="">toutes</option>`+RUNES_AVAIL.map(([c,n])=>
    `<option value="${c}"${c===RUNETARGET?' selected':''}>${n}</option>`).join("");
  root.innerHTML =
    `<div class="notice">`+
    `<span title="Entonnoir : catalogue → items avec un effet brisable → chiffrables (revenu runes ET coût de craft connus)">`+
      `<b>${fmt(B.n_ranked)}</b> chiffrables · ${fmt(B.n_breakable!=null?B.n_breakable:B.n_ranked)} brisables · ${fmt(B.n_catalog)} catalogue</span>`+
    (B.n_recipes!=null?`<span title="Items du catalogue ayant une recette exploitable. Le 2e nombre = items brisables SANS recette (trou de scraping à combler côté catalogue).">📋 <b>${fmt(B.n_recipes)}</b> recettes${B.n_breakable_norecipe?` · <span class="bad">${fmt(B.n_breakable_norecipe)} brisables sans recette</span>`:''}</span>`:'')+
    `<span>${costTag}</span><span>${runeTag}</span>`+
    `<span>coeff théo <b>${B.coeff}%</b></span>`+
    `<label class="chk muted"><input type="checkbox" id="bFav"${BFAVONLY?' checked':''}> ★ favoris</label>`+
    `<label class="muted">Rune ciblée <select id="bRune">${runeOpts}</select></label>`+
    `<button class="btn" id="brisDetail">${BRIS_DETAIL?'Vue simple':'Toutes les colonnes'}</button>`+
    `<span style="margin-left:auto">Batch ${batchSelectorHTML()}</span></div>`+
    // Brisages réels EN PREMIER (watchlist : ce qui est rentable maintenant).
    (hasReal
      ? `<h3 class="sec">🎯 Brisages réels <span class="muted">— coeff observé en jeu appliqué (${B.n_real})</span></h3><div id="breal"></div>`
      : `<h3 class="sec">🎯 Brisages réels</h3><div class="empty">Aucune observation de coefficient en jeu pour l'instant (capture en cours de remplissage).</div>`)+
    `<h3 class="sec">🏆 Top théorique <span class="muted">— ${B.sort_label} · clique une ligne pour le détail</span></h3><div id="btheo"></div>`;
  root.querySelector(".batchsel").addEventListener("click", e=>{
    const btn=e.target.closest("button"); if(!btn) return;
    BATCH=btn.dataset.b; renderBrisage(); if(MODAL_CTX) openBModal(MODAL_CTX.r, MODAL_CTX.real);
  });
  document.getElementById("bFav").addEventListener("change", e=>{ BFAVONLY=e.target.checked; renderBrisage(); });
  document.getElementById("bRune").addEventListener("change", e=>{ RUNETARGET=e.target.value; renderBrisage(); });
  document.getElementById("brisDetail").addEventListener("click", ()=>{ BRIS_DETAIL=!BRIS_DETAIL; renderBrisage(); });
  if(hasReal) renderBTable("breal", B.real, true, {k:"benef", dir:-1});
  renderBTable("btheo", B.theo, false, {k:"cmin", dir:1});
}

// ── Onglet « Craft (revente) » ─────────────────────────────────────────────
const CR = DTV.craft || {available:false};
const CRAFTMAP = (()=>{ const m={}; [...(CR.rows_other||[]),...(CR.rows_equip||[])].forEach(r=>{ if(r.GID!=null && m[r.GID]==null) m[r.GID]=r; }); return m; })();
let CRAFT_DETAIL=false, CRAFT_Q="", EQUIP_BATCH="1";   // équipement : x1 ou x10 (indépendant)
function renderCraft(){
  const root=document.getElementById("craftsell-root");
  if(!CR.available){ root.innerHTML=`<div class="soon"><div class="big">🛠️</div><p>${CR.reason||'Pas de données de craft.'}</p></div>`; return; }
  const costTag = CR.craft_mode ? '<span class="tag ok">coût = craft (tiers HDV optimisés)</span>'
                                : '<span class="tag warn">coût = craft (avgprices, sans optim. tiers)</span>';
  const q=CRAFT_Q.trim().toLowerCase();
  const filt = rows => q ? rows.filter(r=>(r.Nom||"").toLowerCase().includes(q)||String(r.GID).includes(q)) : rows;
  const other = filt(CR.rows_other||[]), equip = filt(CR.rows_equip||[]);
  root.innerHTML =
    `<div class="help">🛠️ <b>Craft (revente).</b> Crafter un item puis le <b>revendre</b> au marché (sans brisage). `+
    `<b>C/Batch</b> = capital · <b>CA</b> = ce que tu encaisses · <b>B×Batch</b> = bénéfice. Ligne <b style="color:var(--accent2)">verte</b> = rentable. `+
    `Le batch <b>💰 budget</b> respecte ton plafond. <b>Équipements</b> : craft par 1 ou 10 seulement (auto en smart/budget). Clique un item → détail + graphe.</div>`+
    `<div class="notice"><span><b>${fmt(CR.n_craftable)}</b> items craftables chiffrables</span><span>${costTag}</span>`+
    `<label class="chk muted"><input type="checkbox" id="cFav"${BFAVONLY?' checked':''}> ★ favoris</label>`+
    `<input id="cQ" type="search" placeholder="Rechercher (Entrée)…" value="${q.replace(/"/g,'&quot;')}" style="width:170px">`+
    `<button class="btn" id="cQbtn">🔍</button>`+
    `<button class="btn" id="craftDetail">${CRAFT_DETAIL?'Vue simple':'Toutes les colonnes'}</button>`+
    `<span style="margin-left:auto">Batch ${batchSelectorHTML()}</span></div>`+
    `<h3 class="sec">📦 Ressources & consommables <span class="muted">— ${other.length}</span></h3><div id="craft-other-tbl"></div>`+
    `<h3 class="sec">🛡️ Équipement & armes <span class="muted">— ${equip.length}</span></h3>`+
    `<div class="controls" style="margin:2px 0 6px"><span class="muted">Batch équip :</span> `+
      `<span class="batchsel" id="equipBatch">`+["1","10"].map(b=>`<button data-eb="${b}" class="${b===EQUIP_BATCH?'on':''}">x${b}</button>`).join("")+`</span>`+
      `<span class="muted">— un équipement se craft rarement en masse</span></div>`+
    `<div id="craft-equip-tbl"></div>`;
  root.querySelector(".batchsel").addEventListener("click", e=>{ const btn=e.target.closest("button"); if(!btn) return;
    BATCH=btn.dataset.b; renderCraft(); if(MODAL_CTX) openBModal(MODAL_CTX.r, MODAL_CTX.real); });
  document.getElementById("cFav").addEventListener("change", e=>{ BFAVONLY=e.target.checked; renderCraft(); });
  const doQ=()=>{ CRAFT_Q=document.getElementById("cQ").value; renderCraft(); };
  document.getElementById("cQbtn").onclick=doQ;
  document.getElementById("cQ").addEventListener("change", doQ);   // valide à Entrée/sortie de champ
  document.getElementById("craftDetail").addEventListener("click", ()=>{ CRAFT_DETAIL=!CRAFT_DETAIL; renderCraft(); });
  document.getElementById("equipBatch").addEventListener("click", e=>{ const btn=e.target.closest("button"); if(!btn) return;
    EQUIP_BATCH=btn.dataset.eb; BATCH_BY_HOST["craft-equip-tbl"]=EQUIP_BATCH; renderCraft(); });
  BATCH_BY_HOST["craft-equip-tbl"]=EQUIP_BATCH;   // le tableau équipement ignore le batch global
  renderBTable("craft-other-tbl", other, false, {k:"bbatch",dir:-1}, craftCols);
  renderBTable("craft-equip-tbl", equip, false, {k:"bbatch",dir:-1}, craftCols);
}

// ── Onglet « 🧺 Ma liste » (panier de craft + liste d'achats) ──────────────
let CRAFTLIST = (()=>{ try{ return JSON.parse(localStorage.getItem("dtv_craftlist"))||[]; }catch(e){ return []; } })();
function saveCraftList(){ try{ localStorage.setItem("dtv_craftlist", JSON.stringify(CRAFTLIST)); }catch(e){} }
// Retrouve la ligne (craft / brisage / concassage) d'un GID.
function craftRowOf(gid){ return (typeof CRAFTMAP!=="undefined"&&CRAFTMAP[gid])
  || (typeof BRISMAP!=="undefined"&&BRISMAP[gid])
  || ((typeof RD!=="undefined"&&RD.concassage)?RD.concassage.find(x=>x.GID===gid):null); }
function addToCraftList(gid, qty){ qty=Math.max(1,Math.round(qty||1));
  const e=CRAFTLIST.find(x=>x.gid===gid); if(e) e.qty+=qty; else CRAFTLIST.push({gid,qty});
  saveCraftList(); renderCraftList(); updateListBadge(); }
function setCraftQty(gid, qty){ const e=CRAFTLIST.find(x=>x.gid===gid); if(!e) return;
  qty=Math.max(1,Math.round(qty||1)); e.qty=qty; saveCraftList(); renderCraftList(); }
function removeFromCraftList(gid){ CRAFTLIST=CRAFTLIST.filter(x=>x.gid!==gid); saveCraftList(); renderCraftList(); updateListBadge(); }
function updateListBadge(){ const b=document.querySelector('nav.tabs button[data-go="liste"]');
  if(b) b.textContent = "🧺 Ma liste" + (CRAFTLIST.length?` (${CRAFTLIST.length})`:""); }
let LIST_RECURSE=true;   // décomposer les sous-crafts quand c'est moins cher
// Meilleur tier d'ACHAT d'un ingrédient : prix unitaire le plus bas.
function bestBuyTier(it){
  let best=null;
  ["x1","x10","x100","x1000"].forEach(src=>{ const st=statsOf(seriesOf(it,src)); if(!st||!(st.last>0)) return;
    const u=st.last/LOTSIZE[src]; if(best==null||u<best.unit) best={tier:src, unit:u}; });
  if(best==null){ const a=avgUnit(it); if(a!=null) best={tier:"avg", unit:a}; }
  return best;
}
// Ajoute un ingrédient à la liste d'achats, en décomposant récursivement les
// sous-crafts quand crafter l'ingrédient revient moins cher que l'acheter.
function expandIngredient(nom, qty, shop, depth){
  const k=normName(nom), gid=NAMEGID[k];
  const it=gid!=null?DTV.items.find(x=>x.gid===gid):null;
  if(LIST_RECURSE && it && it.recipe && it.recipe.length && depth<6){
    const buy=bestBuyTier(it);
    let craftCost=0, ok=true;
    for(const [q,n] of it.recipe){ const g2=NAMEGID[normName(n)], i2=g2!=null?DTV.items.find(x=>x.gid===g2):null;
      const bt2=i2?bestBuyTier(i2):null; if(!bt2){ ok=false; break; } craftCost+=q*bt2.unit; }
    if(ok && (buy==null || craftCost<buy.unit)){   // crafter l'ingrédient est moins cher → décomposer
      for(const [q,n] of it.recipe) expandIngredient(n, q*qty, shop, depth+1);
      return;
    }
  }
  const s=shop[k]||(shop[k]={nom, gid, qty:0}); s.qty+=qty;
}
function renderCraftList(){
  const root=document.getElementById("liste-root"); if(!root) return;
  const intro = `<div class="help">🧺 <b>Ma liste de craft.</b> Ajoute des items depuis leur popup (bouton « ➕ Ma liste » + quantité). `+
    `La liste s'accumule (persistée) et agrège <b>tous les ingrédients à acheter</b> en une seule liste — même avec plusieurs items différents, tu ne te trompes pas.</div>`;
  if(!CRAFTLIST.length){ root.innerHTML=intro+'<div class="empty">Liste vide.</div>'; return; }
  const shop={}; let totCost=0, totCA=0, totBenef=0;
  const itemRows = CRAFTLIST.map(e=>{
    const r=craftRowOf(e.gid);
    const nom = r?r.Nom:(DTV.items.find(x=>x.gid===e.gid)||{}).nom||("GID "+e.gid);
    if(!r) return `<tr><td class="name">${nom}</td><td><input type="number" min="1" value="${e.qty}" data-qty="${e.gid}" style="width:70px"></td>`+
      `<td colspan="3" class="muted">ligne craft indisponible</td><td><button class="btn" data-rm="${e.gid}">✕</button></td></tr>`;
    const d=deriveB(r,false);
    const cost=d.cost!=null?d.cost*e.qty:null, ca=d.rev!=null?d.rev*e.qty:null;
    const benef=(ca!=null&&cost!=null)?ca-cost:null;
    if(cost!=null) totCost+=cost; if(ca!=null) totCA+=ca; if(benef!=null) totBenef+=benef;
    ((r.craft&&r.craft.recipe)||[]).forEach(ing=> expandIngredient(ing.nom, ing.qty*e.qty, shop, 0));
    return `<tr style="cursor:pointer" data-open="${e.gid}"><td class="name">${nom}</td>`+
      `<td><input type="number" min="1" value="${e.qty}" data-qty="${e.gid}" style="width:70px" onclick="event.stopPropagation()"></td>`+
      `<td class="narrow">${num(cost)}</td><td class="narrow">${caFmt(ca)}</td><td class="narrow">${benFmt(benef)}</td>`+
      `<td><button class="btn" data-rm="${e.gid}" onclick="event.stopPropagation()">✕</button></td></tr>`;
  }).join("");
  // Liste d'achats agrégée (tier d'achat conseillé = prix unitaire le + bas).
  let shopCost=0; const shopRows=Object.values(shop).sort((a,b)=>a.nom.localeCompare(b.nom,'fr')).map(s=>{
    const it=s.gid!=null?DTV.items.find(x=>x.gid===s.gid):null;
    const bt=it?bestBuyTier(it):null, u=bt?bt.unit:null;
    const tierLbl = bt?(bt.tier==="avg"?'<span class="muted">moyen</span>':bt.tier):_md;
    const fcell = it?hdvFreshCell(it):_md;
    const line=u!=null?u*s.qty:null; if(line!=null) shopCost+=line;
    const attr=s.gid!=null?` style="cursor:pointer" data-ing="${s.gid}"`:'';
    return `<tr${attr}><td class="name">${s.nom}</td><td class="narrow">${fmt(s.qty)}</td>`+
      `<td class="narrow">${tierLbl}</td><td class="narrow">${u!=null?fmt(u):_md}</td><td class="narrow">${fcell}</td>`+
      `<td class="narrow">${line!=null?fmt(line):_md}</td></tr>`;
  }).join("");
  root.innerHTML = intro+
    `<div class="controls"><button class="btn" id="clearList">🗑 Vider la liste</button>`+
    `<label class="chk muted"><input type="checkbox" id="listRec"${LIST_RECURSE?' checked':''}> décomposer les sous-crafts (récursif)</label>`+
    `<span class="muted">Coût total ${num(totCost)} · CA total <b style="color:#fff">${fmt(totCA)}</b> · Bénéfice total ${benFmt(totBenef)}</span></div>`+
    `<h3 class="sec">📋 Items à crafter</h3>`+
    `<div class="tablewrap"><table><thead><tr><th class="name">Item</th><th>Qté</th><th class="narrow">Coût total</th><th class="narrow">CA total</th><th class="narrow">Bénéf total</th><th></th></tr></thead><tbody id="listItems">${itemRows}</tbody></table></div>`+
    `<h3 class="sec">🛒 Ingrédients à acheter <span class="muted">— agrégé · tier d'achat conseillé</span></h3>`+
    `<div class="tablewrap"><table><thead><tr><th class="name">Ingrédient</th><th class="narrow">Qté totale</th><th class="narrow" title="Tier de lot au prix unitaire le plus bas">Tier conseillé</th><th class="narrow">Prix/u</th><th class="narrow" title="Fraîcheur HDV">F</th><th class="narrow">Coût ligne</th></tr></thead><tbody id="shopRows">${shopRows}`+
    `<tr><td class="name"><b>Total achats</b></td><td></td><td></td><td></td><td></td><td class="narrow"><b style="color:#fff">${fmt(Math.round(shopCost))}</b></td></tr>`+
    `</tbody></table></div>`;
  document.getElementById("clearList").onclick=()=>{ if(confirm("Vider toute la liste ?")){ CRAFTLIST=[]; saveCraftList(); renderCraftList(); updateListBadge(); } };
  document.getElementById("listRec").onchange=e=>{ LIST_RECURSE=e.target.checked; renderCraftList(); };
  root.querySelectorAll("input[data-qty]").forEach(inp=>inp.onchange=()=>setCraftQty(+inp.dataset.qty, +inp.value));
  root.querySelectorAll("button[data-rm]").forEach(b=>b.onclick=()=>removeFromCraftList(+b.dataset.rm));
  root.querySelectorAll("tr[data-open]").forEach(tr=>tr.onclick=()=>{ const r=craftRowOf(+tr.dataset.open); if(r) openItemDetail(r,false); });
  root.querySelectorAll("#shopRows tr[data-ing]").forEach(tr=>tr.onclick=()=>openPriceModal(+tr.dataset.ing));
}

// ── Onglet « ⭐ Favoris » ───────────────────────────────────────────────────
const FAV_INTENTS = [["prix","📈 Prix dans le temps"],["brisage","⚒️ Craft & Brisage"],["craft","🛠️ Craft (revente)"],["arbitrage","💱 Achat/Vente"],["runes","🔮 Runes"]];
function renderFavoris(){
  const root=document.getElementById("favoris-root"); if(!root) return;
  const intro=`<div class="help">⭐ <b>Favoris (liste « ${ACTIVE} »).</b> Pour chaque item : choisis ton <b>intention</b> (à quel onglet il appartient) et prends une <b>note</b> (ex : « attendre que le fer descende »). Clique le nom pour l'ouvrir dans le bon contexte.</div>`;
  const gids=(LISTS[ACTIVE]||[]).filter(g=>!isArchived(g));
  if(!gids.length){ root.innerHTML=intro+'<div class="empty">Aucun favori dans cette liste. Ajoute-en via le bouton ☆ Favori d\'un graphe.</div>'; return; }
  const rows=gids.map(g=>{ const it=DTV.items.find(x=>x.gid===g); if(!it) return "";
    const m=favMeta(g), st=statsOf(seriesOf(it,"avg"));
    const opts=FAV_INTENTS.map(([v,l])=>`<option value="${v}"${m.intent===v?' selected':''}>${l}</option>`).join("");
    return `<tr><td class="fav"><span class="star on" data-fav="${g}">★</span></td>`+
      `<td class="name" style="cursor:pointer" data-open="${g}">${it.nom}</td><td class="type">${it.type||_md}</td>`+
      `<td class="narrow">${st?fmt(st.last):_md}</td>`+
      `<td><select data-intent="${g}">${opts}</select></td>`+
      `<td><input type="text" data-note="${g}" value="${(m.note||'').replace(/"/g,'&quot;')}" placeholder="note…" style="width:240px"></td></tr>`;
  }).join("");
  root.innerHTML=intro+
    `<div class="tablewrap"><table><thead><tr><th class="fav">★</th><th class="name">Item</th><th class="type">Type</th><th class="narrow">Prix moyen</th><th>Intention</th><th>Note</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  root.querySelectorAll("select[data-intent]").forEach(s=>s.onchange=()=>{ favMeta(+s.dataset.intent).intent=s.value; saveFavMeta(); });
  root.querySelectorAll("input[data-note]").forEach(i=>i.onchange=()=>{ favMeta(+i.dataset.note).note=i.value; saveFavMeta(); });
  root.querySelectorAll(".star[data-fav]").forEach(s=>s.onclick=()=>{ toggleFav(+s.dataset.fav); renderListControls(); renderFavoris(); });
  root.querySelectorAll("[data-open]").forEach(td=>td.onclick=()=>{ const g=+td.dataset.open, m=favMeta(g), cr=craftRowOf(g);
    if((m.intent==="brisage"||m.intent==="craft") && cr) openItemDetail(cr,false); else openPriceModal(g); });
}

// ── Onglet « 🗄 Archives » ──────────────────────────────────────────────────
function renderArchives(){
  const root=document.getElementById("archives-root"); if(!root) return;
  const intro=`<div class="help">🗄 <b>Archives.</b> Les items et types archivés restent <b>relevés</b> (prix suivis) mais <b>disparaissent de tous les tableaux</b>. Pratique pour masquer ce qui n'a aucun intérêt (ex : « Potion d'oubli Percepteur », V ≈ 0).</div>`;
  const typeRows=ARCHIVE.types.length?ARCHIVE.types.map(t=>`<tr><td class="name">${t}</td><td><button class="btn" data-unarchtype="${t.replace(/"/g,'&quot;')}">Désarchiver</button></td></tr>`).join(""):'<tr><td colspan="2" class="muted">Aucun type archivé.</td></tr>';
  const itemRows=ARCHIVE.items.length?ARCHIVE.items.map(g=>{ const it=DTV.items.find(x=>x.gid===g); return `<tr><td class="name">${it?it.nom:("GID "+g)}</td><td class="type">${(it&&it.type)||_md}</td><td><button class="btn" data-unarchit="${g}">Désarchiver</button></td></tr>`; }).join(""):'<tr><td colspan="3" class="muted">Aucun item archivé.</td></tr>';
  root.innerHTML=intro+
    `<h3 class="sec">Types archivés <span class="muted">— ${ARCHIVE.types.length}</span></h3>`+
    `<div class="tablewrap"><table><thead><tr><th class="name">Type</th><th></th></tr></thead><tbody>${typeRows}</tbody></table></div>`+
    `<h3 class="sec">Items archivés <span class="muted">— ${ARCHIVE.items.length}</span></h3>`+
    `<div class="tablewrap"><table><thead><tr><th class="name">Item</th><th class="type">Type</th><th></th></tr></thead><tbody>${itemRows}</tbody></table></div>`;
  root.querySelectorAll("[data-unarchtype]").forEach(b=>b.onclick=()=>{ unarchiveType(b.dataset.unarchtype); renderArchives(); refreshActiveTab(); });
  root.querySelectorAll("[data-unarchit]").forEach(b=>b.onclick=()=>{ unarchiveItem(+b.dataset.unarchit); renderArchives(); refreshActiveTab(); });
}

// ── Modale de détail (recette + tiers + runes + craft vs achat) ─────────────
function equipBatchSelHTML(){ return '<span class="batchsel">'+["1","10"].map(b=>
  `<button data-eb="${b}" class="${b===EQUIP_BATCH?'on':''}">x${b}</button>`).join("")+'</span>'; }
function openBModal(r, real){
  if(!r) return;
  MODAL_CTX = {r, real};
  const useBatch = r.is_equip ? EQUIP_BATCH : undefined;
  const d = deriveB(r, real, useBatch);
  const c = r.craft;
  const batchN = d.batchN;
  // Lignes de recette au batch courant (best_tier porté de craft.py).
  let recipeRows = '<tr><td colspan="10" class="muted">Recette indisponible (item non craftable ou prix manquants).</td></tr>';
  if(c && c.recipe && c.recipe.length && batchN){
    let recCraft=0, recBatch=0, recKnown=true, recBuyBatch=0;
    recipeRows = c.recipe.map(ing=>{
      const need = ing.qty * batchN;
      const bt = bestTier(ing.tiers, need);
      const buy = bt ? bt.unit : null, alt = ing.craft_unit;
      // miroir de craft_plan : moins cher entre acheter (tier) et crafter l'ingrédient
      let tier, unit, info, gain=null;
      if(buy!=null && (alt==null || buy<=alt)){ tier="x"+bt.tier; unit=buy; info=`(${Math.ceil(need/bt.tier)} ach.)`; }
      else if(alt!=null){ tier='<span style="color:var(--accent2)">craft</span>'; unit=alt; info=""; if(buy!=null) gain=(buy-alt)*need; }
      const ingGid = NAMEGID[normName(ing.nom)];
      const it2 = ingGid!=null?DTV.items.find(x=>x.gid===ingGid):null;
      const stA = it2?statsOf(seriesOf(it2,"avg")):null;
      const moy = stA?fmt(stA.last):'<span class="muted">—</span>', med = stA?fmt(stA.avg):'<span class="muted">—</span>';
      const ingStyle = ingGid ? ' style="cursor:pointer" title="Cliquer pour voir le graphe de prix"' : '';
      const ingAttr = ingGid ? ` data-ing="${ingGid}"` : '';
      if(buy==null && alt==null){ recKnown=false;
        return `<tr${ingAttr}${ingStyle}><td>${ing.nom}</td><td>${ing.qty}</td><td>${fmt(need)}</td><td colspan="2" class="bad">prix inconnu</td><td>${moy}</td><td>${med}</td><td colspan="3" class="bad">—</td></tr>`; }
      const lineCraft=ing.qty*unit, lineBatch=need*unit; recCraft+=lineCraft; recBatch+=lineBatch;
      recBuyBatch += (buy!=null?buy:unit)*need;   // total si tout acheté (sans sous-craft)
      return `<tr${ingAttr}${ingStyle}><td>${ing.nom}</td><td>${ing.qty}</td><td>${fmt(need)}</td>`+
             `<td>${tier}</td><td>${fmt(unit)}</td><td>${moy}</td><td>${med}</td>`+
             `<td>${fmt(lineCraft)} <span class="muted">${info}</span></td><td>${fmt(lineBatch)}</td>`+
             `<td>${gain!=null?'<span style="color:var(--accent2)">+'+fmt(Math.round(gain))+'</span>':''}</td></tr>`;
    }).join("")+
    `<tr><td class="name"><b>Total craft</b></td><td></td><td></td><td></td><td></td><td></td><td></td>`+
    `<td><b style="color:#fff">${fmt(recCraft)}${recKnown?'':' ≈'}</b></td>`+
    `<td><b style="color:#fff">${fmt(recBatch)}${recKnown?'':' ≈'}</b></td><td></td></tr>`+
    (Math.round(recBuyBatch)!==Math.round(recBatch)?`<tr><td class="name muted">Total sans sous-craft (tout acheté)</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td class="muted">${fmt(Math.round(recBuyBatch))}</td><td></td></tr>`:'');
  }
  const isCon = !!r.is_concassage;
  // Coeff appliqué dans ce contexte de table (réel si tableau réel, sinon théo).
  const mcoeff = real ? r.Coeff_Reel : B.coeff;
  // Concassage : prix de vente = meilleur lot autorisé (règle relevé <3j), sinon prix moyen.
  const cResIt = (isCon && r.GID) ? DTV.items.find(it=>it.gid===r.GID) : null;
  const cBest  = cResIt ? bestSell(cResIt, r.GID) : null;
  const cSellU = isCon ? (cBest ? cBest.unit : r.Prix_Moyen) : d.rev;
  const cBenef = isCon ? ((cSellU!=null&&d.cost!=null)?cSellU-d.cost:null) : d.benef;
  const cRent  = isCon ? ((cSellU!=null&&d.cost)?cSellU/d.cost:null) : d.rent;
  const cLotLbl= cBest ? cBest.src : 'moyen';
  // Section inférieure : "Runes obtenues" pour brisage, "Résultat" pour concassage.
  let bottomSection;
  if(isCon){
    const resIt = r.GID ? DTV.items.find(it=>it.gid===r.GID) : null;
    const tierRows = resIt ? ["x1","x10","x100","x1000"].map(src=>{
      const st=statsOf(seriesOf(resIt,src)); if(!st) return "";
      return `<tr><td>${TIER_LABEL[src]}</td><td>${fmt(st.last)}</td><td>${fmt(st.last/TIER_DIV[src])}/u</td></tr>`;
    }).join("") : "";
    bottomSection =
      `<h3 class="sec">Résultat : 1 × ${r.Nom}</h3>`+
      `<table><thead><tr><th>Source</th><th>Prix lot</th><th>Prix/u</th></tr></thead><tbody>`+
      `<tr><td>Prix moyen</td><td colspan="2">${num(r.Prix_Moyen)}</td></tr>`+
      (tierRows || `<tr><td colspan="3" class="muted">Pas de relevé HDV pour cette rune</td></tr>`)+
      `</tbody></table>`;
  } else {
    let runeValTot=0, runeQtyTot=0;
    const runeRows = (r.runes_detail&&r.runes_detail.length)
      ? r.runes_detail.map(x=>{
          const qc = mcoeff!=null ? x.qty*mcoeff/100 : null;
          const qBatch = qc!=null&&batchN ? qc*batchN : null;
          const val = qc!=null?qc*x.price:null, valBatch = qBatch!=null?qBatch*x.price:null;
          if(valBatch!=null){ runeValTot+=valBatch; runeQtyTot+=qBatch; }
          return `<tr><td>${x.nom} <span class="muted">(${x.code})</span></td><td>${dec2(x.qty)}</td>`+
                 `<td>${dec2(qc)}</td><td>${qBatch==null?'—':dec2(qBatch)}</td><td>${fmt(x.price)}</td>`+
                 `<td>${val==null?'—':fmt(val)}</td><td>${valBatch==null?'—':fmt(valBatch)}</td></tr>`;
        }).join("")
      : '<tr><td colspan="7" class="muted">—</td></tr>';
    bottomSection =
      `<h3 class="sec">Runes obtenues <span class="muted">— au coeff ${mcoeff!=null?mcoeff+'%':'?'} · pour ${batchN||1} brisage(s)</span></h3>`+
      `<table><thead><tr><th class="name">Rune</th><th title="Par brisage à 100%">Qté @100%</th><th title="Par brisage au coeff">Qté @coeff</th><th title="Total récupéré sur le batch">Qté ×Batch</th><th>Prix u.</th><th title="Valeur par brisage">Valeur/u</th><th title="Valeur totale du batch">Valeur ×Batch</th></tr></thead><tbody>${runeRows}`+
      (r.runes_detail&&r.runes_detail.length?`<tr><td class="name"><b>Total runes</b></td><td></td><td></td><td><b>${dec2(runeQtyTot)}</b></td><td></td><td></td><td><b style="color:#fff">${fmt(runeValTot)}</b></td></tr>`:'')+
      `</tbody></table>`;
  }
  // Verdict : concassage → acheter 3 simples vs acheter 1 Pa directement.
  let verdict = "";
  if(d.cost!=null && (isCon ? cSellU!=null : r.Prix_Moyen!=null)){
    if(isCon){
      const profitable = cSellU > d.cost;
      verdict = `<div class="verdict ${profitable?'craft':'buy'}">${profitable
        ? `💡 <b>Concasser</b> (coût ${fmt(d.cost)}/u) puis revendre en lot ${cLotLbl} à ${fmt(cSellU)}/u → bénéfice ${benFmt(cBenef)}/u.`
        : `🛒 <b>Pas rentable</b> : concasser coûte ${fmt(d.cost)}/u pour une revente à ${fmt(cSellU)}/u (lot ${cLotLbl}).`}</div>`;
    } else {
      const buy = r.Prix_Moyen < d.cost;
      verdict = `<div class="verdict ${buy?'buy':'craft'}">${buy
        ? `💡 <b>Acheter</b> l'item fini (${fmt(r.Prix_Moyen)}) est moins cher que le crafter (${fmt(d.cost)}).`
        : `⚒️ <b>Crafter</b> (${fmt(d.cost)}) est moins cher qu'acheter l'item fini (${fmt(r.Prix_Moyen)}).`}</div>`;
    }
  }
  const subLine = isCon
    ? `3 × ${r.from_nom} → 1 × ${r.Nom}`
    : `GID ${r.GID} · niv ${r.Niveau}${r.Type?' · '+r.Type:''}${real?` · coeff réel ${r.Coeff_Reel}%`:` · coeff théo ${B.coeff}%`}`;
  const box=document.getElementById("bmodal-box");
  box.innerHTML =
    `<span class="x" id="bmodal-x">✕</span>`+
    `<h3${r.GID?' class="modtitle" id="bmodal-title" title="Voir le graphe de prix"':''}>${r.Nom||("GID "+r.GID)}${r.GID?' <span class="goicon">📈</span>':''}</h3>`+
    `<div class="sub">${subLine}</div>`+
    (r.GID ? sellLotCtrlHTML(r.GID) : '')+
    `<div class="kv">`+
      `<div class="b"><div class="v">${num(isCon?cSellU:d.rev)}</div><div class="l">${isCon?('Vente / u (lot '+cLotLbl+')'):'Revenu runes / unité'}</div></div>`+
      `<div class="b"><div class="v">${num(d.cost)}</div><div class="l">Coût ${isCon?'concassage':'craft'} / unité</div></div>`+
      `<div class="b"><div class="v">${num(r.Prix_Moyen)}</div><div class="l">Prix moyen (réf.)</div></div>`+
      `<div class="b"><div class="v">${benFmt(cBenef)}</div><div class="l">Bénéfice / unité</div></div>`+
      `<div class="b"><div class="v">${cRent==null?'—':cRent.toFixed(2)}</div><div class="l">Ratio</div></div>`+
      (!isCon?`<div class="b"><div class="v">${d.cmin==null?'—':fmt(d.cmin)+'%'}</div><div class="l">Coeff min</div></div>`:'')+
    `</div>`+
    verdict+
    `<div class="kv" style="align-items:center"><span class="muted">Batch${r.is_equip?' équip':''} :</span> ${r.is_equip?equipBatchSelHTML():batchSelectorHTML()} <span class="muted">${batchN?('= '+fmt(batchN)+' crafts'):''}</span></div>`+
    `<div class="kv">`+
      `<div class="b"><div class="v">${batchN&&d.cost!=null?fmt(d.cost*batchN):'—'}</div><div class="l">Coût TOTAL du batch</div></div>`+
      `<div class="b"><div class="v">${batchN&&cBenef!=null?benFmt(cBenef*batchN):'—'}</div><div class="l">Bénéfice TOTAL du batch</div></div>`+
      `<div class="b"><div class="v">${batchN&&cSellU!=null?fmt(cSellU*batchN):'—'}</div><div class="l">Revenu TOTAL du batch</div></div>`+
    `</div>`+
    (r.GID?`<div class="kv" style="align-items:center"><span class="muted">🧺 Quantité à crafter :</span> `+
      `<input id="bmodal-qty" type="number" min="1" value="${batchN||1}" style="width:80px"> `+
      `<button class="btn" id="bmodal-add">➕ Ajouter à ma liste</button></div>`:'')+
    `<h3 class="sec">Recette ${c&&!c.db?'<span class="muted">(prix moyen, sans optim. tiers)</span>':''}</h3>`+
    `<table><thead><tr><th class="name" style="min-width:120px">Ingrédient</th><th>Qté</th><th title="Quantité totale pour le batch">Besoin</th><th>Tier</th><th title="Prix unitaire d'achat retenu">PU</th><th title="Dernier prix moyen marché">Moyen</th><th title="Prix médian historique">Médian</th><th title="Coût pour 1 craft">Coût ligne</th><th title="Coût pour tout le batch">Coût total</th><th title="Économie en craftant l'ingrédient au lieu de l'acheter">Gain craft</th></tr></thead><tbody>${recipeRows}</tbody></table>`+
    bottomSection;
  box.querySelector(".batchsel").addEventListener("click", e=>{
    const btn=e.target.closest("button"); if(!btn) return;
    if(btn.dataset.eb!=null){ EQUIP_BATCH=btn.dataset.eb; BATCH_BY_HOST["craft-equip-tbl"]=EQUIP_BATCH; }
    else BATCH=btn.dataset.b;
    refreshActiveTab(); openBModal(r, real);
  });
  // Cases de lots de vente : re-render modale + onglet visible.
  box.querySelectorAll("input[data-sell]").forEach(cb=>cb.onchange=()=>{
    toggleSell(+cb.dataset.gid, cb.dataset.sell);
    refreshActiveTab();
    openBModal(r, real);
  });
  // Clic sur un ingrédient → ouvre/maj le graphe de prix (popup de droite si mode double).
  box.addEventListener("click", e=>{
    const tr=e.target.closest("tr[data-ing]"); if(!tr) return;
    const dual = document.getElementById("bmodal").classList.contains("dual-left");
    openPriceModal(+tr.dataset.ing, dual);
  });
  const mt=document.getElementById("bmodal-title");
  if(mt && r.GID) mt.onclick=()=>openPriceModal(r.GID);   // nom/icône → graphe (à droite)
  const addBtn=document.getElementById("bmodal-add");
  if(addBtn) addBtn.onclick=()=>{ const q=Math.max(1,Math.round(+document.getElementById("bmodal-qty").value||1));
    addToCraftList(r.GID, q); addBtn.textContent="✓ Ajouté"; setTimeout(()=>{ if(addBtn.isConnected) addBtn.textContent="➕ Ajouter à ma liste"; },1200); };
  document.getElementById("bmodal-x").onclick = closeBModal;
  document.getElementById("bmodal").style.display = "flex";
  layoutModals();
}
// Place les modales : côte à côte si les DEUX sont ouvertes, centrée sinon.
// Garantit qu'elles ne se superposent jamais, quel que soit l'onglet.
function layoutModals(){
  const bm=document.getElementById("bmodal"), pm=document.getElementById("pmodal");
  const bv=bm.style.display && bm.style.display!=="none";
  const pv=pm.style.display && pm.style.display!=="none";
  const dual=bv&&pv;
  bm.classList.toggle("dual-left", dual);
  pm.classList.toggle("dual-right", dual);
  document.getElementById("closeboth").style.display = (bv||pv) ? "block" : "none";
}
function closeBothModals(){ document.getElementById("bmodal").style.display="none"; MODAL_CTX=null;
  document.getElementById("pmodal").style.display="none"; layoutModals(); }
document.getElementById("closeboth").onclick = closeBothModals;
// Ouvre le détail (craft/brisage/concassage) à GAUCHE et le graphe de l'item
// à DROITE, côte à côte. Cliquer un ingrédient ne change que le graphe de droite.
function openItemDetail(r, real){
  openBModal(r, real);
  if(r.GID) openPriceModal(r.GID);
}
function closeBModal(){
  document.getElementById("bmodal").style.display="none"; MODAL_CTX=null; layoutModals();
}
document.getElementById("bmodal").addEventListener("click", e=>{ if(e.target.id==="bmodal") closeBModal(); });
document.addEventListener("keydown", e=>{ if(e.key==="Escape"){ closeBModal(); if(typeof closePriceModal==="function") closePriceModal(); } });

// ── Onglet « Bonnes affaires du moment » ───────────────────────────────────
function median(a){ const b=a.slice().sort((x,y)=>x-y), n=b.length;
  return n ? (n%2 ? b[(n-1)/2] : (b[n/2-1]+b[n/2])/2) : null; }
// Statistiques « affaire » d'un item à partir de sa série de prix moyen.
function dealStats(item){
  const s=item.avg.filter(p=>p[1]!=null).map(p=>p[1]);
  if(s.length<4) return null;
  const cur=s[s.length-1], med=median(s), mean=s.reduce((a,b)=>a+b,0)/s.length;
  const sd=Math.sqrt(s.reduce((a,b)=>a+(b-mean)**2,0)/s.length);
  return {cur, med, mean, n:s.length,
          ecart: med ? (cur-med)/med*100 : null,
          z: sd ? (cur-mean)/sd : null,
          series: item.avg.filter(p=>p[1]!=null)};
}
const DEALS = (()=>{
  const out=[];
  for(const it of DTV.items){
    const st=dealStats(it); if(!st||st.ecart==null) continue;
    out.push({gid:it.gid, nom:it.nom, type:it.type||"", level:it.level, st});
  }
  return out;
})();
const DEALMAP = (()=>{ const m={}; DEALS.forEach(d=>{ m[normName(d.nom)]=d; }); return m; })();
// Lookup nom→gid sur tous les items connus (pour rendre les ingrédients cliquables).
const NAMEGID = (()=>{ const m={}; DTV.items.forEach(it=>{ m[normName(it.nom)]=it.gid; }); return m; })();
// Index GID → ligne brisage (pour proposer « briser » sur un item bon marché).
const BRISMAP = (()=>{ const m={}; (B.theo||[]).forEach(r=>{ if(r.GID!=null && m[r.GID]==null) m[r.GID]=r; }); return m; })();
// Meilleure DÉCISION sur un item bon marché maintenant (acheté à `cur`). Toutes
// les options sont évaluées en achetant à cur, par UNITÉ, et on ne garde QUE les
// rentables (>0). Évite de proposer une action qui fait perdre des kamas.
let _actCache={};
function bestActionDeal(deal){
  if(deal.gid in _actCache) return _actCache[deal.gid];
  const gid=deal.gid, cur=deal.st.cur, med=deal.st.med;
  const it=DTV.items.find(x=>x.gid===gid);
  const opts=[];
  // Flip : acheter bas, revendre à la médiane (ou vendre haut si au-dessus).
  if(med!=null){ if(med>cur) opts.push({kind:"🔄 Revente médiane", benef:med-cur, cost:cur, ca:med});
                 else if(cur>med) opts.push({kind:"📤 Vendre (prix haut)", benef:cur-med, cost:med, ca:cur}); }
  // Briser l'item acheté à cur → runes.
  const brz=BRISMAP[gid]; if(brz && brz.Revenu_theo!=null) opts.push({kind:"⚒️ Briser", benef:brz.Revenu_theo-cur, cost:cur, ca:brz.Revenu_theo});
  // Concasser : acheter 3 runes à cur → 1 du tier supérieur revendable.
  ((typeof _CONC_ING_MAP!=="undefined"&&_CONC_ING_MAP[gid])||[]).forEach(o=>{
    const rit=DTV.items.find(x=>x.gid===o.GID);
    const b=rit?(bestSell(rit,o.GID)||(avgUnit(rit)!=null?{unit:avgUnit(rit)}:null)):null;
    if(b) opts.push({kind:"🔨 Concasser", benef:b.unit-3*cur, cost:3*cur, ca:b.unit}); });
  // Arbitrage de lot (achat tier n → vente tier n+1), bénéfice par unité.
  if(it && typeof arbRow==="function"){ const a=arbRow(it); if(a) opts.push({kind:"💱 "+a.buy+"→"+a.sell, benef:a.ecartU, cost:a.t[a.buy].unit, ca:a.t[a.sell].unit}); }
  const pos=opts.filter(o=>o.benef!=null && o.benef>0).sort((x,y)=>y.benef-x.benef);
  return _actCache[deal.gid] = (pos[0]||null);
}
let AFF_SEUIL=-10, AFF_SENS="buy", AFF_SORT={k:"ecart",dir:1}, OP_SORT={k:"eco",dir:-1}, OP2_SORT={k:"eco",dir:-1};
const ecartColor = e => e<0 ? 'var(--accent2)' : e>0 ? 'var(--bad)' : 'var(--muted)';
const _md = '<span class="muted">—</span>';
// Économie NETTE d'un craft grâce aux promos : Σ qté×(médiane − prix actuel) sur
// les ingrédients suivis. Un ingrédient AU-DESSUS de sa médiane réduit l'économie
// (déduit) → on ne garde l'opportunité que si le total reste positif.
function recipeEconomie(r){
  let eco=0, promo=[], hasDeal=false;
  for(const ing of (r.craft.recipe||[])){
    const deal=DEALMAP[normName(ing.nom)]; if(!deal||deal.st.med==null) continue;
    hasDeal=true;
    const save = ing.qty*(deal.st.med - deal.st.cur);
    eco += save;
    if(save>0) promo.push({ing, deal, save});
  }
  return {eco, promo, hasDeal};
}
function affOpCols(){
  const bItem = o=>DTV.items.find(it=>it.gid===o.r.GID);
  return [
    {k:"nom", l:"Item", cls:"name", get:o=>o.r.Nom, fmt:o=>o.r.Nom},
    {k:"type", l:"Type", cls:"type", get:o=>o.r.Type||"", fmt:o=>o.r.Type||_md},
    {k:"niv", l:"Niv", cls:"narrow", get:o=>o.r.Niveau, fmt:o=>o.r.Niveau==null?_md:o.r.Niveau},
    {k:"vol", l:"V", cls:"narrow", title:"Volume V de l'item", get:o=>{const it=bItem(o);return it?volumeIndex(seriesOf(it,"avg")):null;}, fmt:o=>{const it=bItem(o);if(!it)return _md;const v=volumeIndex(seriesOf(it,"avg"));return v==null?_md:(+v).toFixed(1);}},
    {k:"fresh", l:"F", cls:"narrow", title:"Fraîcheur HDV", get:o=>hdvFreshDays(bItem(o)), fmt:o=>hdvFreshCell(bItem(o))},
    {k:"promo", l:"Ingrédient(s) en promo", cls:"runesb", sort:false, get:o=>0,
      fmt:o=>o.promo.map(x=>`${x.ing.nom} <span style="color:var(--accent2)" title="-${fmt(Math.round(x.save))} k vs médiane">${pct(x.deal.st.ecart)}</span>`).join(", ")},
    {k:"eco", l:"Économie", cls:"narrow", title:"Kamas économisés par craft grâce aux promos (net : ingrédients chers déduits)",
      get:o=>o.eco, fmt:o=>`<b style="color:var(--accent2)">${fmt(Math.round(o.eco))}</b>`},
    {k:"ecopct", l:"Éco%", cls:"narrow", title:"Économie en % du coût de craft unitaire (Économie ÷ Craft)",
      get:o=>o.d.cost?o.eco/o.d.cost*100:null, fmt:o=>o.d.cost?`<span style="color:var(--accent2)">${(o.eco/o.d.cost*100).toFixed(1)}%</span>`:_md},
    {k:"cost", l:"Craft", cls:"narrow", title:"Coût de craft au batch courant", get:o=>o.d.cost, fmt:o=>num(o.d.cost)},
    {k:"batchN", l:"Batch", cls:"narrow", get:o=>o.d.batchN, fmt:o=>o.d.batchN==null?_md:fmt(o.d.batchN)},
    {k:"ca", l:"CA", cls:"narrow", title:"Chiffre d'affaires : valeur des runes du batch (revenu × Batch)",
      get:o=>o.d.rev==null||o.d.batchN==null?null:o.d.rev*o.d.batchN, fmt:o=>caFmt(o.d.rev==null||o.d.batchN==null?null:o.d.rev*o.d.batchN)},
    {k:"benef", l:"Bénéf", cls:"narrow", get:o=>o.d.benef, fmt:o=>benFmt(o.d.benef)},
    {k:"bbatch", l:"B×Batch", cls:"narrow", get:o=>o.d.benef==null||o.d.batchN==null?null:o.d.benef*o.d.batchN, fmt:o=>benFmt(o.d.benef==null||o.d.batchN==null?null:o.d.benef*o.d.batchN)},
    {k:"cmin", l:"C.min", cls:"narrow gold", title:"Coeff serveur minimal pour être rentable", get:o=>o.d.cmin, fmt:o=>o.d.cmin==null?_md:fmt(o.d.cmin)+'%'},
    {k:"rent", l:"Rent", cls:"narrow gold", get:o=>o.d.rent, fmt:o=>o.d.rent==null?_md:o.d.rent.toFixed(2)},
    {k:"runes", l:"Runes obtenues / u", cls:"runesb", sort:false, get:o=>0, fmt:o=>o.r.Runes||_md},
  ];
}

function affDealCols(){
  const dItem = r=>DTV.items.find(x=>x.gid===r.gid);
  return [
    {k:"fav", l:"★", cls:"fav", sort:false, get:r=>0, fmt:r=>`<span class="star ${isFav(r.gid)?'on':''}" data-fav="${r.gid}">★</span>`},
    {k:"nom", l:"Nom", cls:"name", get:r=>r.nom, fmt:r=>r.nom},
    {k:"type", l:"Type", cls:"type", get:r=>r.type, fmt:r=>r.type||_md},
    {k:"vol", l:"V", cls:"narrow", title:"Volume V (activité marché)", get:r=>{const it=dItem(r);return it?volumeIndex(seriesOf(it,"avg")):null;}, fmt:r=>{const it=dItem(r);if(!it)return _md;const v=volumeIndex(seriesOf(it,"avg"));return v==null?_md:(+v).toFixed(1);}},
    {k:"fresh", l:"F", cls:"narrow", title:"Fraîcheur HDV ; bascule sur le prix moyen (tag « moy ») si pas de relevé récent", get:r=>{const it=dItem(r); return it?(hdvFreshDays(it)??seriesFreshDays(seriesOf(it,"avg"))):null;}, fmt:r=>{const it=dItem(r); return it?dealFreshCell(it):_md;}},
    {k:"cur", l:"Prix actuel", cls:"narrow", get:r=>r.st.cur, fmt:r=>fmt(r.st.cur)},
    {k:"med", l:"Médiane", cls:"narrow", title:"Prix médian historique", get:r=>r.st.med, fmt:r=>fmt(r.st.med)},
    {k:"ecart", l:"Écart", cls:"narrow", title:"Écart du prix actuel vs médiane historique", get:r=>r.st.ecart, fmt:r=>`<span style="color:${ecartColor(r.st.ecart)}">${pct(r.st.ecart)}</span>`},
    {k:"action", l:"Meilleure action", cls:"narrow", title:"Décision la plus rentable en achetant maintenant : flip à la médiane, brisage, concassage, ou arbitrage de lot. N'affiche que le rentable.",
      get:r=>{ const a=bestActionDeal(r); return a?a.kind:""; }, fmt:r=>{ const a=bestActionDeal(r); return a?a.kind:_md; }},
    {k:"acost", l:"Coût/u", cls:"narrow", title:"Coût unitaire de l'action (achat + transformation)", get:r=>{const a=bestActionDeal(r);return a?a.cost:null;}, fmt:r=>{const a=bestActionDeal(r);return a&&a.cost!=null?fmt(Math.round(a.cost)):_md;}},
    {k:"aca", l:"CA/u", cls:"narrow", title:"Revenu unitaire de l'action", get:r=>{const a=bestActionDeal(r);return a?a.ca:null;}, fmt:r=>{const a=bestActionDeal(r);return a&&a.ca!=null?caFmt(Math.round(a.ca)):_md;}},
    {k:"abenef", l:"Bénéf/u", cls:"narrow", title:"Bénéfice par unité de l'action", get:r=>{const a=bestActionDeal(r);return a?a.benef:null;}, fmt:r=>{const a=bestActionDeal(r);return a?`<b style="color:var(--accent2)">+${fmt(Math.round(a.benef))}</b>`:_md;}},
    {k:"aratio", l:"Ratio", cls:"narrow gold", title:"Ratio CA/Coût de l'action (>1 = gain)", get:r=>{const a=bestActionDeal(r);return a&&a.cost?a.ca/a.cost:null;}, fmt:r=>{const a=bestActionDeal(r);return a&&a.cost?(a.ca/a.cost).toFixed(2):_md;}},
    {k:"spark", l:"Tendance", sort:false, get:r=>0, fmt:r=>sparkline(lastDays(r.st.series,7))},
  ];
}
function renderAffaires(){
  const root=document.getElementById("affaires-root");
  _actCache={};   // les actions dépendent du batch/lots courants → recalcul à chaque rendu
  const seuilSel = `<select id="affSeuil">${[-5,-10,-20,-30].map(v=>`<option value="${v}"${v===AFF_SEUIL?' selected':''}>${Math.abs(v)}%</option>`).join("")}</select>`;
  const sensSel = `<select id="affSens"><option value="buy"${AFF_SENS==="buy"?" selected":""}>sous la médiane (à acheter)</option><option value="sell"${AFF_SENS==="sell"?" selected":""}>au-dessus (à vendre)</option></select>`;
  // Section 1 : « top des décisions » — items dont une action est RENTABLE maintenant.
  let rows = DEALS.filter(d=> !isArchived(d.gid) && (AFF_SENS==="buy" ? d.st.ecart<=AFF_SEUIL : d.st.ecart>=Math.abs(AFF_SEUIL)));
  rows = rows.filter(r=>{ const a=bestActionDeal(r); return a && (MIN_BENEF<=0 || a.benef>=MIN_BENEF); });
  const cols = affDealCols();
  const col = cols.find(c=>c.k===AFF_SORT.k)||cols.find(c=>c.k==="abenef")||cols[6];
  rows.sort((a,b)=>{ let va=col.get(a),vb=col.get(b);
    const an=va==null,bn=vb==null; if(an&&bn)return 0; if(an)return 1; if(bn)return -1;
    if(typeof va==="string"){va=va.toLowerCase();vb=vb.toLowerCase();return va<vb?-AFF_SORT.dir:va>vb?AFF_SORT.dir:0;}
    return (va-vb)*AFF_SORT.dir; });
  const head = cols.map(c=>{ const arr=AFF_SORT.k===c.k?`<span class="arrow">${AFF_SORT.dir<0?"▼":"▲"}</span>`:"";
    const tt=c.title?` title="${c.title}"`:""; return `<th class="${c.cls||''}"${tt} data-k="${c.k}" data-sort="${c.sort!==false}">${c.l} ${arr}</th>`; }).join("");
  const body = rows.length ? rows.map(r=>`<tr data-gid="${r.gid}">`+cols.map(c=>`<td class="${c.cls||''}">${c.fmt(r)}</td>`).join("")+"</tr>").join("")
    : `<tr><td colspan="${cols.length}"><div class="empty">Aucun item ${AFF_SENS==="buy"?"sous":"au-dessus de"} sa médiane à ce seuil.</div></td></tr>`;
  // Section 2 : opportunités craft/brisage induites (un ingrédient est en promo).
  let ops=[];
  if(B.available){
    for(const r of B.theo){
      if(!r.craft||!r.craft.recipe || isArchived(r.GID)) continue;
      const d=deriveB(r,false);
      if(!(d.benef>0)) continue;
      const invest=(d.cost!=null&&d.batchN!=null)?d.cost*d.batchN:null;
      const benefB=(d.benef!=null&&d.batchN!=null)?d.benef*d.batchN:null;
      if(!passInvestBenef(invest, benefB)) continue;   // capital max / bénéf min
      // Au moins un ingrédient en promo sous le seuil, ET économie nette positive
      // (un ingrédient au prix haut ne doit pas annuler la promo).
      const e=recipeEconomie(r);
      if(!e.hasDeal || e.eco<=0) continue;
      if(!e.promo.some(x=>x.deal.st.ecart<=AFF_SEUIL)) continue;
      ops.push({r, d, promo:e.promo, eco:e.eco});
    }
  }
  const opCols = affOpCols();
  const opCol = opCols.find(c=>c.k===OP_SORT.k)||opCols[5];
  ops.sort((a,b)=>{ let va=opCol.get(a),vb=opCol.get(b);
    const an=va==null,bn=vb==null; if(an&&bn)return 0; if(an)return 1; if(bn)return -1;
    if(typeof va==="string"){va=va.toLowerCase();vb=vb.toLowerCase();return va<vb?-OP_SORT.dir:va>vb?OP_SORT.dir:0;}
    return (va-vb)*OP_SORT.dir; });
  const opHead = opCols.map(c=>{ const arr=OP_SORT.k===c.k?`<span class="arrow">${OP_SORT.dir<0?"▼":"▲"}</span>`:"";
    const tt=c.title?` title="${c.title}"`:""; return `<th class="${c.cls||''}"${tt} data-k="${c.k}" data-sort="${c.sort!==false}">${c.l} ${arr}</th>`; }).join("");
  const opBody = ops.length ? ops.map(o=>`<tr data-gid="${o.r.GID}" style="cursor:pointer">`+
      opCols.map(c=>`<td class="${c.cls||''}">${c.fmt(o)}</td>`).join("")+"</tr>").join("")
    : `<tr><td colspan="${opCols.length}"><div class="empty">${B.available?"Aucune recette dont un ingrédient est en promo à ce seuil.":"Catalogue craft indisponible."}</div></td></tr>`;
  // Section 3 : opportunités Craft (revente) induites (même logique, items à revendre).
  let cops=[];
  if(CR.available){
    [...(CR.rows_other||[]),...(CR.rows_equip||[])].forEach(r=>{
      if(!r.craft||!r.craft.recipe || isArchived(r.GID)) return;
      const d=deriveB(r,false); if(!(d.benef>0)) return;
      const invest=(d.cost!=null&&d.batchN!=null)?d.cost*d.batchN:null;
      const benefB=(d.benef!=null&&d.batchN!=null)?d.benef*d.batchN:null;
      if(!passInvestBenef(invest, benefB)) return;
      const e=recipeEconomie(r); if(!e.hasDeal || e.eco<=0) return;
      if(!e.promo.some(x=>x.deal.st.ecart<=AFF_SEUIL)) return;
      cops.push({r, d, promo:e.promo, eco:e.eco});
    });
  }
  const cCols = affOpCols();
  const cCol = cCols.find(c=>c.k===OP2_SORT.k)||cCols[5];
  cops.sort((a,b)=>{ let va=cCol.get(a),vb=cCol.get(b);
    const an=va==null,bn=vb==null; if(an&&bn)return 0; if(an)return 1; if(bn)return -1;
    if(typeof va==="string"){va=va.toLowerCase();vb=vb.toLowerCase();return va<vb?-OP2_SORT.dir:va>vb?OP2_SORT.dir:0;}
    return (va-vb)*OP2_SORT.dir; });
  const cHead = cCols.map(c=>{ const arr=OP2_SORT.k===c.k?`<span class="arrow">${OP2_SORT.dir<0?"▼":"▲"}</span>`:"";
    const tt=c.title?` title="${c.title}"`:""; return `<th class="${c.cls||''}"${tt} data-k="${c.k}" data-sort="${c.sort!==false}">${c.l} ${arr}</th>`; }).join("");
  const cBody = cops.length ? cops.map(o=>`<tr data-gid="${o.r.GID}" style="cursor:pointer">`+
      cCols.map(c=>`<td class="${c.cls||''}">${c.fmt(o)}</td>`).join("")+"</tr>").join("")
    : `<tr><td colspan="${cCols.length}"><div class="empty">${CR.available?"Aucun craft à revendre dont un ingrédient est en promo.":"Onglet Craft indisponible."}</div></td></tr>`;

  root.innerHTML =
    `<div class="controls"><label class="muted">Affaires <b id="affCount"></b></label>`+
    `<label class="muted">Sens&nbsp;${sensSel}</label>`+
    `<label class="muted">Seuil d'écart&nbsp;${seuilSel}</label>`+
    `<span class="muted">prix actuel vs médiane historique du prix moyen</span></div>`+
    `<h3 class="sec">💸 Prix bas du moment <span class="muted">— clique une ligne pour voir le graphe</span></h3>`+
    `<div class="tablewrap"><table id="affTbl"><thead><tr>${head}</tr></thead><tbody id="affRows">${body}</tbody></table></div>`+
    `<h3 class="sec">⚒️ Opportunités craft/brisage induites <span class="muted">— rentables maintenant ET un ingrédient est en promo · clique pour le détail</span></h3>`+
    `<div class="tablewrap"><table id="opTbl"><thead><tr>${opHead}</tr></thead><tbody id="opRows">${opBody}</tbody></table></div>`+
    `<h3 class="sec">🛠️ Opportunités craft (revente) induites <span class="muted">— crafter puis revendre, avec un ingrédient en promo · clique pour le détail</span></h3>`+
    `<div class="tablewrap"><table id="cOpTbl"><thead><tr>${cHead}</tr></thead><tbody id="cOpRows">${cBody}</tbody></table></div>`;
  document.getElementById("affCount").textContent = rows.length;
  document.getElementById("affSeuil").addEventListener("change", e=>{ AFF_SEUIL=Number(e.target.value); renderAffaires(); });
  document.getElementById("affSens").addEventListener("change", e=>{ AFF_SENS=e.target.value; AFF_SORT={k:"ecart",dir:AFF_SENS==="buy"?1:-1}; renderAffaires(); });
  document.querySelector("#affTbl thead").addEventListener("click", e=>{
    const th=e.target.closest("th"); if(!th||th.dataset.sort==="false"||!th.dataset.k) return;
    const k=th.dataset.k; if(AFF_SORT.k===k) AFF_SORT.dir*=-1; else AFF_SORT={k, dir:(k==="nom"||k==="type")?1:-1};
    renderAffaires();
  });
  document.getElementById("affRows").addEventListener("click", e=>{
    const star=e.target.closest(".star");
    if(star){ const gid=+star.dataset.fav; toggleFav(gid); star.classList.toggle("on",isFav(gid)); renderListControls(); return; }
    const tr=e.target.closest("tr"); if(!tr||!tr.dataset.gid) return;
    openPriceModal(+tr.dataset.gid);
  });
  document.querySelector("#opTbl thead").addEventListener("click", e=>{
    const th=e.target.closest("th"); if(!th||th.dataset.sort==="false"||!th.dataset.k) return;
    const k=th.dataset.k; if(OP_SORT.k===k) OP_SORT.dir*=-1; else OP_SORT={k, dir:(k==="nom"||k==="type")?1:-1};
    renderAffaires();
  });
  document.getElementById("opRows").addEventListener("click", e=>{
    const tr=e.target.closest("tr"); if(!tr||!tr.dataset.gid) return;
    const r=B.theo.find(x=>x.GID==tr.dataset.gid); if(r) openItemDetail(r,false);
  });
  document.querySelector("#cOpTbl thead").addEventListener("click", e=>{
    const th=e.target.closest("th"); if(!th||th.dataset.sort==="false"||!th.dataset.k) return;
    const k=th.dataset.k; if(OP2_SORT.k===k) OP2_SORT.dir*=-1; else OP2_SORT={k, dir:(k==="nom"||k==="type")?1:-1};
    renderAffaires();
  });
  document.getElementById("cOpRows").addEventListener("click", e=>{
    const tr=e.target.closest("tr"); if(!tr||!tr.dataset.gid) return;
    const r=(typeof CRAFTMAP!=="undefined")?CRAFTMAP[+tr.dataset.gid]:null; if(r) openItemDetail(r,false);
  });
}
// Popup graphe de prix d'un item (réutilise showDetail : graphe + Volume V +
// crafts qui utilisent la ressource).
function openPriceModal(gid, dual){
  const box=document.getElementById("pmodal-box");
  box.innerHTML = `<span class="x" id="pmodal-x">✕</span><div class="pdetail"></div>`;
  showDetail(gid, box.querySelector(".pdetail"));
  document.getElementById("pmodal-x").onclick = closePriceModal;
  document.getElementById("pmodal").style.display = "flex";
  layoutModals();   // côte à côte si le détail craft est aussi ouvert
}
function closePriceModal(){ document.getElementById("pmodal").style.display="none"; layoutModals(); }
document.getElementById("pmodal").addEventListener("click", e=>{ if(e.target.id==="pmodal") closePriceModal(); });

// ── Onglet « Achat / Vente » (arbitrage entre tailles de lot) ──────────────
// Acheter au tier au prix unitaire le + bas, revendre via un lot autorisé au
// prix unitaire le + haut. Ex : 25/u en x1 mais 60/u en x10 → acheter 10×25,
// revendre 1 lot de 10 à 600. Inversement gros lot pas cher → petit lot cher.
let ARB_SORT={k:"ecart",dir:-1}, ARB_MINV=0, ARB_Q="";
function arbRow(it){
  // Tiers utilisables : seulement ceux dont le relevé date de < 3 jours
  // (évite de comparer des prix de lots relevés à des dates différentes).
  const t={};
  ["x1","x10","x100","x1000"].forEach(src=>{ const u=tierFreshUnit(it,src);
    if(u!=null){ const st=statsOf(seriesOf(it,src)); t[src]={lot:st.last, unit:u, size:LOTSIZE[src]}; } });
  // On ne passe que d'un tier au tier adjacent (1↔10, 10↔100, 100↔1000) :
  // acheter 100 unités en lots de 1 pour revendre par 100 n'est pas réaliste.
  const pairs=[["x1","x10"],["x10","x100"],["x100","x1000"]];
  let best=null;
  for(const [a,b] of pairs){
    if(!t[a]||!t[b]) continue;
    for(const [buy,sell] of [[a,b],[b,a]]){
      if(sell==="x1000") continue;                 // on ne vend pas par 1000
      if(!isSellOn(it.gid, sell)) continue;
      const ecartU=t[sell].unit-t[buy].unit; if(ecartU<=0) continue;
      const cand={buy, sell, ecartU, ecartPct:t[buy].unit>0?ecartU/t[buy].unit*100:null,
                  benefLot:t[sell].lot - t[sell].size*t[buy].unit, capital:t[sell].size*t[buy].unit};
      if(best==null || (cand.ecartPct||0)>(best.ecartPct||0)) best=cand;
    }
  }
  if(!best) return null;
  return {gid:it.gid, nom:it.nom, type:it.type||"", vol:volumeIndex(seriesOf(it,"avg")), t, ...best};
}
function renderArbitrage(){
  const root=document.getElementById("arb-root");
  let rows=DTV.items.filter(it=>!isArchived(it.gid)).map(arbRow).filter(Boolean);
  const q=ARB_Q.trim().toLowerCase();
  if(q) rows=rows.filter(r=>r.nom.toLowerCase().includes(q)||String(r.gid).includes(q));
  if(ARB_MINV>0) rows=rows.filter(r=>(r.vol||0)>=ARB_MINV);
  rows=rows.filter(r=>passInvestBenef(r.capital, r.benefLot));   // capital max / bénéf min
  const cols=[
    {k:"fav", l:"★", cls:"fav", sort:false, get:r=>0, fmt:r=>`<span class="star ${isFav(r.gid)?'on':''}" data-fav="${r.gid}">★</span>`},
    {k:"nom",   l:"Item", cls:"name", get:r=>r.nom, fmt:r=>r.nom},
    {k:"type",  l:"Type", cls:"type", get:r=>r.type, fmt:r=>r.type||'<span class="muted">—</span>'},
    {k:"vol",   l:"V",    cls:"narrow", title:"Volume V (activité marché)", get:r=>r.vol, fmt:r=>r.vol==null?'<span class="muted">—</span>':(+r.vol).toFixed(1)},
    {k:"fresh", l:"F",    cls:"narrow", title:"Fraîcheur HDV du dernier relevé. ● vert <3j · orange <10j · rouge", get:r=>hdvFreshDays(DTV.items.find(x=>x.gid===r.gid)), fmt:r=>hdvFreshCell(DTV.items.find(x=>x.gid===r.gid))},
    {k:"buy",   l:"Achat", cls:"narrow", title:"Tier d'achat le moins cher · prix unitaire",
      get:r=>r.t[r.buy].unit, fmt:r=>`<span title="lot ${fmt(r.t[r.buy].lot)}">${r.buy} · ${fmt(r.t[r.buy].unit)}/u</span>`},
    {k:"sell",  l:"Vente", cls:"narrow", title:"Meilleur lot de vente autorisé · prix unitaire",
      get:r=>r.t[r.sell].unit, fmt:r=>`<span title="lot ${fmt(r.t[r.sell].lot)}">${r.sell} · ${fmt(r.t[r.sell].unit)}/u</span>`},
    {k:"u1",   l:"x1/u",   cls:"narrow", title:"Prix unitaire en lot x1 (vert = bas / rouge = cher vs médiane)", get:r=>{const it=DTV.items.find(x=>x.gid===r.gid),s=it?statsOf(seriesOf(it,"x1")):null;return s?s.last:null;}, fmt:r=>tierUnitCell(DTV.items.find(x=>x.gid===r.gid),"x1")},
    {k:"u10",  l:"x10/u",  cls:"narrow", title:"Prix unitaire en lot x10 (vert = bas / rouge = cher vs médiane)", get:r=>{const it=DTV.items.find(x=>x.gid===r.gid),s=it?statsOf(seriesOf(it,"x10")):null;return s?s.last/10:null;}, fmt:r=>tierUnitCell(DTV.items.find(x=>x.gid===r.gid),"x10")},
    {k:"u100", l:"x100/u", cls:"narrow", title:"Prix unitaire en lot x100 (vert = bas / rouge = cher vs médiane)", get:r=>{const it=DTV.items.find(x=>x.gid===r.gid),s=it?statsOf(seriesOf(it,"x100")):null;return s?s.last/100:null;}, fmt:r=>tierUnitCell(DTV.items.find(x=>x.gid===r.gid),"x100")},
    {k:"u1000",l:"x1000/u",cls:"narrow", title:"Prix unitaire en lot x1000 (vert = bas / rouge = cher vs médiane)", get:r=>{const it=DTV.items.find(x=>x.gid===r.gid),s=it?statsOf(seriesOf(it,"x1000")):null;return s?s.last/1000:null;}, fmt:r=>tierUnitCell(DTV.items.find(x=>x.gid===r.gid),"x1000")},
    {k:"ca", l:"CA", cls:"narrow", title:"Chiffre d'affaires : prix de vente du lot (ce que tu encaisses par lot vendu)", get:r=>r.t[r.sell].lot, fmt:r=>caFmt(r.t[r.sell].lot)},
    {k:"ecart", l:"Écart/u", cls:"narrow", title:"Bénéfice par unité = vente/u − achat/u", get:r=>r.ecartU, fmt:r=>benFmt(r.ecartU)},
    {k:"ecartPct", l:"Écart %", cls:"var", title:"Marge en % du prix d'achat", get:r=>r.ecartPct, fmt:r=>r.ecartPct==null?'—':varCell(r.ecartPct)},
    {k:"benefLot", l:"Bénéf/lot", cls:"narrow", title:"Bénéfice net pour 1 lot vendu (prix lot vente − achat des unités)", get:r=>r.benefLot, fmt:r=>benFmt(r.benefLot)},
    {k:"capital", l:"Capital", cls:"narrow", title:"Mise à avancer pour 1 lot (taille lot × prix unitaire achat)", get:r=>r.capital, fmt:r=>fmt(r.capital)},
    {k:"ratio", l:"Ratio", cls:"narrow gold", title:"Ratio vente/u ÷ achat/u (>1 = gain)",
      get:r=>r.t[r.buy].unit>0?r.t[r.sell].unit/r.t[r.buy].unit:null,
      fmt:r=>{ const v=r.t[r.buy].unit>0?r.t[r.sell].unit/r.t[r.buy].unit:null; return v==null?'<span class="muted">—</span>':v.toFixed(2); }},
  ];
  const col=cols.find(c=>c.k===ARB_SORT.k)||cols[6];
  rows.sort((a,b)=>{ let va=col.get(a),vb=col.get(b);
    const an=(va==null),bn=(vb==null); if(an&&bn)return 0; if(an)return 1; if(bn)return -1;
    if(typeof va==="string"){va=va.toLowerCase();vb=vb.toLowerCase();return va<vb?-ARB_SORT.dir:va>vb?ARB_SORT.dir:0;}
    return (va-vb)*ARB_SORT.dir; });
  const head=cols.map(c=>{ const arr=ARB_SORT.k===c.k?`<span class="arrow">${ARB_SORT.dir<0?"▼":"▲"}</span>`:"";
    const tt=c.title?` title="${c.title}"`:""; return `<th class="${c.cls||''}"${tt} data-k="${c.k}" data-sort="${c.sort!==false}">${c.l} ${arr}</th>`; }).join("");
  const body=rows.length ? rows.map(r=>`<tr data-gid="${r.gid}">`+cols.map(c=>`<td class="${c.cls||''}">${c.fmt(r)}</td>`).join("")+"</tr>").join("")
    : `<tr><td colspan="${cols.length}"><div class="empty">Aucune opportunité (nécessite ≥2 tiers de prix HDV par item).</div></td></tr>`;
  root.innerHTML =
    `<div class="help">💱 <b>Achat / Vente.</b> Acheter un item à un tier de lot et le revendre au tier <b>adjacent</b> plus cher à l'unité (ex : acheter par 1 à 25/u, revendre par 10 à 60/u). `+
    `<b>${rows.length}</b> opportunités, sur relevés &lt; 3 j uniquement (pas de faux écart). <b>Bénéf/lot</b> = gain net d'une vente · <b>Capital</b> = mise à avancer. Clique un item pour régler ses lots de vente.</div>`+
    `<div class="controls">Volume min <input id="arbV" type="number" min="0" max="10" step="0.5" value="${ARB_MINV}" style="width:60px">`+
    `<input id="arbQ" type="search" placeholder="Rechercher (Entrée)…" value="${q.replace(/"/g,"&quot;")}" style="width:170px">`+
    `<button class="btn" id="arbQbtn">🔍</button></div>`+
    `<div class="tablewrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  document.getElementById("arbV").onchange=e=>{ ARB_MINV=Number(e.target.value)||0; renderArbitrage(); };
  const arbDoQ=()=>{ ARB_Q=document.getElementById("arbQ").value; renderArbitrage(); };
  document.getElementById("arbQbtn").onclick=arbDoQ;
  document.getElementById("arbQ").addEventListener("change", arbDoQ);   // Entrée / sortie de champ
  root.querySelector("thead").addEventListener("click",e=>{
    const th=e.target.closest("th"); if(!th||th.dataset.sort==="false"||!th.dataset.k) return;
    const k=th.dataset.k; if(ARB_SORT.k===k) ARB_SORT.dir*=-1; else ARB_SORT={k,dir:(k==="nom"||k==="type")?1:-1};
    renderArbitrage();
  });
  root.querySelector("tbody").addEventListener("click",e=>{
    const star=e.target.closest(".star");
    if(star){ const gid=+star.dataset.fav; toggleFav(gid); star.classList.toggle("on",isFav(gid)); renderListControls(); return; }
    const tr=e.target.closest("tr"); if(!tr||!tr.dataset.gid) return;
    openPriceModal(+tr.dataset.gid);
  });
}

// ── Onglet « Runes » ───────────────────────────────────────────────────────
const RD = DTV.runes || {runes:{}, concassage:[], live_prices:false};
const _CONC_ING_MAP = (()=>{ const m={};
  (RD.concassage||[]).forEach(r=>{ const fg=NAMEGID[normName(r.from_nom)];
    if(fg!=null){ (m[fg]=m[fg]||[]).push(r); } }); return m; })();

let _RUNE_NOM_SET = null, RUNE_SRC = "avg", RUNE_Q = "";
let RUNE_SORT = {k:"nom", dir:1};
let CONC_DETAIL = false;   // false = vue essentielle, true = toutes les colonnes

function _renderRuneConc(){
  const ctrl = document.getElementById("rune-conc-ctrl");
  if(ctrl){
    ctrl.innerHTML = `<span class="muted">Batch :</span> ${batchSelectorHTML()} `+
      `<button class="btn" id="concDetail">${CONC_DETAIL?'Vue simple':'Toutes les colonnes'}</button>`;
    ctrl.querySelector(".batchsel").addEventListener("click", e=>{
      const btn=e.target.closest("button"); if(!btn) return;
      BATCH=btn.dataset.b; _renderRuneConc();
      if(MODAL_CTX && MODAL_CTX.r.is_concassage) openBModal(MODAL_CTX.r, false);
    });
    ctrl.querySelector("#concDetail").addEventListener("click", ()=>{ CONC_DETAIL=!CONC_DETAIL; _renderRuneConc(); });
  }
  if(RD.concassage && RD.concassage.length){
    renderBTable("conc-tbl", RD.concassage, false, {k:"bbatch",dir:-1}, concassageCols);
  } else {
    document.getElementById("conc-tbl").innerHTML =
      '<div class="empty">Pas de données de concassage (nécessite des relevés HDV de runes).</div>';
  }
}

// Colonnes génériques « produire (craft/concassage) puis revendre ». `lead` =
// colonnes d'identification de la ligne ; `detail` = true → toutes les colonnes.
// Le revenu utilise le meilleur lot de vente autorisé (règle 3j) ; repli prix
// moyen pour les items non vendus en lots (équipements).
function sellBatchCols(real, lead, detail){
  function resIt(r){ return r.GID ? DTV.items.find(it=>it.gid===r.GID) : null; }
  function sellU(r, src){ if(!isSellOn(r.GID,src)) return null; const it=resIt(r); return it?effUnit(it,src):null; }
  function best(r){ const it=resIt(r); if(!it) return null;
    return bestSell(it, r.GID) || (avgUnit(it)!=null?{src:'moy', unit:avgUnit(it)}:null); }
  const off = '<span class="muted" title="Lot désactivé (clic l\'item → cases vente)">·</span>';
  const ratFmt = v=>v==null?'<span class="muted">—</span>':v.toFixed(2);
  function bLot(r, src, n){ const u=sellU(r,src), c=r._d.cost; return u==null||c==null?null:(u-c)*n; }
  function rTier(r, src){ const u=sellU(r,src), c=r._d.cost; return u==null||!c?null:u/c; }
  const cols = lead.concat([
    {k:"vol", l:"V", cls:"narrow", title:"Volume V : activité marché de l'item (0–10)",
      get:r=>{ const it=resIt(r); return it?volumeIndex(seriesOf(it,"avg")):null; },
      fmt:r=>{ const it=resIt(r); if(!it) return'<span class="muted">—</span>';
               const v=volumeIndex(seriesOf(it,"avg")); return v==null?'<span class="muted">—</span>':(+v).toFixed(1); }},
    {k:"fresh", l:"F", cls:"narrow", title:"Fraîcheur HDV du dernier relevé réel. ● vert <3j · orange <10j · rouge",
      get:r=>hdvFreshDays(resIt(r)), fmt:r=>hdvFreshCell(resIt(r))},
    {k:"batchN", l:"Batch", cls:"narrow", title:"Nombre de crafts/transfo au batch courant",
      get:r=>r._d.batchN, fmt:r=>r._d.batchN==null?'<span class="muted">—</span>':fmt(r._d.batchN)},
    {k:"cost", l:"C/u", cls:"narrow", title:"Coût de production d'1 unité (batch courant)",
      get:r=>r._d.cost, fmt:r=>num(r._d.cost)},
    {k:"cbatch", l:"C/Batch", cls:"narrow", title:"Coût total du batch (C/u × Batch) — capital à avancer",
      get:r=>r._d.cost==null||r._d.batchN==null?null:r._d.cost*r._d.batchN,
      fmt:r=>r._d.cost==null||r._d.batchN==null?'<span class="muted">—</span>':num(r._d.cost*r._d.batchN)},
    {k:"ca", l:"CA", cls:"narrow", title:"Chiffre d'affaires : revenu de vente du batch au meilleur lot — ce que tu encaisses",
      get:r=>{ const b=best(r); return b&&r._d.batchN!=null?b.unit*r._d.batchN:null; },
      fmt:r=>{ const b=best(r); return caFmt(b&&r._d.batchN!=null?b.unit*r._d.batchN:null); }},
    {k:"bbatch", l:"B×Batch", cls:"narrow", title:"Bénéfice total du batch au meilleur lot autorisé (règle relevé <3j)",
      get:r=>{ const b=best(r); return b&&r._d.cost!=null&&r._d.batchN!=null?(b.unit-r._d.cost)*r._d.batchN:null; },
      fmt:r=>{ const b=best(r); return benFmt(b&&r._d.cost!=null&&r._d.batchN!=null?(b.unit-r._d.cost)*r._d.batchN:null); }},
    {k:"rbatch", l:"RBatch", cls:"narrow gold", title:"Ratio au meilleur lot autorisé (vente/u ÷ coût/u)",
      get:r=>{ const b=best(r); return b&&r._d.cost?b.unit/r._d.cost:null; },
      fmt:r=>{ const b=best(r); return ratFmt(b&&r._d.cost?b.unit/r._d.cost:null); }},
    {k:"b10", l:"B×10", cls:"narrow", title:"Bénéfice total d'un lot de 10 (vente <3j sinon prix moyen)",
      get:r=>bLot(r,"x10",10), fmt:r=>isSellOn(r.GID,"x10")?benFmt(bLot(r,"x10",10)):off},
    {k:"r10", l:"R10", cls:"narrow gold", title:"Ratio en vente par 10", get:r=>rTier(r,"x10"), fmt:r=>isSellOn(r.GID,"x10")?ratFmt(rTier(r,"x10")):off},
    {k:"b100", l:"B×100", cls:"narrow", title:"Bénéfice total d'un lot de 100", get:r=>bLot(r,"x100",100), fmt:r=>isSellOn(r.GID,"x100")?benFmt(bLot(r,"x100",100)):off},
    {k:"r100", l:"R100", cls:"narrow gold", title:"Ratio en vente par 100", get:r=>rTier(r,"x100"), fmt:r=>isSellOn(r.GID,"x100")?ratFmt(rTier(r,"x100")):off},
    {k:"rmoyen", l:"RMoyen", cls:"narrow gold", title:"Ratio sur prix moyen marché (référence) = prix moyen/u ÷ coût/u",
      get:r=>{ const it=resIt(r), a=it?avgUnit(it):null; return a&&r._d.cost?a/r._d.cost:null; },
      fmt:r=>{ const it=resIt(r), a=it?avgUnit(it):null; return ratFmt(a&&r._d.cost?a/r._d.cost:null); }},
  ]);
  if(!detail){
    const ESS = new Set([...lead.map(c=>c.k), "vol","fresh","batchN","cost","cbatch","ca","bbatch","rbatch","b10","b100"]);
    return cols.filter(c=>ESS.has(c.k));
  }
  return cols;
}
const _favCol = {k:"fav", l:"★", cls:"fav", sort:false, get:r=>0,
  fmt:r=>`<span class="star ${isFav(r.GID)?'on':''}" data-fav="${r.GID}">★</span>`};
function concassageCols(real){
  return sellBatchCols(real, [ _favCol,
    {k:"Nom", l:"Résultat", cls:"name", title:"Rune obtenue (1 exemplaire)", get:r=>r.Nom, fmt:r=>r.Nom},
    {k:"from_nom", l:"Ingrédient", cls:"name", title:"Rune de départ (×3)", get:r=>r.from_nom, fmt:r=>r.from_nom},
  ], CONC_DETAIL);
}
function craftCols(real){
  return sellBatchCols(real, [ _favCol,
    {k:"Nom", l:"Item", cls:"name", title:"Item à crafter puis revendre", get:r=>r.Nom, fmt:r=>r.Nom},
    {k:"Type", l:"Type", cls:"type", get:r=>r.Type||"", fmt:r=>r.Type||'<span class="muted">—</span>'},
    {k:"Niveau", l:"Niv", cls:"narrow", get:r=>r.Niveau, fmt:r=>r.Niveau==null?'<span class="muted">—</span>':r.Niveau},
  ], CRAFT_DETAIL);
}

function _renderRunePrices(){
  const q = RUNE_Q.trim().toLowerCase();
  let rows = DTV.items.filter(it=>_RUNE_NOM_SET.has(normName(it.nom)) && !isArchived(it.gid)).map(it=>{
    const s = seriesOf(it, RUNE_SRC), st = statsOf(s), avgS = seriesOf(it, "avg");
    const hdvLast = it.hdv.length ? it.hdv[it.hdv.length-1][0] : null;
    return {gid:it.gid, nom:it.nom, type:it.type||"", level:it.level,
            item:it, s, st, avgS,
            varj:varOver(avgS,1), vars:varOver(avgS,7), varm:varOver(avgS,30),
            vol:volumeIndex(avgS),
            hdvN:it.hdv.length, hdvLast, hdvLastT:hdvLast?Date.parse(hdvLast):-Infinity};
  }).filter(r=>r.st);
  if(q) rows = rows.filter(r=>r.nom.toLowerCase().includes(q)||String(r.gid).includes(q));
  const col = COLS.find(c=>c.k===RUNE_SORT.k) || COLS[1];
  rows.sort((a,b)=>{
    let va=col.get(a), vb=col.get(b);
    const an=(va==null), bn=(vb==null); if(an&&bn)return 0; if(an)return 1; if(bn)return -1;
    if(typeof va==="string"){va=va.toLowerCase();vb=vb.toLowerCase();return va<vb?-RUNE_SORT.dir:va>vb?RUNE_SORT.dir:0;}
    return (va-vb)*RUNE_SORT.dir;
  });
  const srcOpts = ["avg","x1","x10","x100","x1000"].map(s=>
    `<option value="${s}"${s===RUNE_SRC?" selected":""}>${TIER_LABEL[s]}</option>`).join("");
  document.getElementById("rune-price-ctrl").innerHTML =
    `Source : <select id="runesrc">${srcOpts}</select> `+
    `<input id="runeq" type="search" placeholder="Rechercher (Entrée)…" value="${q.replace(/"/g,"&quot;")}" style="width:170px">`+
    `<button class="btn" id="runeqbtn">🔍</button>`;
  if(!rows.length){
    document.getElementById("rune-price-tbl").innerHTML =
      '<div class="empty">Aucune rune dans les données — lancez une capture pour obtenir des prix de runes.</div>';
  } else {
    const head = COLS.map(c=>{
      const arr = RUNE_SORT.k===c.k?`<span class="arrow">${RUNE_SORT.dir<0?"▼":"▲"}</span>`:"";
      const tt = c.title?` title="${c.title}"`:"";
      return `<th class="${c.cls||''}"${tt} data-k="${c.k}" data-sort="${c.sort!==false}">${c.l} ${arr}</th>`;
    }).join("");
    const body = rows.map(r=>`<tr data-gid="${r.gid}">`+COLS.map(c=>`<td class="${c.cls||''}">${c.fmt(r)}</td>`).join("")+"</tr>").join("");
    document.getElementById("rune-price-tbl").innerHTML =
      `<div class="tablewrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }
  document.getElementById("runesrc").onchange = e=>{ RUNE_SRC=e.target.value; _renderRunePrices(); };
  const runeDoQ=()=>{ RUNE_Q=document.getElementById("runeq").value; _renderRunePrices(); };
  document.getElementById("runeqbtn").onclick=runeDoQ;
  document.getElementById("runeq").addEventListener("change", runeDoQ);   // Entrée / sortie de champ
  const thead = document.querySelector("#rune-price-tbl thead");
  if(thead) thead.addEventListener("click", e=>{
    const th=e.target.closest("th"); if(!th||th.dataset.sort==="false"||!th.dataset.k) return;
    const k=th.dataset.k;
    if(RUNE_SORT.k===k) RUNE_SORT.dir*=-1; else RUNE_SORT={k, dir:(k==="nom"||k==="type")?1:-1};
    _renderRunePrices();
  });
  const tbody = document.querySelector("#rune-price-tbl tbody");
  if(tbody) tbody.addEventListener("click", e=>{
    const star=e.target.closest(".star");
    if(star){ const gid=+star.dataset.fav; toggleFav(gid); star.classList.toggle("on",isFav(gid)); renderListControls(); return; }
    const tr=e.target.closest("tr"); if(!tr||!tr.dataset.gid) return;
    // Graphe à droite du tableau (comme « Prix dans le temps »), pas en popup.
    showDetail(+tr.dataset.gid, document.getElementById("rune-detail"));
  });
}

function renderRunes(){
  const root = document.getElementById("runes-root");
  if(!_RUNE_NOM_SET){
    _RUNE_NOM_SET = new Set();
    Object.values(RD.runes||{}).forEach(r=>r.tiers.forEach(t=>_RUNE_NOM_SET.add(normName(t.nom))));
  }
  const liveTag = RD.live_prices
    ? '<span style="color:var(--accent2)">● prix HDV</span>'
    : '<span class="muted">● prix exemple</span>';
  root.innerHTML =
    `<div class="help">🔮 <b>Runes.</b> En haut : le prix de chaque rune dans le temps (clique une ligne → graphe à droite). `+
    `En bas : le <b>concassage</b> — transformer 3 runes d'un tier en 1 du tier supérieur. `+
    `Une ligne <b style="color:var(--accent2)">verte</b> = rentable (RBatch &gt; 1). Règle le <b>Batch</b> (taille de production) et les <b>lots de vente</b> réalistes en cliquant une rune. `+
    `<b>« Toutes les colonnes »</b> déplie le détail par lot (×10/×100).</div>`+
    `<div class="controls" id="rune-price-ctrl"></div>`+
    `<h3 class="sec">💎 Prix des runes ${liveTag}</h3>`+
    `<div class="layout with-detail">`+
      `<div id="rune-price-tbl"></div>`+
      `<div id="rune-detail" class="detail"><div class="empty">Clique une rune pour voir son graphe.</div></div>`+
    `</div>`+
    `<h3 class="sec">🔨 Concassage <span class="muted">— 3 × tier inférieur → 1 × tier supérieur — <small>clique une ligne : concassage à gauche + graphe à droite</small></span></h3>`+
    `<div class="controls" id="rune-conc-ctrl" style="margin-bottom:4px"></div>`+
    `<div id="conc-tbl"></div>`;
  _renderRunePrices();
  _renderRuneConc();
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
renderCraft();
renderAffaires();
renderArbitrage();
renderRunes();
renderCraftList(); updateListBadge();
renderFavoris(); renderArchives();
if(DTV.items.length){
  // sélectionne le 1er item de la vue (niveau le plus bas) pour montrer un graphe d'emblée
  const first = computeRows()[0];
  if(first) showDetail(first.gid);
}
</script>
</body>
</html>
"""
