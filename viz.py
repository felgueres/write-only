import math, argparse
import matplotlib.pyplot as plt
import networkx as nx
from rdflib import Namespace, URIRef
from nx_loader import load_rdf
from pyvis.network import Network
import json

KG     = Namespace("https://your.name/kg/")
SCHEMA = Namespace("http://schema.org/")
SKOS   = Namespace("http://www.w3.org/2004/02/skos/core#")

# ---------- helpers ----------
def resolve_curie(s:str)->URIRef:
    s = s.strip()
    if s.startswith("kg:"): return URIRef(str(KG)+s[3:])
    if s.startswith("http://") or s.startswith("https://"): return URIRef(s)
    return URIRef(str(KG)+s)  # last resort

def label_book(rdf, b):  return str(rdf.value(b, SCHEMA.name) or b)
def label_concept(rdf, c): return str(rdf.value(c, SKOS.prefLabel) or rdf.value(c, SCHEMA.name) or c)

# ---------- View A: Concept -> Books (collapse highlights) ----------
def concept_to_books(rdf, concept_iri):
    G = nx.DiGraph()
    cname = label_concept(rdf, concept_iri)
    for h in rdf.subjects(KG.refersToConcept, concept_iri):
        for b in rdf.objects(h, KG.inBook):
            G.add_node(concept_iri, kind="Concept", label=cname)
            G.add_node(b, kind="Book", label=label_book(rdf, b))
            w = G[concept_iri][b]["weight"]+1 if G.has_edge(concept_iri,b) else 1
            G.add_edge(concept_iri, b, weight=w)
    return G

def plot_concept_books(G):
    if G.number_of_edges()==0:
        print("No books for this concept."); return
    # bar chart
    rows = sorted(((G.nodes[b]["label"], d["weight"]) for _,b,d in G.edges(data=True)),
                  key=lambda x:x[1], reverse=True)
    labs, vals = [r[0] for r in rows], [r[1] for r in rows]
    plt.figure(figsize=(10, max(4,0.4*len(labs))))
    plt.barh(labs[::-1], vals[::-1])
    plt.xlabel("Mentions (highlights)"); plt.title(f"Books for concept: {G.nodes[list(G.nodes)[0]].get('label','Concept')}")
    plt.tight_layout(); plt.show()

    # small network (concept center → books)
    pos = {}
    center = [n for n,d in G.nodes(data=True) if d.get("kind")=="Concept"][0]
    pos[center] = (0,0)
    books = [n for n,d in G.nodes(data=True) if d.get("kind")=="Book"]
    for i,b in enumerate(books):
        pos[b] = (1, -i)
    widths = [1+math.log(d["weight"]) for _,_,d in G.edges(data=True)]
    plt.figure(figsize=(8, max(4,0.3*len(books))))
    nx.draw_networkx_nodes(G, pos, nodelist=[center], node_color="tab:purple", node_size=500)
    nx.draw_networkx_nodes(G, pos, nodelist=books, node_color="tab:blue", node_size=250)
    nx.draw_networkx_edges(G, pos, width=widths, arrows=False, alpha=0.6)
    nx.draw_networkx_labels(G, pos, {center:G.nodes[center]["label"]}, font_size=10)
    nx.draw_networkx_labels(G, pos, {b:G.nodes[b]["label"][:40] for b in books}, font_size=8)
    plt.axis("off"); plt.tight_layout(); plt.show()

# ---------- View B: Book↔Book similarity by shared concepts ----------
def book_similarity_by_concepts(rdf, min_shared=2, top_edges=200):
    # build counts: for each highlight h with refersToConcept c and inBook b, increment (b,c)
    bc = {}
    books = set(); concepts = set()
    for h,b in rdf.subject_objects(KG.inBook):
        books.add(b)
        for c in rdf.objects(h, KG.refersToConcept):
            concepts.add(c)
            bc[(b,c)] = bc.get((b,c), 0) + 1

    # index: for each concept, which books mention it
    concept_books = {}
    for (b,c), _ in bc.items():
        concept_books.setdefault(c, set()).add(b)

    # weighted undirected Book–Book graph
    S = nx.Graph()
    for b in books:
        S.add_node(b, kind="Book", label=label_book(rdf,b))
    for c, bs in concept_books.items():
        bs = list(bs)
        for i in range(len(bs)):
            for j in range(i+1, len(bs)):
                u, v = bs[i], bs[j]
                w = S[u][v]["weight"]+1 if S.has_edge(u,v) else 1
                S.add_edge(u, v, weight=w)

    # prune weak edges
    S.remove_edges_from([(u,v) for u,v,d in S.edges(data=True) if d["weight"]<min_shared])
    if top_edges and S.number_of_edges()>top_edges:
        # keep top N by weight
        edges_sorted = sorted(S.edges(data=True), key=lambda e: e[2]["weight"], reverse=True)[:top_edges]
        keep = {(u,v) for u,v,_ in edges_sorted}
        S.remove_edges_from([e for e in S.edges if e not in keep and (e[1],e[0]) not in keep])

    # drop isolated
    S.remove_nodes_from([n for n in list(S.nodes) if S.degree(n)==0])
    return S

