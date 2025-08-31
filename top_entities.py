# top_entities.py
# reuse your loader
from nx_loader import load_rdf, build_nx
import networkx as nx

def is_entity(G, n):
    return any(t.endswith("/Entity") for t in G.nodes[n].get("types", []))

def label(G, n):
    # prefLabel or schema:name or fallback
    return G.nodes[n].get("prefLabel") or G.nodes[n].get("label") or str(n)

def top_entities(G, k=20):
    ents = [n for n in G.nodes if is_entity(G, n)]
    counts = sorted(((n, G.in_degree(n)) for n in ents), key=lambda x: x[1], reverse=True)
    return [(label(G, n), c, n) for n, c in counts[:k]]

def top_entities_for_book(G, book_curie, k=20):
    # count entities only from highlights that belong to this book
    from nx_loader import node_by_curie
    b = node_by_curie(book_curie)
    hs = [h for h in G.predecessors(b) if any(t.endswith("/Highlight") for t in G.nodes[h].get("types", []))]
    counts = {}
    for h in hs:
        for _, e, data in G.out_edges(h, data=True):
            if data.get("predicate", "").endswith("/mentionsEntity") and is_entity(G, e):
                counts[e] = counts.get(e, 0) + 1
    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:k]
    return [(label(G, e), c, e) for e, c in top]

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "all_books.jsonld"
    rdf = load_rdf(path)
    G = build_nx(rdf, directed=True)

    print("Top entities (global):")
    for name, c, _ in top_entities(G, k=15):
        print(f"{c:>4}  {name}")

    print("\nTop entities in one book:")
    book = "kg:book/63e3cd42b05c"
    for name, c, _ in top_entities_for_book(G, book, k=10):
        print(f"{c:>4}  {name}")

