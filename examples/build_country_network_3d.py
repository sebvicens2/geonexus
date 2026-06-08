"""Interactive 3D country network — fly through it, with labels and layer filter.

The readable Network view, in navigable 3D: one force-directed cloud of countries,
labelled, edges green (cooperation) / red (conflict). Filter by layer, click a
country to fly to it and focus its links. WebGL via 3d-force-graph + spritetext.

    python examples/build_country_network_3d.py
        → reports/geonexus_country_network_3d.html

Opens in any browser (loads the libs from a CDN, so needs internet + WebGL).
"""

from __future__ import annotations

import base64
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from multilayer import CAMEO, LAYERS, _actor

OUT_PATH = Path("reports") / "geonexus_country_network_3d.html"
SITUATION = Path(__file__).parent / "data" / "world_observer_situation.json"
FLAGS_CACHE = Path(__file__).parent / "data" / "flags_b64.json"


def _flag_uris(isos: set[str]) -> dict[str, str]:
    """Fetch flag PNGs once and cache them base64-encoded (so the HTML is offline-safe)."""
    cache = json.loads(FLAGS_CACHE.read_text(encoding="utf-8")) if FLAGS_CACHE.exists() else {}
    changed = False
    for iso in sorted(isos):
        if iso in cache:
            continue
        try:
            with urllib.request.urlopen(f"https://flagcdn.com/w80/{iso}.png", timeout=15) as r:
                cache[iso] = "data:image/png;base64," + base64.b64encode(r.read()).decode("ascii")
            changed = True
        except Exception:  # missing flag just falls back to a sphere
            pass
    if changed:
        FLAGS_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    return {iso: cache[iso] for iso in isos if iso in cache}


# country name -> ISO 3166-1 alpha-2 (for flagcdn flag textures); blocs fall back to a sphere
ISO2 = {
    "Afghanistan": "af",
    "Albania": "al",
    "Algeria": "dz",
    "Argentina": "ar",
    "Armenia": "am",
    "Australia": "au",
    "Azerbaijan": "az",
    "Bahrain": "bh",
    "Bangladesh": "bd",
    "Belarus": "by",
    "Bolivia": "bo",
    "Bosnia and Herzegovina": "ba",
    "Brazil": "br",
    "Burkina Faso": "bf",
    "Cambodia": "kh",
    "Canada": "ca",
    "Chile": "cl",
    "China": "cn",
    "Colombia": "co",
    "Congo": "cg",
    "Cuba": "cu",
    "Cyprus": "cy",
    "Czech Republic": "cz",
    "DR Congo": "cd",
    "Denmark": "dk",
    "Ecuador": "ec",
    "Egypt": "eg",
    "Estonia": "ee",
    "Ethiopia": "et",
    "European Union": "eu",
    "Finland": "fi",
    "France": "fr",
    "Germany": "de",
    "Ghana": "gh",
    "Greece": "gr",
    "Guatemala": "gt",
    "Hong Kong": "hk",
    "Hungary": "hu",
    "India": "in",
    "Indonesia": "id",
    "Iran": "ir",
    "Ireland": "ie",
    "Israel": "il",
    "Italy": "it",
    "Ivory Coast": "ci",
    "Jamaica": "jm",
    "Japan": "jp",
    "Jordan": "jo",
    "Kazakhstan": "kz",
    "Kenya": "ke",
    "Kosovo": "xk",
    "Kuwait": "kw",
    "Kyrgyzstan": "kg",
    "Laos": "la",
    "Latvia": "lv",
    "Lebanon": "lb",
    "Luxembourg": "lu",
    "Malaysia": "my",
    "Mali": "ml",
    "Mexico": "mx",
    "Montenegro": "me",
    "Morocco": "ma",
    "Myanmar": "mm",
    "Namibia": "na",
    "Nepal": "np",
    "Netherlands": "nl",
    "New Zealand": "nz",
    "Niger": "ne",
    "Nigeria": "ng",
    "North Korea": "kp",
    "Norway": "no",
    "Pakistan": "pk",
    "Palestine": "ps",
    "Panama": "pa",
    "Papua New Guinea": "pg",
    "Paraguay": "py",
    "Philippines": "ph",
    "Poland": "pl",
    "Portugal": "pt",
    "Qatar": "qa",
    "Romania": "ro",
    "Russia": "ru",
    "Rwanda": "rw",
    "Saudi Arabia": "sa",
    "Senegal": "sn",
    "Serbia": "rs",
    "Singapore": "sg",
    "Slovakia": "sk",
    "Somalia": "so",
    "South Africa": "za",
    "South Korea": "kr",
    "Sudan": "sd",
    "Sweden": "se",
    "Switzerland": "ch",
    "Syria": "sy",
    "Taiwan": "tw",
    "Thailand": "th",
    "Timor-Leste": "tl",
    "Tunisia": "tn",
    "Turkey": "tr",
    "Uganda": "ug",
    "Ukraine": "ua",
    "United Kingdom": "gb",
    "United States": "us",
    "Uruguay": "uy",
    "Uzbekistan": "uz",
    "Venezuela": "ve",
    "Vietnam": "vn",
    "Yemen": "ye",
    "Zimbabwe": "zw",
}