def plot_book_similarity(S):
    if S.number_of_nodes()==0: 
        print("No similar-book edges after pruning."); return
    pos = nx.spring_layout(S, seed=42, k=0.9, weight="weight")
    widths = [1+math.log(d["weight"]) for _,_,d in S.edges(data=True)]
    plt.figure(figsize=(12,10))
    nx.draw_networkx_edges(S, pos, width=widths, alpha=0.35)
    nx.draw_networkx_nodes(S, pos, node_color="tab:blue", node_size=260)
    nx.draw_networkx_labels(S, pos, {n:S.nodes[n]["label"][:40] for n in S.nodes()}, font_size=8)
    plt.title("Book ↔ Book similarity (shared concepts)")
    plt.axis("off"); plt.tight_layout(); plt.show()

def highlights_for_concept(rdf, concept_iri, max_per_book=10, snippet=180):
    out = {}
    for h in rdf.subjects(KG.refersToConcept, concept_iri):
        b = next(rdf.objects(h, KG.inBook), None)
        if not b: continue
        txt = str(rdf.value(h, KG.highlightText) or "")
        loc = str(rdf.value(h, KG.atLocation) or "")
        out.setdefault(b, []).append((txt, loc, h))
    # sort by length desc or leave as-is
    for b in out:
        out[b] = out[b][:max_per_book]
    return out

def concept_browser_all(rdf, out_html="concept_browser.html",
                        max_books_per_concept=200, max_highlights_per_book=200):
    # ---- build index: concept -> book -> [highlights + entities] ----
    SCHEMA = Namespace("http://schema.org/")
    SKOS   = Namespace("http://www.w3.org/2004/02/skos/core#")

    def label_book(b):    return str(rdf.value(b, SCHEMA.name) or b)
    def label_concept(c): return str(rdf.value(c, SKOS.prefLabel) or rdf.value(c, SCHEMA.name) or c)
    def label_entity(e):  return str(rdf.value(e, SKOS.prefLabel) or rdf.value(e, SCHEMA.name) or e)

    cbh = {}   # concept -> {book -> {"highlights": [...], "entities": set()}}
    for h, b in rdf.subject_objects(KG.inBook):
        for c in rdf.objects(h, KG.refersToConcept):
            txt = str(rdf.value(h, KG.highlightText) or "")
            ents = [label_entity(e) for e in rdf.objects(h, KG.mentionsEntity)]
            slot = cbh.setdefault(c, {}).setdefault(b, {"highlights": [], "entities": set()})
            slot["highlights"].append(txt)
            slot["entities"].update(ents)

    # serialize to JSON (sorted, capped)
    concepts = []
    for c, books in cbh.items():
        books_rows = []
        for b, data in books.items():
            hls = data["highlights"][:max_highlights_per_book]
            ents = list(data["entities"])
            books_rows.append((b, label_book(b), len(hls), hls, ents))
        books_rows = sorted(books_rows, key=lambda x: x[2], reverse=True)[:max_books_per_concept]

        concepts.append({
            "id": str(c),
            "label": label_concept(c),
            "total": sum(n for _, _, n, _, _ in books_rows),
            "books": [
                {"id": str(b), "label": blabel, "count": n,
                 "highlights": hls, "entities": ents}
                for (b, blabel, n, hls, ents) in books_rows
            ],
        })

    concepts.sort(key=lambda d: (-d["total"], d["label"].lower()))

    import json
    DATA = json.dumps(concepts)

    # ---- dump minimal HTML (3 columns, inline entity highlighting) ----
    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>Concept Browser</title>
