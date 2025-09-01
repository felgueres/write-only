# viz_views.py
# pip install rdflib networkx matplotlib pyvis
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
def concept_to_books_two_pane(rdf, concept_iri, out_html="concept_books.html", max_snippets=50):
    net = Network(height="100%", width="100%", directed=False)
    cname = label_concept(rdf, concept_iri)
    cid = str(concept_iri)
    net.add_node(cid, label=cname, color="#8e63c7", shape="dot", size=20, title=cname)

    per_book = {}
    for h in rdf.subjects(KG.refersToConcept, concept_iri):
        b = next(rdf.objects(h, KG.inBook), None)
        if not b: continue
        txt = str(rdf.value(h, KG.highlightText) or "")
        per_book.setdefault(b, []).append({"text": txt, "id": str(h)})

    for b, hs in per_book.items():
        bname = label_book(rdf, b)
        bid = str(b)
        net.add_node(bid, label=(bname[:60] + ("…" if len(bname)>60 else "")), title=bname,
                     color="#4e79a7", shape="dot")
        net.add_edge(cid, bid, value=len(hs))

    net.barnes_hut(gravity=-22000, central_gravity=0.25, spring_length=140, spring_strength=0.02)
    html_str = net.generate_html(notebook=False)

    import json
    highlights_json = json.dumps({str(k): v[:max_snippets] for k, v in per_book.items()})

    INJECT = f"""
<style>
  html,body {{ height:100%; margin:0; }}
  #app {{ display:flex; height:100vh; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }}
  #graph {{ flex: 1 1 60%; min-width:0; height:100vh; }}
  #graph #mynetwork {{ width:100% !important; height:100% !important; }}
  #side {{
    flex: 1 1 40%; max-width: 620px; border-left: 1px solid #e5e7eb; overflow:auto; padding: 12px 14px;
    background:#fafafa;
  }}
  h2 {{ margin:8px 0 12px; font-size:16px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border-bottom: 1px solid #e5e7eb; padding: 8px; text-align: left; vertical-align: top; }}
  .hid {{ color:#9ca3af; font-size:11px; }}
  .muted {{ color:#6b7280; }}
</style>
<div id="app">
  <div id="graph"></div>
  <div id="side">
    <h2 id="side-title">Select a book node to view highlights</h2>
    <div id="meta" class="muted"></div>
    <table id="hl-table" style="display:none;">
      <thead><tr><th style="width:70%;">Highlight</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</div>
<script>
  const HIGHLIGHTS = {highlights_json};

  function renderForBook(bookId, bookLabel) {{
    const tbl = document.getElementById('hl-table');
    const tbody = tbl.querySelector('tbody');
    tbody.innerHTML = '';
    const rows = HIGHLIGHTS[bookId] || [];
    document.getElementById('side-title').textContent = bookLabel || 'Highlights';
    document.getElementById('meta').textContent = rows.length ? (rows.length + ' highlights') : 'No highlights';
    if (!rows.length) {{ tbl.style.display='none'; return; }}
    for (const r of rows) {{
      const tr = document.createElement('tr');
      const tdText = document.createElement('td');
      tdText.textContent = r.text.length > 300 ? r.text.slice(0,300) + '…' : r.text;
      tr.appendChild(tdText);
      tbody.appendChild(tr);
    }}
    tbl.style.display = '';
  }}

  // After pyvis initializes window.network & #mynetwork, mount two-pane and move the canvas.
  (function waitNet(){{
    const netDiv = document.getElementById('mynetwork');
    if (!netDiv || !window.network) return setTimeout(waitNet, 30);

    // Build two-pane and move #mynetwork into #graph
    const graph = document.querySelector('#graph');
    graph.appendChild(netDiv);

    // Ensure sizes
    netDiv.style.width  = '100%';
    netDiv.style.height = '100%';

    // Redraw to fit new container
    try {{ network.redraw(); network.fit(); }} catch(e) {{}}

    // Click to populate table
    network.on('selectNode', function(params){{
      const id = params.nodes[0];
      if (id && HIGHLIGHTS[id]) {{
        let label = id;
        try {{
          const n = network.body.data.nodes.get(id);
          label = (n && n.title) ? n.title : (n && n.label) ? n.label : id;
        }} catch(e) {{}}
        renderForBook(id, label);
      }}
    }});

    // Auto-select the book with most mentions
    const ids = Object.keys(HIGHLIGHTS);
    if (ids.length) {{
      const best = ids.map(id => [id, HIGHLIGHTS[id].length]).sort((a,b)=>b[1]-a[1])[0][0];
      try {{
        const n = network.body.data.nodes.get(best);
        const label = (n && n.title) ? n.title : (n && n.label) ? n.label : best;
        renderForBook(best, label);
        network.selectNodes([best]);
      }} catch(e) {{}}
    }}

    // Resize handling
    window.addEventListener('resize', function(){{
      try {{ network.redraw(); network.fit(); }} catch(e) {{}}
    }});
  }})();
</script>
"""

    # Insert our app shell right after <body>, and keep the original pyvis #mynetwork where it is.
    html_str = html_str.replace("<body>", "<body>" + INJECT)

    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html_str)
    print("wrote", out_html)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="read_graph.jsonld")
    ap.add_argument("--concept", type=str, help="plot Concept→Books for this concept (CURIE/IRI/label)")
    ap.add_argument("--book-sim", action="store_true", help="plot Book↔Book similarity by shared concepts")
    ap.add_argument("--min-shared", type=int, default=2, help="minimum shared concepts to keep a book-book edge")
    ap.add_argument("--top-edges", type=int, default=200, help="cap number of similarity edges (after pruning)")
    args = ap.parse_args()

    rdf = load_rdf(args.path)

    if args.concept:
        c = resolve_curie(args.concept)
        G = concept_to_books(rdf, c)
        plot_concept_books(G)
        concept_to_books_two_pane(rdf, c, out_html="concept_books.html", max_snippets=6)

    if args.book_sim:
        S = book_similarity_by_concepts(rdf, min_shared=args.min_shared, top_edges=args.top_edges)
        plot_book_similarity(S)

