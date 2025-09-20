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
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  html,body { margin:0; height:100%; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
  #app { display:flex; height:100vh; }
  .col { flex:0 0 200px; border-right:1px solid #e5e7eb; overflow:auto; padding:10px 12px; }
  .col.first-col { flex:0 0 220px; max-width:240px; min-width:160px; }
  .graph-col { flex:1; min-width:400px; }
  .control-col { flex:0 0 300px; min-width:280px; }
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
  #network { width:100%; height:calc(100vh - 60px); border:1px solid #e5e7eb; background:#ffffff; }
  .node { font-family: Arial, Helvetica, sans-serif; font-size: 14px; font-weight: bold; }
  .node-rect { fill: white; stroke: black; stroke-width: 1; }
  .node-text { font-family: Arial, Helvetica, sans-serif; fill: black; text-anchor: middle; dominant-baseline: central; }
  .node-text-title { font-size: 12px; font-weight: bold; }
  .node-text-content { font-size: 11px; font-weight: normal; }
  .edge-line { stroke: black; stroke-width: 1; fill: none; }
  .arrow { fill: black; }
  .divider-line { stroke: black; stroke-width: 1; }
  .path-controls { margin-bottom:8px; }
  .path-info { font-size:12px; color:#6b7280; margin:4px 0; }
  .info-panel { position:fixed; top:20px; right:20px; width:400px; max-height:80vh; background:white; border:1px solid #e5e7eb; border-radius:8px; padding:16px; box-shadow:0 10px 25px rgba(0,0,0,0.1); z-index:1000; overflow-y:auto; display:none; }
  .info-panel h3 { margin:0 0 12px 0; font-size:16px; font-weight:600; color:#374151; }
  .info-panel .close-btn { position:absolute; top:12px; right:12px; background:none; border:none; font-size:18px; cursor:pointer; color:#6b7280; }
  .info-panel .close-btn:hover { color:#374151; }
  .info-panel .field { margin-bottom:12px; }
  .info-panel .field-label { font-weight:600; color:#374151; margin-bottom:4px; }
  .info-panel .field-value { color:#6b7280; word-break:break-word; }
  .control-section { margin-bottom:20px; padding-bottom:16px; border-bottom:1px solid #e5e7eb; }
  .control-section:last-child { border-bottom:none; }
  .control-section h3 { margin:0 0 8px 0; font-size:13px; font-weight:600; color:#374151; }
  .node-metadata { padding:12px; background:#f9fafb; border-radius:6px; border:1px solid #e5e7eb; font-size:12px; line-height:1.4; }
  .node-metadata .field { margin-bottom:8px; }
  .node-metadata .field:last-child { margin-bottom:0; }
  .node-metadata .field-label { font-weight:600; color:#374151; margin-bottom:2px; }
  .node-metadata .field-value { color:#6b7280; word-break:break-word; }
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
  <div class="col graph-col">
    <h2 id="graph-title">Graph View</h2>
    <div id="network"></div>
  </div>
  <div class="col control-col">
    <h2>Graph Controls</h2>

    <div class="control-section">
      <h3>Shortest Path</h3>
      <input id="path-from" class="path-input" placeholder="From" />
      <div id="from-suggestions" class="suggestions"></div>
      <input id="path-to" class="path-input" placeholder="To" />
      <div id="to-suggestions" class="suggestions"></div>
      <button id="find-path" class="path-btn">Find Path</button>
      <div id="path-info" class="path-info"></div>
    </div>

    <div class="control-section">
      <h3>Neighborhood</h3>
      <input id="neighborhood-node" class="path-input" placeholder="Select node" />
      <div id="neighborhood-suggestions" class="suggestions"></div>
      <input id="neighborhood-depth" class="path-input" type="number" value="1" min="1" max="3" placeholder="Depth" />
      <button id="explore-neighborhood" class="path-btn">Explore</button>
    </div>

    <div class="control-section">
      <h3>Graph Properties</h3>
      <button id="show-clusters" class="path-btn">Show Clusters</button>
      <button id="show-centrality" class="path-btn">Show Centrality</button>
      <div id="graph-stats" class="path-info"></div>
    </div>

    <div class="control-section">
      <h3>Selected Node</h3>
      <div id="node-metadata" class="node-metadata">
        Click a node to see details
      </div>
    </div>
  </div>
</div>

<div id="info-panel" class="info-panel">
  <button class="close-btn">&times;</button>
  <h3 id="info-title">Node Information</h3>
  <div id="info-content"></div>
</div>

<script>
console.log('Script starting...');

document.addEventListener('DOMContentLoaded', function() {
console.log('DOM loaded, starting main script...');

const DATA = REPLACE_DATA;
const GRAPH_DATA = REPLACE_GRAPH_DATA;

console.log('DATA loaded:', !!DATA, 'length:', DATA ? DATA.length : 0);
console.log('GRAPH_DATA loaded:', !!GRAPH_DATA);

const $ = s => document.querySelector(s);
const listConcepts = $('#concepts'), listBooks = $('#books');
const booksTitle = $('#books-title'), graphTitle = $('#graph-title');
const searchInput = $('#concept-search');

console.log('DOM elements found:', {
  listConcepts: !!listConcepts,
  listBooks: !!listBooks,
  booksTitle: !!booksTitle,
  graphTitle: !!graphTitle,
  searchInput: !!searchInput
});

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
  console.log('selectConcept called with:', c);
  booksTitle.textContent = 'Books – ' + c.label;
  graphTitle.textContent = 'Graph – ' + c.label;
  listBooks.innerHTML = '';

  c.books.forEach(b => {
    const li = el('li', {class:'item'},
      el('span', {text:b.label}),
      el('span', {class:'badge'}, String(b.count))
    );
    li.onclick = () => selectBook(c, b);
    listBooks.appendChild(li);
  });

  // Show concept-books graph
  console.log('About to call showConceptBooksGraph');
  showConceptBooksGraph(c);
}

function selectBook(c, b) {
  graphTitle.textContent = 'Graph – ' + b.label;

  // Show book-highlights-entities graph
  showBookHighlightsGraph(c, b);
}

// ---- Graph Visualization Functions ----
function showConceptBooksGraph(concept) {
  console.log('showConceptBooksGraph called with:', concept);
  console.log('GRAPH_DATA exists:', !!GRAPH_DATA);
  console.log('svg exists:', !!svg);
  console.log('g exists:', !!g);

  if (!GRAPH_DATA) {
    console.log('No GRAPH_DATA, returning');
    return;
  }

  // Create nodes: concept + related books
  const d3Nodes = [];
  const d3Edges = [];
  const nodeMap = new Map();

  // Add concept node
  const conceptNode = {
    id: concept.id,
    type: 'Concept',
    cleanLabel: concept.label,
    data: { id: concept.id, label: concept.label, types: ['Concept'] },
    x: 200,
    y: 150,
    width: 160,
    height: 50,
    style: { fill: '#e9ecef', stroke: '#000000', width: 160, height: 50 }
  };
  d3Nodes.push(conceptNode);
  nodeMap.set(concept.id, conceptNode);

  // Add book nodes in a circle around concept
  const radius = 200;
  const angleStep = (2 * Math.PI) / concept.books.length;

  concept.books.forEach((book, index) => {
    const angle = index * angleStep;
    const x = 200 + radius * Math.cos(angle);
    const y = 150 + radius * Math.sin(angle);

    const bookNode = {
      id: book.id,
      type: 'Book',
      cleanLabel: truncateLabel(book.label, 30),
      data: { id: book.id, label: book.label, types: ['Book'] },
      x: x,
      y: y,
      width: 140,
      height: 40,
      style: { fill: '#f8f9fa', stroke: '#000000', width: 140, height: 40 }
    };
    d3Nodes.push(bookNode);
    nodeMap.set(book.id, bookNode);

    // Add edge from concept to book
    d3Edges.push({
      source: conceptNode,
      target: bookNode
    });
  });

  console.log('About to call renderNetwork with nodes:', d3Nodes.length, 'edges:', d3Edges.length);
  renderNetwork(d3Nodes, d3Edges);
  console.log('renderNetwork call completed');
}

function showBookHighlightsGraph(concept, book) {
  if (!GRAPH_DATA) return;

  // Create a simplified graph showing book + highlights + entities from that book
  const d3Nodes = [];
  const d3Edges = [];

  // Add book node at center
  const bookNode = {
    id: book.id,
    type: 'Book',
    cleanLabel: book.label,
    data: { id: book.id, label: book.label, types: ['Book'] },
    x: 200,
    y: 100,
    width: 160,
    height: 50,
    style: { fill: '#f8f9fa', stroke: '#000000', width: 160, height: 50 }
  };
  d3Nodes.push(bookNode);

  // Add highlights as nodes (simplified - just show count for now)
  const highlightNode = {
    id: book.id + '_highlights',
    type: 'Highlights',
    cleanLabel: `${book.count} highlights`,
    data: { id: book.id + '_highlights', label: `${book.count} highlights`, types: ['Highlights'] },
    x: 50,
    y: 200,
    width: 120,
    height: 40,
    style: { fill: '#e9ecef', stroke: '#000000', width: 120, height: 40 }
  };
  d3Nodes.push(highlightNode);

  d3Edges.push({
    source: bookNode,
    target: highlightNode
  });

  // Add entities as nodes
  if (book.entities && book.entities.length > 0) {
    book.entities.forEach((entity, index) => {
      const entityNode = {
        id: `entity_${index}`,
        type: 'Entity',
        cleanLabel: truncateLabel(entity, 20),
        data: { id: `entity_${index}`, label: entity, types: ['Entity'] },
        x: 350 + (index % 3) * 120,
        y: 150 + Math.floor(index / 3) * 80,
        width: 100,
        height: 35,
        style: { fill: '#ffffff', stroke: '#000000', width: 100, height: 35 }
      };
      d3Nodes.push(entityNode);

      d3Edges.push({
        source: bookNode,
        target: entityNode
      });
    });
  }

  renderNetwork(d3Nodes, d3Edges);
}

// ---- D3.js Network Visualization ----
let svg, g; // Global variables for D3

// Initialize D3 SVG function (global)
function initializeNetwork() {
    console.log('initializeNetwork: d3 available:', typeof d3);
    console.log('initializeNetwork: looking for #network element');

    const container = d3.select('#network');
    console.log('initializeNetwork: container found:', !container.empty());

    container.selectAll('*').remove();
    
    svg = container
      .append('svg')
      .attr('width', '100%')
      .attr('height', '100%');
    
    // Define arrow marker
    const defs = svg.append('defs');
    
    defs.append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 8)
      .attr('refY', 0)
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .attr('orient', 'auto')
      .attr('markerUnits', 'strokeWidth')
      .append('path')
      .attr('d', 'M 0,-5 L 10,0 L 0,5')
      .attr('fill', 'black')
      .attr('stroke', 'black');
    
    g = svg.append('g');
    
    // Add zoom behavior
    const zoom = d3.zoom()
      .scaleExtent([0.1, 3])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });
    
    svg.call(zoom);
  }

// Initialize the network immediately
console.log('Initializing network...');
initializeNetwork();
console.log('Network initialized, svg:', !!svg, 'g:', !!g);

// Helper functions (make globally available)
function getNodeType(types) {
    if (types.some(t => t.includes('Book'))) return 'Book';
    if (types.some(t => t.includes('Entity'))) return 'Entity';
    if (types.some(t => t.includes('Highlight'))) return 'Highlight';
    return 'Other';
  }
  
  function truncateLabel(label, maxLength = 40) {
    return label.length > maxLength ? label.substring(0, maxLength) + '…' : label;
  }
  
  // Clean up entity labels to show readable names instead of URLs
  function cleanEntityLabel(label, nodeType) {
    if (nodeType === 'Entity' && typeof label === 'string') {
      // Extract from URLs like "https://example.com/napoleon" -> "napoleon"
      if (label.includes('http')) {
        const parts = label.split('/');
        const lastPart = parts[parts.length - 1];
        if (lastPart && lastPart !== '') {
          return lastPart.charAt(0).toUpperCase() + lastPart.slice(1);
        }
      }
      // Extract from URIs like "kg:entity/napoleon" -> "napoleon"
      if (label.includes(':') || label.includes('/')) {
        const parts = label.split(/[:/]/);
        const lastPart = parts[parts.length - 1];
        if (lastPart && lastPart !== '') {
          return lastPart.charAt(0).toUpperCase() + lastPart.slice(1);
        }
      }
    }
    return label;
  }
  
  // Get node styling for D3
  function getNodeStyle(type) {
    switch (type) {
      case 'Book':
        return { fill: '#f8f9fa', stroke: '#000000', width: 160, height: 50 };
      case 'Entity':
        return { fill: '#ffffff', stroke: '#000000', width: 120, height: 40 };
      case 'Highlight':
        return { fill: '#e9ecef', stroke: '#000000', width: 200, height: 60 };
      default:
        return { fill: '#f1f3f4', stroke: '#000000', width: 140, height: 45 };
    }
  }
  
  
  
  // Create hierarchical static layout like Graphviz
  function createHierarchicalLayout(nodes, edges, path = []) {
    const positions = new Map();
    
    if (path.length > 0) {
      // For path visualization: smart 2D grid
      const nodesPerRow = Math.ceil(Math.sqrt(path.length));
      const spacing = 260;
      
      path.forEach((nodeId, index) => {
        const row = Math.floor(index / nodesPerRow);
        const col = index % nodesPerRow;
        positions.set(nodeId, { 
          x: col * spacing + 50, 
          y: row * spacing + 50 
        });
      });
    } else {
      // For general visualization: improved grouped layout
      const groups = {
        'Book': [],
        'Entity': [],
        'Highlight': [],
        'Other': []
      };
      
      nodes.forEach(node => {
        const nodeType = getNodeType(node.types || []);
        if (groups[nodeType]) {
          groups[nodeType].push(node);
        } else {
          groups['Other'].push(node);
        }
      });
      
      // Layout parameters - better spacing for arrow visibility
      const nodeSpacing = 100;
      const levelSpacing = 280;
      const nodesPerColumn = 6; // Wrap columns after 6 nodes
      
      let levelIndex = 0;
      
      // Position each group in tighter columns
      Object.entries(groups).forEach(([type, typeNodes]) => {
        if (typeNodes.length === 0) return;
        
        const columnsNeeded = Math.ceil(typeNodes.length / nodesPerColumn);
        
        for (let col = 0; col < columnsNeeded; col++) {
          const startIdx = col * nodesPerColumn;
          const endIdx = Math.min(startIdx + nodesPerColumn, typeNodes.length);
          const columnNodes = typeNodes.slice(startIdx, endIdx);
          
          const x = (levelIndex + col) * levelSpacing;
          
          columnNodes.forEach((node, index) => {
            positions.set(node.id, { 
              x, 
              y: index * nodeSpacing + 30
            });
          });
        }
        
        levelIndex += columnsNeeded;
      });
    }
    
    return positions;
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
      renderNetwork([], []);
      return;
    }
    
    pathInfo.textContent = `Found path with ${path.length} nodes`;
    
    // Create D3 nodes and edges
    const d3Nodes = [];
    const d3Edges = [];
    const nodeMap2 = new Map();
    
    // Create a better 2D layout for path visualization
    const nodesPerRow = Math.ceil(Math.sqrt(path.length));
    const horizontalSpacing = 280;
    const verticalSpacing = 150;
    
    path.forEach((nodeId, index) => {
      const node = nodeMap.get(nodeId);
      if (node) {
        const nodeType = getNodeType(node.types);
        const style = getNodeStyle(nodeType);
        const cleanLabel = cleanEntityLabel(node.label, nodeType);
        const truncatedLabel = truncateLabel(cleanLabel, 40);
        
        // Calculate 2D position
        const row = Math.floor(index / nodesPerRow);
        const col = index % nodesPerRow;
        
        // Center the layout
        const totalWidth = nodesPerRow * horizontalSpacing;
        const totalHeight = Math.ceil(path.length / nodesPerRow) * verticalSpacing;
        
        const d3Node = {
          id: nodeId,
          type: nodeType,
          cleanLabel: truncatedLabel,
          data: node,
          x: col * horizontalSpacing + 50,
          y: row * verticalSpacing + 50,
          width: style.width,
          height: style.height,
          style: style
        };
        
        d3Nodes.push(d3Node);
        nodeMap2.set(nodeId, d3Node);
      }
    });
    
    // Create edges between consecutive path nodes
    for (let i = 0; i < path.length - 1; i++) {
      const sourceNode = nodeMap2.get(path[i]);
      const targetNode = nodeMap2.get(path[i + 1]);
      if (sourceNode && targetNode) {
        d3Edges.push({
          source: sourceNode,
          target: targetNode
        });
      }
    }
    
    renderNetwork(d3Nodes, d3Edges);
    
    // Fit to view
    const bbox = g.node().getBBox();
    if (bbox.width > 0 && bbox.height > 0) {
      const svgRect = svg.node().getBoundingClientRect();
      const scale = Math.min(svgRect.width / (bbox.width + 100), svgRect.height / (bbox.height + 100), 1);
      const x = svgRect.width / 2 - (bbox.x + bbox.width / 2) * scale;
      const y = svgRect.height / 2 - (bbox.y + bbox.height / 2) * scale;
      
      svg.call(d3.zoom().transform, d3.zoomIdentity.translate(x, y).scale(scale));
    }
  }

// Render network with D3 (global function)
function renderNetwork(nodes, edges) {
  console.log('renderNetwork called with:', nodes.length, 'nodes,', edges.length, 'edges');
  console.log('g element:', g);

  if (!g) {
    console.error('g element is not available!');
    return;
  }

  g.selectAll('*').remove();

  // Draw edges first (so they appear behind nodes)
  const edgeSelection = g.selectAll('.edge')
    .data(edges)
    .enter()
    .append('g')
    .attr('class', 'edge');

  edgeSelection.append('line')
    .attr('class', 'edge-line')
    .attr('x1', d => d.source.x + d.source.width)
    .attr('y1', d => d.source.y + d.source.height/2)
    .attr('x2', d => d.target.x)
    .attr('y2', d => d.target.y + d.target.height/2)
    .attr('stroke', 'black')
    .attr('stroke-width', 1)
    .attr('marker-end', 'url(#arrowhead)');

  // Draw nodes
  const nodeSelection = g.selectAll('.node')
    .data(nodes)
    .enter()
    .append('g')
    .attr('class', 'node')
    .attr('transform', d => `translate(${d.x}, ${d.y})`)
    .style('cursor', 'pointer')
    .on('click', function(event, d) {
      console.log('Node clicked:', d);
      showNodeInfo(d.data);

      // Populate control panel inputs
      const pathFromInput = $('#path-from');
      const pathToInput = $('#path-to');
      const neighborhoodInput = $('#neighborhood-node');
      const pathInfo = $('#path-info');

      if (pathFromInput && !pathFromInput.value) {
        pathFromInput.value = d.data.label;
        pathFromInput.dataset.nodeId = d.data.id;
      } else if (pathToInput && !pathToInput.value) {
        pathToInput.value = d.data.label;
        pathToInput.dataset.nodeId = d.data.id;
      }

      if (neighborhoodInput) {
        neighborhoodInput.value = d.data.label;
        neighborhoodInput.dataset.nodeId = d.data.id;
      }

      if (pathInfo) {
        pathInfo.textContent = `Selected: ${d.data.label} (${d.type})`;
      }
    });

  // Add rectangles with sharp corners
  nodeSelection.append('rect')
    .attr('class', 'node-rect')
    .attr('width', d => d.width)
    .attr('height', d => d.height)
    .attr('fill', d => d.style.fill)
    .attr('stroke', d => d.style.stroke)
    .attr('rx', 0)  // Sharp corners
    .attr('ry', 0); // Sharp corners

  // Add horizontal divider line
  nodeSelection.append('line')
    .attr('class', 'divider-line')
    .attr('x1', 0)
    .attr('y1', d => d.height * 0.35)  // 35% down from top
    .attr('x2', d => d.width)
    .attr('y2', d => d.height * 0.35);

  // Add type labels (top section)
  nodeSelection.append('text')
    .attr('class', 'node-text node-text-title')
    .attr('x', d => d.width/2)
    .attr('y', d => d.height * 0.2)  // Centered in top section
    .text(d => d.type.toUpperCase());

  // Add main content (bottom section with word wrapping)
  nodeSelection.each(function(d) {
    const textElement = d3.select(this);
    const words = d.cleanLabel.split(' ');
    const lineHeight = 13;
    const startY = d.height * 0.5;  // Start in bottom section
    const maxWidth = d.width - 10;
    let y = startY;
    let line = [];

    for (let word of words) {
      line.push(word);
      const testLine = line.join(' ');

      // Better character width estimation for Arial
      if (testLine.length * 7 > maxWidth) {
        if (line.length > 1) {
          line.pop();
          textElement.append('text')
            .attr('class', 'node-text node-text-content')
            .attr('x', d.width/2)
            .attr('y', y)
            .text(line.join(' '));
          line = [word];
          y += lineHeight;

          // Prevent overflow below box
          if (y > d.height - 5) break;
        }
      }
    }

    if (line.length > 0 && y <= d.height - 5) {
      textElement.append('text')
        .attr('class', 'node-text node-text-content')
        .attr('x', d.width/2)
        .attr('y', y)
        .text(line.join(' '));
    }
  });
}

// Info panel functionality (global function)
function showNodeInfo(node) {
  const nodeType = getNodeType(node.types);

  // Update popup panel
  const infoTitle = $('#info-title');
  const infoContent = $('#info-content');
  const infoPanel = $('#info-panel');

  if (infoTitle) infoTitle.textContent = `${nodeType} Information`;

  let content = `
    <div class="field">
      <div class="field-label">Type</div>
      <div class="field-value">${nodeType}</div>
    </div>
    <div class="field">
      <div class="field-label">Full Label</div>
      <div class="field-value">${node.label}</div>
    </div>
    <div class="field">
      <div class="field-label">ID</div>
      <div class="field-value">${node.id}</div>
    </div>
  `;

  if (node.types && node.types.length > 0) {
    content += `
      <div class="field">
        <div class="field-label">Types</div>
        <div class="field-value">${node.types.join(', ')}</div>
      </div>
    `;
  }

  if (infoContent) infoContent.innerHTML = content;

  // Update control panel metadata section
  const nodeMetadata = $('#node-metadata');
  if (nodeMetadata) {
    nodeMetadata.innerHTML = content;
  }

  // Show popup (optional - could remove this if you prefer only control panel)
  // if (infoPanel) infoPanel.style.display = 'block';
}

function hideNodeInfo() {
  const infoPanel = $('#info-panel');
  infoPanel.style.display = 'none';
}

// Neighborhood exploration function (global)
function exploreNeighborhood(nodeId, depth) {
  console.log('exploreNeighborhood called with:', nodeId, 'depth:', depth);
  console.log('GRAPH_DATA available:', !!GRAPH_DATA);

  if (!GRAPH_DATA) {
    console.error('GRAPH_DATA not available for neighborhood exploration');
    const pathInfo = $('#path-info');
    if (pathInfo) pathInfo.textContent = 'Graph data not available';
    return;
  }

  const nodeMap = new Map();
  GRAPH_DATA.nodes.forEach(node => nodeMap.set(node.id, node));

  // Build adjacency list
  const graph = new Map();
  GRAPH_DATA.nodes.forEach(node => graph.set(node.id, new Set()));
  GRAPH_DATA.edges.forEach(edge => {
    if (graph.has(edge.from) && graph.has(edge.to)) {
      graph.get(edge.from).add(edge.to);
      graph.get(edge.to).add(edge.from);
    }
  });

  // BFS to find neighborhood
  const visited = new Set([nodeId]);
  const queue = [[nodeId, 0]];
  const neighborhoodNodes = new Set([nodeId]);

  while (queue.length > 0) {
    const [currentId, currentDepth] = queue.shift();

    if (currentDepth < depth) {
      for (const neighborId of graph.get(currentId) || []) {
        if (!visited.has(neighborId)) {
          visited.add(neighborId);
          neighborhoodNodes.add(neighborId);
          queue.push([neighborId, currentDepth + 1]);
        }
      }
    }
  }

  // Create visualization
  const d3Nodes = [];
  const d3Edges = [];
  const positions = createHierarchicalLayout(Array.from(neighborhoodNodes), GRAPH_DATA.edges);

  Array.from(neighborhoodNodes).forEach(id => {
    const node = nodeMap.get(id);
    if (node) {
      const nodeType = getNodeType(node.types);
      const style = getNodeStyle(nodeType);
      const cleanLabel = cleanEntityLabel(node.label, nodeType);
      const pos = positions.get(id) || { x: 0, y: 0 };

      d3Nodes.push({
        id: id,
        type: nodeType,
        cleanLabel: truncateLabel(cleanLabel, 30),
        data: node,
        x: pos.x,
        y: pos.y,
        width: style.width,
        height: style.height,
        style: style
      });
    }
  });

  // Add edges between neighborhood nodes
  GRAPH_DATA.edges.forEach(edge => {
    if (neighborhoodNodes.has(edge.from) && neighborhoodNodes.has(edge.to)) {
      const sourceNode = d3Nodes.find(n => n.id === edge.from);
      const targetNode = d3Nodes.find(n => n.id === edge.to);
      if (sourceNode && targetNode) {
        d3Edges.push({ source: sourceNode, target: targetNode });
      }
    }
  });

  renderNetwork(d3Nodes, d3Edges);
  const pathInfo = $('#path-info');
  if (pathInfo) pathInfo.textContent = `Showing ${neighborhoodNodes.size} nodes in ${depth}-hop neighborhood`;
}

// Search nodes for autocomplete (global)
function searchNodes(query) {
  if (!query || query.length < 2) return [];
  if (!GRAPH_DATA) return [];

  const q = query.toLowerCase();
  return GRAPH_DATA.nodes
    .filter(node => node.label.toLowerCase().includes(q))
    .slice(0, 10);
}

// Show autocomplete suggestions (global)
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

// Initialize concepts list and event handlers AFTER network is ready
searchInput.addEventListener('input', e => renderConcepts(e.target.value));
renderConcepts('');
if (DATA.length) selectConcept(DATA[0]);

if (GRAPH_DATA) {
  const pathFromInput = $('#path-from');
  const pathToInput = $('#path-to');
  const findPathBtn = $('#find-path');
  const pathInfo = $('#path-info');

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

  // Neighborhood exploration
  const neighborhoodInput = $('#neighborhood-node');
  const neighborhoodSuggestions = $('#neighborhood-suggestions');
  const neighborhoodDepth = $('#neighborhood-depth');
  const exploreBtn = $('#explore-neighborhood');

  neighborhoodInput.addEventListener('input', () => {
    showSuggestions(neighborhoodInput, neighborhoodSuggestions);
  });

  exploreBtn.addEventListener('click', () => {
    const nodeId = neighborhoodInput.dataset.nodeId;
    const depth = parseInt(neighborhoodDepth.value) || 1;
    if (nodeId) {
      exploreNeighborhood(nodeId, depth);
    }
  });

  // Graph properties
  $('#show-clusters').addEventListener('click', showClusters);
  $('#show-centrality').addEventListener('click', showCentrality);


  // Graph clustering (simplified)
  function showClusters() {
    $('#graph-stats').textContent = 'Clustering analysis not yet implemented';
  }

  // Centrality analysis (simplified)
  function showCentrality() {
    if (!GRAPH_DATA) return;

    // Simple degree centrality
    const degreeMap = new Map();
    GRAPH_DATA.nodes.forEach(node => degreeMap.set(node.id, 0));

    GRAPH_DATA.edges.forEach(edge => {
      if (degreeMap.has(edge.from)) degreeMap.set(edge.from, degreeMap.get(edge.from) + 1);
      if (degreeMap.has(edge.to)) degreeMap.set(edge.to, degreeMap.get(edge.to) + 1);
    });

    const sorted = Array.from(degreeMap.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5);

    const stats = sorted.map(([id, degree]) => {
      const node = GRAPH_DATA.nodes.find(n => n.id === id);
      const label = node ? node.label.substring(0, 30) : id;
      return `${label}: ${degree} connections`;
    }).join('<br>');

    $('#graph-stats').innerHTML = `<strong>Top 5 by degree:</strong><br>${stats}`;
  }

  // Info panel event listeners
  const infoPanel = $('#info-panel');
  const closeBtn = infoPanel.querySelector('.close-btn');

  closeBtn.addEventListener('click', hideNodeInfo);

  // Close panel when clicking outside
  document.addEventListener('click', function(e) {
    if (infoPanel.style.display === 'block' && !infoPanel.contains(e.target) && !e.target.closest('#network')) {
      hideNodeInfo();
    }
  });
  
  // Click handlers are now handled in renderNetwork function
  
} else {
  // No graph data available
  const controlCol = $('.control-col');
  if (controlCol) {
    controlCol.innerHTML = '<h2>Graph Controls</h2><div class="muted">Graph data not available</div>';
  }
}

}); // End DOMContentLoaded
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