<style>
  html,body { margin:0; height:100%; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
  #app { display:flex; height:100vh; }
  .col { flex:1; border-right:1px solid #e5e7eb; overflow:auto; padding:10px 12px; }
  .col:last-child { border-right:none; }
  h2 { margin:0 0 8px 0; font-size:14px; font-weight:600; color:#374151; }
  .search { width:100%; box-sizing:border-box; padding:6px 8px; margin-bottom:8px; border:1px solid #e5e7eb; border-radius:6px; }
  ul { list-style:none; margin:0; padding:0; }
  li.item { padding:6px 8px; border-radius:6px; cursor:pointer; display:flex; justify-content:space-between; gap:8px; }
  li.item:hover { background:#f3f4f6; }
  .badge { padding:0 8px; background:#eef2ff; color:#4338ca; border-radius:999px; font-size:12px; }
  .muted { color:#6b7280; font-size:12px; }
  .hl { border-bottom:1px solid #e5e7eb; padding:8px 0; font-size:14px; }
  .ent { border-bottom: 2px solid #ef4444; background: #fff1f2; }
</style>
</head>
<body>
<div id="app">
  <div class="col">
    <h2>Concepts</h2>
    <input id="concept-search" class="search" placeholder="Filter concepts…" />
    <ul id="concepts"></ul>
  </div>
  <div class="col">
    <h2 id="books-title" class="muted">Books</h2>
    <ul id="books"></ul>
  </div>
  <div class="col">
    <h2 id="highlights-title" class="muted">Highlights</h2>
    <div id="highlights"></div>
  </div>
</div>

<script>
const DATA = REPLACE_DATA;
const $ = s => document.querySelector(s);
const listConcepts = $('#concepts'), listBooks = $('#books'), listHL = $('#highlights');
const booksTitle = $('#books-title'), hlTitle = $('#highlights-title');
const searchInput = $('#concept-search');

function el(tag, attrs={}, ...children) {
  const n = document.createElement(tag);
  for (const [k,v] of Object.entries(attrs)) {
    if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else n.setAttribute(k, v);
  }
  for (const c of children) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  return n;
}

function escapeReg(s){ return s.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'); }

function highlightEntities(text, entityLabels) {
  if (!entityLabels.length) return text;
  const sorted = [...new Set(entityLabels)].sort((a,b)=>b.length-a.length).map(escapeReg);
  const re = new RegExp('\\\\b(' + sorted.join('|') + ')\\\\b', 'gi');
  return text.replace(re, (m)=>`<span class="ent">${m}</span>`);
}

function renderConcepts(filter="") {
  listConcepts.innerHTML = '';
  const q = filter.trim().toLowerCase();
  DATA.filter(c => !q || c.label.toLowerCase().includes(q)).forEach(c => {
    const li = el('li', {class:'item'},
      el('span', {text:c.label}),
      el('span', {class:'badge'}, String(c.total))
    );
    li.onclick = () => selectConcept(c);
    listConcepts.appendChild(li);
  });
}

function selectConcept(c) {
  booksTitle.textContent = 'Books – ' + c.label;
  listBooks.innerHTML = '';
  hlTitle.textContent = 'Highlights';
  listHL.innerHTML = '';
  c.books.forEach(b => {
    const li = el('li', {class:'item'},
      el('span', {text:b.label}),
      el('span', {class:'badge'}, String(b.count))
    );
    li.onclick = () => selectBook(c, b);
    listBooks.appendChild(li);
  });
}

function selectBook(c, b) {
  hlTitle.textContent = 'Highlights – ' + b.label;
  listHL.innerHTML = '';
  const entityLabels = b.entities || [];
  b.highlights.forEach(txt => {
    if (!txt) return;
    const html = highlightEntities(txt, entityLabels);
    const div = el('div', {class:'hl'});
    div.innerHTML = html;
    listHL.appendChild(div);
  });
}

searchInput.addEventListener('input', e => renderConcepts(e.target.value));
renderConcepts('');
if (DATA.length) selectConcept(DATA[0]);
</script>
</body>
</html>"""

    html = html.replace("REPLACE_DATA", DATA)

    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote", out_html)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="read_graph.jsonld")
    ap.add_argument("--concept", type=str, help="plot Concept→Books for this concept (CURIE/IRI/label)")
    ap.add_argument("--book-sim", action="store_true", help="plot Book↔Book similarity by shared concepts")
    ap.add_argument("--min-shared", type=int, default=2, help="minimum shared concepts to keep a book-book edge")
    ap.add_argument("--top-edges", type=int, default=200, help="cap number of similarity edges (after pruning)")
    ap.add_argument("--browser", action="store_true", help="open 3-column Concept→Books→Highlights browser")

    args = ap.parse_args()

    rdf = load_rdf(args.path)

    if args.browser:
        concept_browser_all(rdf, out_html="concept_browser_1.html", max_highlights_per_book=200)

    if args.concept:
        c = resolve_curie(args.concept)
        G = concept_to_books(rdf, c)

    if args.book_sim:
        S = book_similarity_by_concepts(rdf, min_shared=args.min_shared, top_edges=args.top_edges)
        plot_book_similarity(S)

