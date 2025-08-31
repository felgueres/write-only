from rdflib import Graph as RDFGraph, Namespace, RDF, URIRef, Literal
import networkx as nx

KG = Namespace("https://your.name/kg/")
SCHEMA = Namespace("http://schema.org/")

def load_rdf(jsonld_path: str) -> RDFGraph:
    g = RDFGraph()
    g.parse(jsonld_path, format="json-ld")
    return g

def build_nx(g_rdf: RDFGraph, directed=True) -> nx.MultiDiGraph:
    G = nx.MultiDiGraph() if directed else nx.MultiGraph()

    # node typing + labels (optional metadata)
    for s, _, otype in g_rdf.triples((None, RDF.type, None)):
        G.add_node(s)
        G.nodes[s].setdefault("types", set()).add(str(otype))

    # attach human labels if present
    for s, _, name in g_rdf.triples((None, SCHEMA.name, None)):
        G.add_node(s)
        G.nodes[s]["label"] = str(name)

    # highlights don't have schema:name, keep snippet as label fallback
    for s, _, txt in g_rdf.triples((None, KG.highlightText, None)):
        G.add_node(s)
        G.nodes[s].setdefault("label", str(txt)[:120] + ("…" if len(str(txt)) > 120 else ""))

    # choose which predicates become edges
    edge_preds = [
        KG.inBook,          # Highlight -> Book
        # KG.hasAnnotation,   # Highlight -> Annotation
        # add more when you model them:
        # KG.refersToConcept, KG.taggedWith, KG.inSection, KG.hasAuthor, ...
    ]

    for p in edge_preds:
        for s, _, o in g_rdf.triples((None, p, None)):
            G.add_node(s); G.add_node(o)
            G.add_edge(s, o, predicate=str(p))
    return G

# --- 3) Helpers / Queries ---
def node_by_curie(curie: str) -> URIRef:
    """Accepts 'kg:book/...' style ids from your JSON-LD and returns full URI."""
    if curie.startswith("kg:"):
        return URIRef(str(KG) + curie[3:])  # strip 'kg:' and append
    return URIRef(curie)

def shortest_path(G: nx.Graph, a: str, b: str):
    sa, sb = node_by_curie(a), node_by_curie(b)
    path = nx.shortest_path(G, sa, sb)
    return [(n, G.nodes[n].get("label") or n) for n in path]

def neighbors(G: nx.Graph, curie: str):
    n = node_by_curie(curie)
    out = []
    for tgt in G.successors(n) if G.is_directed() else G.neighbors(n):
        for k, data in G.get_edge_data(n, tgt).items():
            out.append((tgt, data.get("predicate")))
    return out

def highlights_in_book(G: nx.Graph, book_curie: str):
    """Return highlight nodes pointing to a given Book via inBook."""
    book = node_by_curie(book_curie)
    res = []
    for h in G.predecessors(book) if G.is_directed() else G.neighbors(book):
        # keep only Highlight-typed nodes
        if any(t.endswith("/Highlight") for t in G.nodes[h].get("types", [])):
            res.append((h, G.nodes[h].get("label")))
    return res

# --- 4) CLI demo ---
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python nx_loader.py all_books.jsonld")
        sys.exit(1)

    rdf = load_rdf(sys.argv[1])
    G = build_nx(rdf, directed=True)

    # examples (adjust IDs to your data)
    book_id = "kg:book/63e3cd42b05c"
    print("\nHighlights in book:")
    for n, label in highlights_in_book(G, book_id)[:10]:
        print(" -", G.nodes[n].get("label"))

    # path between two nodes (e.g., a highlight and its book)
    a = "kg:highlight/63e3cd42b05c#h-2ba1a25b"
    b = "kg:book/63e3cd42b05c"
    print("\nShortest path:")
    for n, label in shortest_path(G, a, b):
        print(" ->", label)

    # raw neighbors
    print("\nNeighbors of book (edges + predicates):")
    for tgt, pred in neighbors(G, book_id)[:10]:
        print(" -", G.nodes[tgt].get("label"), "|", pred)