def _situation_html() -> str:
    """Cached LLM situation report as HTML paragraphs (empty hint if not generated)."""
    import html as _html

    if not SITUATION.exists():
        return (
            '<p class="muted">No cached report. Run '
            "<code>python examples/synthesize_situation.py</code> (needs Ollama).</p>"
        )
    text = json.loads(SITUATION.read_text(encoding="utf-8")).get("text", "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    items = [ln.lstrip("-•*").strip() for ln in lines if ln.lstrip()[:1] in "-•*"]
    if items:
        return "<ul>" + "".join(f"<li>{_html.escape(i)}</li>" for i in items) + "</ul>"
    return "".join(f"<p>{_html.escape(b.strip())}</p>" for b in text.split("\n\n") if b.strip())


def main() -> None:
    if not CAMEO.exists():
        print(f"{CAMEO} not found — run extract_cameo.py first.")
        return
    # directed dyads: subject -> object (who acts on whom), net sign per (a, b, layer)
    cameo = json.loads(CAMEO.read_text(encoding="utf-8"))
    directed: dict[str, dict[tuple[str, str], int]] = {lay: {} for lay in LAYERS}
    actors: set[str] = set()
    for e in cameo:
        a, b = _actor(e["a"]), _actor(e["b"])
        if not a or not b or a == b or e["domain"] not in directed:
            continue
        directed[e["domain"]][(a, b)] = directed[e["domain"]].get((a, b), 0) + e["sign"]
        actors.update((a, b))
    dyads = {lay: [[a, b, s] for (a, b), s in d.items() if s] for lay, d in directed.items()}
    countries = sorted(actors)  # alphabetical for the pair dropdowns
    data = {"layers": LAYERS, "dyads": dyads, "countries": countries}

    isos = {ISO2[c] for c in actors if c in ISO2}
    flags = _flag_uris(isos)
    flags_by_country = {c: flags[ISO2[c]] for c in actors if c in ISO2 and ISO2[c] in flags}

    sit = json.loads(SITUATION.read_text(encoding="utf-8")) if SITUATION.exists() else {}
    pairs_js = {
        k: {"text": v.get("text", ""), "edges": v.get("edges", [])}
        for k, v in sit.get("pairs", {}).items()
    }
    countries_js = {
        k: {"text": v.get("text", ""), "interactions": v.get("interactions", [])}
        for k, v in sit.get("countries", {}).items()
    }
    page = (
        _TEMPLATE.replace("__DATA__", json.dumps(data))
        .replace("__SITUATION__", _situation_html())
        .replace("__PAIRS__", json.dumps(pairs_js))
        .replace("__COUNTRIES__", json.dumps(countries_js))
        .replace("__FLAGS__", json.dumps(flags_by_country))
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB) — open in a browser (WebGL)")


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>GeoNexus — 3D country network</title>
<style>
  body { margin:0; color:#e2e8f0; overflow:hidden;
    background:radial-gradient(ellipse at 50% 38%, #0e1730 0%, #070b15 55%, #04060d 100%);
    font-family:"Segoe UI",system-ui,-apple-system,sans-serif; }
  #hud { position:fixed; top:0; left:0; right:0; z-index:10; padding:14px 22px;
    background:linear-gradient(180deg,#070b15ee 0%,#070b1500 100%); }
  #hud h1 { margin:0; font-size:18px; font-weight:700; letter-spacing:.3px; }
  #hud h1 span { color:#7dd3fc; }
  #hud p { margin:5px 0 9px; font-size:12.5px; color:#8b9bb4; max-width:780px; }
  .btn { background:#172033cc; border:1px solid #2b3a52; color:#cbd5e1; font-size:13px;
    padding:6px 13px; border-radius:999px; cursor:pointer; margin-right:5px;
    transition:all .15s; }
  .btn:hover { border-color:#475569; background:#1e293b; }
  .btn.on { background:#2563eb; border-color:#3b82f6; color:#fff; }
  select { background:#172033cc; color:#cbd5e1; border:1px solid #2b3a52;
    border-radius:999px; padding:5px 12px; font-size:13px; margin-right:4px; }
  #pair { margin-top:9px; font-size:13px; color:#8b9bb4; }
  #g { position:fixed; inset:0; z-index:1; }
  #report { position:fixed; top:0; right:0; width:380px; max-width:90vw; height:100%;
    z-index:20; background:#0f172af2; border-left:1px solid #334155; padding:20px 22px;
    overflow:auto; transform:translateX(100%); transition:transform .25s;
    backdrop-filter:blur(3px); }
  #report.open { transform:translateX(0); }
  #report h2 { margin:0 0 4px; font-size:16px; }
  #report .muted2 { color:#64748b; font-size:11.5px; margin:0 0 12px; }
  #report p { font-size:13.5px; line-height:1.55; color:#cbd5e1; }
  #report ul { margin:6px 0 10px; padding-left:18px; }
  #report li { font-size:13.5px; line-height:1.5; margin:5px 0; color:#cbd5e1; }
  #report code { background:#1e293b; padding:1px 5px; border-radius:4px; }
  #report .ev { margin-top:5px; font-size:13px; }
  #report .why { color:#94a3b8; font-size:12px; margin:1px 0 0 16px; font-style:italic; }
  #rptclose { float:right; cursor:pointer; color:#94a3b8; font-size:18px; border:none;
    background:none; }
</style>
<!-- single shared three instance (importmap) so label sprites render correctly;
     three/ prefix covers subpaths like three/webgpu that 3d-force-graph imports -->
<script type="importmap">
{ "imports": {
  "three": "https://esm.sh/three@0.160.0",
  "three/": "https://esm.sh/three@0.160.0/"
} }
</script>
</head><body>
<div id="hud">
  <h1><span>GeoNexus</span> — 3D country network</h1>
  <p>Link colour = domain · dots = sign
     (<span style="color:#4ade80">green coop</span> /
     <span style="color:#f87171">red conflict</span>) · arrow = who acted (subject → object).
     Click a country for its summary; empty space resets.</p>
  <div id="btns"></div>
  <div id="pair">Focus a pair:
    <select id="pa"></select> <select id="pb"></select>
    <button class="btn" id="clr">show all</button>
    <button class="btn" id="rpt">📄 Situation report</button>
    <label style="margin-left:10px">Spread
      <input type="range" id="spread" min="40" max="420" value="150" style="vertical-align:middle">
    </label>
    <span id="pairinfo"></span>
  </div>
</div>
<div id="report">
  <button id="rptclose">&times;</button>
  <h2 id="rpttitle">Situation report</h2>
  <p class="muted2" id="rptsub">Written by a local LLM from the signed multi-layer
    signals · cached.</p>
  <div id="rptbody">__SITUATION__</div>
</div>
<div id="g"></div>
<script type="module">
// Primary: one shared three (ES modules) -> always-on hub labels, no black box.
// Fallback: UMD 3d-force-graph -> still navigable, names on hover.
let ForceGraph3D = null, SpriteText = null;
try {
  ForceGraph3D = (await import('https://esm.sh/3d-force-graph?external=three')).default;
  SpriteText = (await import('https://esm.sh/three-spritetext?external=three')).default;
} catch (e) {
  try {
    await new Promise((res, rej) => {
      const sc = document.createElement('script');
      sc.src = 'https://unpkg.com/3d-force-graph';
      sc.onload = res; sc.onerror = rej;
      document.head.appendChild(sc);
    });
    ForceGraph3D = window.ForceGraph3D;  // SpriteText stays null -> hover labels only
  } catch (e2) {
    document.getElementById('g').innerHTML =
      '<p style="color:#f87171;padding:140px 40px">Could not load the 3D libraries '
      + '(needs an internet connection).</p>';
    throw e2;
  }
}
// same three instance as 3d-force-graph -> flag sprites render; optional, fails soft
let THREE = null;
try { THREE = await import('https://esm.sh/three@0.160.0'); } catch (e) { /* no flags */ }
const D = __DATA__;
const PAIRS = __PAIRS__;  // per-pair: {text (LLM summary), edges:[{domain,cameo,sign,why}]}
const COUNTRIES = __COUNTRIES__;  // per-country: {text (LLM summary), interactions:[...]}
const FLAGS = __FLAGS__;  // country -> base64 flag data-URI (blocs absent -> coloured sphere)
const SPHERE_GEO = THREE ? new THREE.SphereGeometry(1, 14, 14) : null;

// preload every flag (base64 -> 128x128 canvas -> CanvasTexture) BEFORE building nodes,
// so each material is created WITH its map (assigning map after first render renders black)
const FLAG_TEX = {};
if (THREE) {
  await Promise.all(Object.entries(FLAGS).map(([name, uri]) => new Promise(res => {
    const img = new Image();
    img.onload = () => {
      const cv = document.createElement('canvas');
      cv.width = 128; cv.height = 128;
      cv.getContext('2d').drawImage(img, 0, 0, 128, 128);
      const t = new THREE.CanvasTexture(cv);
      t.colorSpace = THREE.SRGBColorSpace;
      FLAG_TEX[name] = t;
      res();
    };
    img.onerror = () => res();
    img.src = uri;
  })));
}
const esc = s => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
function bulletize(text) {  // render LLM bullet output as a list (fallback: paragraph)
  const lines = text.split('\n').map(x => x.trim()).filter(Boolean);
  const items = lines.filter(l => /^[-•*]/.test(l)).map(l => l.replace(/^[-•*]\s*/, ''));
  return items.length
    ? '<ul>' + items.map(i => `<li>${esc(i)}</li>`).join('') + '</ul>'
    : '<p>' + esc(text) + '</p>';
}
const LAYERS = D.layers;
const active = new Set(LAYERS);  // multi-select: all layers on by default
const HUBS = 16;                 // how many top countries get a permanent label
let pair = [null, null];         // when both set: show only the pair + direct neighbours
let selectedCountry = null;      // when a node is clicked: show that country's summary
const LAYER_COLOR = {            // link colour = domain; conflict shown via moving particles
  military: '#ef4444', economic: '#f59e0b', diplomatic: '#3b82f6',
  energy: '#a855f7', health: '#10b981',
};

function graphFor(activeSet) {
  // one link per (dyad, layer) so link colour can show the domain (no aggregation)
  const links = [], nbr = {};
  for (const L of activeSet) for (const [a, b, s] of D.dyads[L]) {
    if (!s) continue;
    links.push({ source: a, target: b, net: s, layer: L });
    (nbr[a] = nbr[a] || new Set()).add(b);
    (nbr[b] = nbr[b] || new Set()).add(a);
  }
  const ids = new Set();
  links.forEach(l => { ids.add(l.source); ids.add(l.target); });
  const nodes = [...ids].map(c => ({ id: c, deg: nbr[c] ? nbr[c].size : 1 }));
  // label only the top-degree hubs ("les principaux") to avoid clutter
  const hubSet = new Set([...nodes].sort((x, y) => y.deg - x.deg).slice(0, HUBS).map(n => n.id));
  nodes.forEach(n => { n.labelOn = hubSet.has(n.id); });
  return { nodes, links };
}

let hlNodes = new Set(), hlLinks = new Set();
const NODE_COLOR = n =>  // visual hierarchy by connectivity (bloom makes hubs glow)
  n.deg >= 8 ? '#fcd34d' : n.deg >= 4 ? '#7dd3fc' : '#94a3b8';
const Graph = ForceGraph3D()(document.getElementById('g'))
  .backgroundColor('#070b15')  // solid (transparent + postprocessing can render black)
  .nodeRelSize(4)
  .nodeResolution(14)
  .nodeOpacity(0.95)
  .nodeVal(n => 2 + n.deg)
  .nodeColor(n => (hlNodes.size && !hlNodes.has(n.id)) ? 'rgba(148,163,184,0.25)' : NODE_COLOR(n))
  .nodeLabel('id')  // hover tooltip (and the only labels in UMD fallback mode)
  .nodeThreeObject(n => {
    if (!THREE) return undefined;  // UMD fallback: default sphere + hover labels
    const dim = hlNodes.size > 0 && !hlNodes.has(n.id);
    const focused = hlNodes.size > 0 && hlNodes.has(n.id);
    const sz = 5 + Math.min(11, n.deg);
    const group = new THREE.Group();
    // coloured sphere keeps the volume (Mesh+colour renders fine everywhere)
    const mesh = new THREE.Mesh(SPHERE_GEO, new THREE.MeshBasicMaterial({
      color: NODE_COLOR(n), transparent: true, opacity: dim ? 0.18 : 0.9,
    }));
    mesh.scale.setScalar(sz * 0.4);
    group.add(mesh);
    // flag as a billboard sprite on the sphere — same Sprite+CanvasTexture path as labels
    const tex = FLAG_TEX[n.id];
    if (tex) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({
        map: tex, transparent: true, opacity: dim ? 0.25 : 1, depthTest: false,
      }));
      sp.scale.set(sz * 0.85, sz * 0.57, 1);  // flags are ~3:2
      sp.renderOrder = 3;
      group.add(sp);
    }
    if (SpriteText && (focused || n.labelOn)) {  // label hubs + the focused node
      const t = new SpriteText(n.id);
      t.backgroundColor = 'rgba(7,11,21,0.5)'; t.padding = 1.5; t.borderRadius = 3;
      t.color = dim ? 'rgba(200,210,225,0.25)' : '#f8fafc';
      t.textHeight = 6 + Math.min(5, n.deg); t.fontWeight = '600';
      t.position.set(0, sz * 0.9 + 3, 0);
      group.add(t);
    }
    return group;
  })
  .nodeThreeObjectExtend(false)
  .linkColor(l => {
    const base = LAYER_COLOR[l.layer] || '#94a3b8';
    if (!hlLinks.size) return base;
    return hlLinks.has(l) ? base : 'rgba(100,116,139,0.04)';  // distant flows recede
  })
  .linkWidth(l => Math.min(5, 0.6 + Math.abs(l.net)))
  .linkCurvature(l => (LAYERS.indexOf(l.layer) - 2) * 0.12)  // fan parallel layer edges
  .linkOpacity(0.5)
  // a focus dims/hides the distant flows: only the selected country's links keep dots/arrows
  .linkDirectionalParticles(l =>
    (hlLinks.size && !hlLinks.has(l)) ? 0 : 2 + Math.min(4, Math.abs(l.net)))
  .linkDirectionalParticleWidth(3)
  .linkDirectionalParticleSpeed(l => (l.net < 0 ? 0.0025 : 0.0014))
  .linkDirectionalParticleColor(l => (l.net > 0 ? '#4ade80' : '#f87171'))
  .linkDirectionalArrowLength(l => (hlLinks.size && !hlLinks.has(l)) ? 0 : 3.5)
  .linkDirectionalArrowRelPos(1)
  .linkDirectionalArrowColor(l => LAYER_COLOR[l.layer] || '#888')
  .linkLabel(l => {  // hover tooltip: who acts on whom, domain, stance, and the reason
    const a = l.source.id || l.source, b = l.target.id || l.target;
    const p = PAIRS[[a, b].sort().join('|')];
    const stance = l.net > 0 ? 'cooperation' : 'conflict';
    const m = p && p.edges ? p.edges.find(e => e.domain === l.layer && e.why) : null;
    const col = LAYER_COLOR[l.layer] || '#888';
    return `<div style="max-width:280px"><b>${a} → ${b}</b> `
      + `<span style="color:#94a3b8">(${a} acted toward ${b})</span><br>`
      + `<span style="color:${col}">${l.layer}</span> · ${stance}`
      + (m ? `<br><i style="color:#cbd5e1">${esc(m.why)}</i>` : '') + '</div>';
  })
  .onNodeClick(node => {
    hlNodes = new Set([node.id]); hlLinks = new Set();
    Graph.graphData().links.forEach(l => {
      const s = l.source.id || l.source, t = l.target.id || l.target;
      if (s === node.id || t === node.id) {
        hlLinks.add(l); hlNodes.add(s); hlNodes.add(t);
      }
    });
    Graph.nodeThreeObject(Graph.nodeThreeObject());  // refresh labels
    Graph.linkColor(Graph.linkColor()); Graph.nodeColor(Graph.nodeColor());
    Graph.linkDirectionalParticles(Graph.linkDirectionalParticles());
    Graph.linkDirectionalArrowLength(Graph.linkDirectionalArrowLength());
    const d = 80, r = 1 + d / Math.hypot(node.x, node.y, node.z || 1);  // closer standoff
    Graph.cameraPosition({ x: node.x * r, y: node.y * r, z: node.z * r }, node, 1000);
    selectedCountry = node.id;  // panel content updates; user opens it via the button
    renderPanel();
  })
  .onBackgroundClick(() => {
    hlNodes = new Set(); hlLinks = new Set(); selectedCountry = null;
    Graph.nodeThreeObject(Graph.nodeThreeObject());
    Graph.linkColor(Graph.linkColor()); Graph.nodeColor(Graph.nodeColor());
    Graph.linkDirectionalParticles(Graph.linkDirectionalParticles());
    Graph.linkDirectionalArrowLength(Graph.linkDirectionalArrowLength());
    renderPanel();
  });

Graph.d3Force('charge').strength(-150);  // more repulsion -> a more legible, spread layout

const spread = document.getElementById('spread');  // live spread control
spread.oninput = () => {
  Graph.d3Force('charge').strength(-(+spread.value));
  Graph.d3ReheatSimulation();
};

const lid = l => l.source.id || l.source;       // link endpoints can be id or node obj
const tid = l => l.target.id || l.target;

function currentData() {
  const g = graphFor(active);
  const [a, b] = pair;
  if (!a || !b) return g;
  // keep the pair + every node directly connected to A or B, and edges among them
  const keep = new Set([a, b]);
  for (const l of g.links) {
    const s = lid(l), t = tid(l);
    if (s === a || t === a || s === b || t === b) { keep.add(s); keep.add(t); }
  }
  return {
    nodes: g.nodes.filter(n => keep.has(n.id)).map(n => ({ ...n, labelOn: true })),
    links: g.links.filter(l => keep.has(lid(l)) && keep.has(tid(l))),
  };
}

function redraw() {
  hlNodes = new Set(); hlLinks = new Set();
  Graph.graphData(currentData());
  const [a, b] = pair;
  document.getElementById('pairinfo').textContent =
    a && b ? `— showing ${a} & ${b} and their direct links` : '';
  renderPanel();
}

const btns = document.getElementById('btns');
LAYERS.forEach(lay => {  // multi-select: each button toggles a layer on/off
  const b = document.createElement('button');
  b.className = 'btn'; b.textContent = lay;
  const col = LAYER_COLOR[lay];
  const paint = () => {  // colour the button by its layer so it maps to link colour
    const on = active.has(lay);
    b.style.background = on ? col : '#1e293b';
    b.style.color = on ? '#0b1020' : col;
    b.style.borderColor = col;
  };
  paint();
  b.onclick = () => {
    if (active.has(lay)) active.delete(lay); else active.add(lay);
    if (active.size === 0) active.add(lay);  // keep ≥1
    paint(); redraw();
  };
  btns.appendChild(b);
});

const pa = document.getElementById('pa'), pb = document.getElementById('pb');
function fill(sel) {
  sel.appendChild(new Option('—', ''));
  D.countries.forEach(c => sel.appendChild(new Option(c, c)));
}
fill(pa); fill(pb);
pa.onchange = pb.onchange = () => {
  pair = [pa.value || null, pb.value || null];
  selectedCountry = null;
  redraw();  // panel content updates; user opens it via the Situation report button
};
document.getElementById('clr').onclick = () => {
  pa.value = ''; pb.value = ''; pair = [null, null]; selectedCountry = null; redraw();
};

const report = document.getElementById('report');
const GLOBAL_HTML = document.getElementById('rptbody').innerHTML;

function _interactionRows(items, withField) {
  return items.map(e => {
    const why = e.why ? `<div class="why">${esc(e.why)}</div>` : '';
    const who = withField ? `${esc(e.with)} · ` : '';
    return `<div class="ev"><span style="color:${LAYER_COLOR[e.domain] || '#888'}">●</span> `
      + `${who}${esc(e.domain)}: ${esc(e.cameo)} (${e.sign > 0 ? '+' : ''}${e.sign})</div>${why}`;
  }).join('');
}

function renderPanel() {
  const [a, b] = pair;
  const title = document.getElementById('rpttitle');
  const sub = document.getElementById('rptsub');
  const body = document.getElementById('rptbody');

  if (a && b) {  // a focused pair
    const p = PAIRS[[a, b].sort().join('|')];
    title.textContent = a + ' & ' + b;
    if (!p || (!p.text && !(p.edges && p.edges.length))) {
      sub.textContent = '';
      body.innerHTML = '<p class="muted">No direct interactions recorded between these two.</p>';
      return;
    }
    sub.textContent = 'Pair summary (LLM + interactions, cached) · media-derived.';
    body.innerHTML = (p.text ? bulletize(p.text) : '')
      + (p.edges && p.edges.length
        ? '<p class="muted2">Interactions &amp; reasons</p>'
          + _interactionRows(p.edges, false) : '');
    return;
  }

  if (selectedCountry) {  // a clicked country
    const c = COUNTRIES[selectedCountry];
    title.textContent = selectedCountry;
    if (!c || (!c.text && !(c.interactions && c.interactions.length))) {
      sub.textContent = '';
      body.innerHTML = '<p class="muted">No summary recorded for this country.</p>';
      return;
    }
    sub.textContent = 'Country summary (LLM + interactions, cached) · media-derived.';
    body.innerHTML = (c.text ? bulletize(c.text) : '')
      + (c.interactions && c.interactions.length
        ? '<p class="muted2">Interactions &amp; reasons</p>'
          + _interactionRows(c.interactions, true) : '');
    return;
  }

  title.textContent = 'Situation report';  // global
  sub.textContent = 'Written by a local LLM from the signed multi-layer signals · cached.';
  body.innerHTML = GLOBAL_HTML;
}
document.getElementById('rpt').onclick = () => report.classList.toggle('open');
document.getElementById('rptclose').onclick = () => report.classList.remove('open');
redraw();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
