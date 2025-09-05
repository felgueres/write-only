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
                        max_books_per_concept=200, max_highlights_per_book=200, 
                        include_shortest_path=True):
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
    
    # ---- build NetworkX graph for shortest path functionality ----
    GRAPH_DATA = "null"
    if include_shortest_path:
        from nx_loader import build_nx, shortest_path
        try:
            G = build_nx(rdf)
            # Export simplified graph structure for client-side pathfinding
            nodes_data = []
            edges_data = []
            
            for node_uri, data in G.nodes(data=True):
                nodes_data.append({
                    'id': str(node_uri),
                    'label': data.get('label', str(node_uri)[-50:]),
                    'types': list(data.get('types', set()))
                })
            
            for u, v, data in G.edges(data=True):
                edges_data.append({
                    'from': str(u),
                    'to': str(v), 
                    'predicate': data.get('predicate', '')
                })
            
            graph_structure = {
                'nodes': nodes_data,
                'edges': edges_data
            }
            GRAPH_DATA = json.dumps(graph_structure)
        except Exception as e:
            print(f"Warning: Could not build graph data for shortest path: {e}")
            GRAPH_DATA = "null"

    # ---- dump minimal HTML (3 columns, inline entity highlighting) ----
    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>Concept Browser</title>
<script src="https://unpkg.com/cytoscape@3.26.0/dist/cytoscape.min.js"></script>
<style>
  html,body { margin:0; height:100%; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
  #app { display:flex; height:100vh; }
  .col { flex:0 0 200px; border-right:1px solid #e5e7eb; overflow:auto; padding:10px 12px; }
  .col.first-col { flex:0 0 220px; max-width:240px; min-width:160px; }
  .path-col { flex:1; min-width:500px; }
  .col:last-child { border-right:none; }
  h2 { margin:0 0 8px 0; font-size:14px; font-weight:600; color:#374151; }
  .search { width:100%; box-sizing:border-box; padding:6px 8px; margin-bottom:8px; border:1px solid #e5e7eb; border-radius:6px; }
  ul { list-style:none; margin:0; padding:0; }
  li.item { padding:6px 8px; border-radius:6px; cursor:pointer; display:flex; justify-content:space-between; gap:8px; }
  li.item:hover { background:#f3f4f6; }
  .badge { padding:2px 6px; background:#eef2ff; color:#4338ca; border-radius:10px; font-size:11px; min-width:20px; text-align:center; white-space:nowrap; height:18px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
  .muted { color:#6b7280; font-size:12px; }
  .hl { border-bottom:1px solid #e5e7eb; padding:8px 0; font-size:14px; }
  .ent { border-bottom: 2px solid #ef4444; background: #fff1f2; }
  .path-input { width:100%; box-sizing:border-box; padding:6px 8px; margin:2px 0; border:1px solid #e5e7eb; border-radius:4px; }
  .path-btn { padding:6px 12px; background:#3b82f6; color:white; border:none; border-radius:4px; cursor:pointer; margin:4px 0; }
  .path-btn:hover { background:#2563eb; }
  .path-result { margin:8px 0; padding:8px; border:1px solid #e5e7eb; border-radius:4px; background:#f9fafb; }
  .path-node { padding:4px 8px; margin:2px 0; border-radius:4px; font-size:12px; }
  .path-book { background:#dbeafe; color:#1e40af; }
  .path-entity { background:#fef3c7; color:#92400e; }
  .path-highlight { background:#f3e8ff; color:#7c2d12; }
  .suggestions { position:relative; max-height:150px; overflow-y:auto; border:1px solid #e5e7eb; border-radius:4px; background:white; display:none; }
  .suggestions:not(:empty) { display:block; }
  .suggestions .item { padding:6px 8px; cursor:pointer; border-bottom:1px solid #f3f4f6; }
  .suggestions .item:hover { background:#f3f4f6; }
  .suggestions .item:last-child { border-bottom:none; }
  #cy { width:100%; height:400px; border:1px solid #e5e7eb; border-radius:4px; margin-top:8px; background:#fafafa; }
  .path-controls { margin-bottom:8px; }
  .path-info { font-size:12px; color:#6b7280; margin:4px 0; }
</style>
</head>
<body>
<div id="app">
  <div class="col first-col">
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
  <div class="col path-col">
    <h2>Shortest Path</h2>
    <div class="path-controls">
      <input id="path-from" class="path-input" placeholder="From (search nodes...)" />
      <div id="from-suggestions" class="suggestions"></div>
      <input id="path-to" class="path-input" placeholder="To (search nodes...)" />
      <div id="to-suggestions" class="suggestions"></div>
      <button id="find-path" class="path-btn">Find Path</button>
      <div id="path-info" class="path-info"></div>
    </div>
    <div id="cy"></div>
  </div>
</div>

<script>
const DATA = REPLACE_DATA;
const GRAPH_DATA = REPLACE_GRAPH_DATA;
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

// ---- Shortest Path Functionality ----
if (GRAPH_DATA) {
  const pathFromInput = $('#path-from');
  const pathToInput = $('#path-to');
  const findPathBtn = $('#find-path');
  const pathInfo = $('#path-info');
  let cy = null;
  
  // Initialize Cytoscape
  function initializeCytoscape() {
    cy = cytoscape({
      container: $('#cy'),
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'font-size': '10px',
            'text-wrap': 'wrap',
            'text-max-width': '80px',
            'text-valign': 'center',
            'text-halign': 'center',
            'background-color': '#ccc',
            'width': '30px',
            'height': '30px'
          }
        },
        {
          selector: 'node[type = "Book"]',
          style: {
            'background-color': '#3b82f6',
            'width': '40px',
            'height': '40px',
            'font-weight': 'bold'
          }
        },
        {
          selector: 'node[type = "Entity"]',
          style: {
            'background-color': '#f59e0b',
            'width': '35px',
            'height': '35px'
          }
        },
        {
          selector: 'node[type = "Highlight"]',
          style: {
            'background-color': '#8b5cf6',
            'width': '25px',
            'height': '25px'
          }
        },
        {
          selector: 'edge',
          style: {
            'width': 2,
            'line-color': '#ddd',
            'target-arrow-color': '#ddd',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier'
          }
        },
        {
          selector: '.path',
          style: {
            'line-color': '#ef4444',
            'target-arrow-color': '#ef4444',
            'width': 4,
            'z-index': 999
          }
        },
        {
          selector: '.path-node',
          style: {
            'border-width': 3,
            'border-color': '#ef4444',
            'z-index': 999
          }
        }
      ],
      layout: { name: 'preset' },
      elements: []
    });
  }
  
  initializeCytoscape();
  
  // Helper functions
  function getNodeType(types) {
    if (types.some(t => t.includes('Book'))) return 'Book';
    if (types.some(t => t.includes('Entity'))) return 'Entity';
    if (types.some(t => t.includes('Highlight'))) return 'Highlight';
    return 'Other';
  }
  
  function truncateLabel(label, maxLength = 30) {
    return label.length > maxLength ? label.substring(0, maxLength) + '…' : label;
  }
  
  // Search nodes for autocomplete
  function searchNodes(query) {
    if (!query || query.length < 2) return [];
    const q = query.toLowerCase();
    return GRAPH_DATA.nodes
      .filter(node => node.label.toLowerCase().includes(q))
      .slice(0, 10);
  }
  
  // Show autocomplete suggestions
  function showSuggestions(input, suggestionsDiv, callback) {
    const query = input.value.trim();
    const suggestions = searchNodes(query);
    
    suggestionsDiv.innerHTML = '';
    suggestions.forEach(node => {
      const div = el('div', {
        class: 'item',
        text: `${node.label} (${node.types.map(t => t.split('/').pop()).join(', ')})`
      });
      div.onclick = () => {
        input.value = node.label;
        input.dataset.nodeId = node.id;
        suggestionsDiv.innerHTML = '';
        callback && callback(node);
      };
      suggestionsDiv.appendChild(div);
    });
  }
  
  // Find and visualize shortest path
  function findAndVisualizePath(fromId, toId) {
    if (!fromId || !toId) {
      pathInfo.textContent = 'Please select valid start and end nodes';
      return;
    }
    
    // Create a temporary graph with path-relevant nodes
    const nodeMap = new Map();
    GRAPH_DATA.nodes.forEach(node => nodeMap.set(node.id, node));
    
    // Build adjacency list for BFS
    const graph = new Map();
    GRAPH_DATA.nodes.forEach(node => graph.set(node.id, new Set()));
    
    GRAPH_DATA.edges.forEach(edge => {
      if (graph.has(edge.from) && graph.has(edge.to)) {
        graph.get(edge.from).add(edge.to);
        graph.get(edge.to).add(edge.from); // Make undirected
      }
    });
    
    // BFS shortest path
    function findPath(start, end) {
      if (start === end) return [start];
      
      const queue = [[start]];
      const visited = new Set([start]);
      
      while (queue.length > 0) {
        const path = queue.shift();
        const current = path[path.length - 1];
        
        for (const neighbor of graph.get(current) || []) {
          if (neighbor === end) {
            return [...path, neighbor];
          }
          
          if (!visited.has(neighbor)) {
            visited.add(neighbor);
            queue.push([...path, neighbor]);
          }
        }
      }
      return null;
    }
    
    const path = findPath(fromId, toId);
    
    if (!path) {
      pathInfo.textContent = 'No path found between selected nodes';
      cy.elements().remove();
      return;
    }
    
    pathInfo.textContent = `Found path with ${path.length} nodes`;
    
    // Only show path nodes, no additional context
    const pathSet = new Set(path);
    const nodesToShow = path;
    
    // Prepare cytoscape elements
    const elements = [];
    
    // Add nodes
    nodesToShow.forEach(nodeId => {
      const node = nodeMap.get(nodeId);
      if (node) {
        elements.push({
          data: {
            id: nodeId,
            label: truncateLabel(node.label),
            type: getNodeType(node.types)
          },
          classes: pathSet.has(nodeId) ? 'path-node' : ''
        });
      }
    });
    
    // Add edges
    GRAPH_DATA.edges.forEach(edge => {
      if (nodesToShow.includes(edge.from) && nodesToShow.includes(edge.to)) {
        const isInPath = pathSet.has(edge.from) && pathSet.has(edge.to) &&
                        (path.indexOf(edge.from) === path.indexOf(edge.to) - 1 ||
                         path.indexOf(edge.to) === path.indexOf(edge.from) - 1);
        
        elements.push({
          data: {
            id: `${edge.from}-${edge.to}`,
            source: edge.from,
            target: edge.to
          },
          classes: isInPath ? 'path' : ''
        });
      }
    });
    
    // Update graph
    cy.elements().remove();
    cy.add(elements);
    
    // Apply layout
    cy.layout({
      name: 'breadthfirst',
      directed: true,
      roots: `#${fromId}`,
      padding: 10,
      spacingFactor: 1.2
    }).run();
    
    // Center on path
    setTimeout(() => {
      cy.fit(cy.nodes('.path-node'), 50);
    }, 100);
  }
  
  // Event listeners
  pathFromInput.addEventListener('input', () => {
    showSuggestions(pathFromInput, $('#from-suggestions'));
  });
  
  pathToInput.addEventListener('input', () => {
    showSuggestions(pathToInput, $('#to-suggestions'));
  });
  
  findPathBtn.addEventListener('click', () => {
    const fromId = pathFromInput.dataset.nodeId;
    const toId = pathToInput.dataset.nodeId;
    findAndVisualizePath(fromId, toId);
  });
  
  // Add click handler to show node info
  cy.on('tap', 'node', function(evt) {
    const node = evt.target;
    pathInfo.textContent = `Selected: ${node.data('label')} (${node.data('type')})`;
  });
  
} else {
  // No graph data available
  const pathCol = $('.path-col');
  if (pathCol) {
    pathCol.innerHTML = '<h2>Shortest Path</h2><div class="muted">Graph data not available</div>';
  }
}
</script>
</body>
</html>"""

    html = html.replace("REPLACE_DATA", DATA)
    html = html.replace("REPLACE_GRAPH_DATA", GRAPH_DATA)

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
        concept_browser_all(rdf, out_html="concept_browser.html", max_highlights_per_book=200)

    if args.concept:
        c = resolve_curie(args.concept)
        G = concept_to_books(rdf, c)

    if args.book_sim:
        S = book_similarity_by_concepts(rdf, min_shared=args.min_shared, top_edges=args.top_edges)
        plot_book_similarity(S)

