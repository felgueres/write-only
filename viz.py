# viz_static.py
# pip install rdflib networkx matplotlib
import matplotlib.pyplot as plt
import networkx as nx
from rdflib import Namespace
from nx_loader import load_rdf, build_nx, node_by_curie  # reuse your loader

KG = Namespace("https://your.name/kg/")

def k_hop_subgraph(G, center, k=2):
    seen = {center}
    frontier = {center}
    for _ in range(k):
        new = set()
        for u in frontier:
            new.update(G.predecessors(u) if G.is_directed() else G.neighbors(u))
            new.update(G.successors(u) if G.is_directed() else [])
        frontier = new - seen
        seen |= new
    return G.subgraph(seen).copy()

def color_by_type(G, n):
    types = G.nodes[n].get("types", set())
    if any(t.endswith("/Book") for t in types): return "tab:blue"
    if any(t.endswith("/Highlight") for t in types): return "tab:orange"
    if any(t.endswith("/Entity") for t in types): return "tab:green"
    return "tab:gray"

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "all_books.jsonld"
    rdf = load_rdf(path)
    G = build_nx(rdf, directed=True)
    pos = nx.spring_layout(G, seed=42)

    node_colors = [color_by_type(G, n) for n in G.nodes()]
    labels = {n: G.nodes[n].get("label", str(n)).split("\n")[0][:40] for n in G.nodes()}

    plt.figure(figsize=(10, 8))
    nx.draw_networkx(G, pos, with_labels=False, node_color=node_colors, node_size=300, arrows=True)
    nx.draw_networkx_labels(G, pos, labels, font_size=8)
    plt.axis("off")
    plt.tight_layout()
    plt.show()

