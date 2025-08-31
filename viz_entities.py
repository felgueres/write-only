import matplotlib.pyplot as plt
import networkx as nx
from rdflib import Namespace
from nx_loader import load_rdf
from rdflib.namespace import RDF
import math
KG = Namespace("https://your.name/kg/")
SCHEMA = Namespace("http://schema.org/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

def build_be(rdf):
    G = nx.DiGraph()
    for h,b in rdf.subject_objects(KG.inBook):
        for e in rdf.objects(h, KG.mentionsEntity):
            bname = rdf.value(b, SCHEMA.name) or str(b)
            ename = rdf.value(e, SKOS.prefLabel) or rdf.value(e, SCHEMA.name) or str(e)
            G.add_node(b, kind="Book", label=str(bname))
            G.add_node(e, kind="Entity", label=str(ename))
            G.add_edge(b, e, weight=G[b][e]["weight"]+1 if G.has_edge(b,e) else 1)
    return G

def prune(G, min_w=6, top_entities=1, top_per_book=1):
    # drop weak edges
    G.remove_edges_from([(u,v) for u,v,d in G.edges(data=True) if d["weight"]<min_w])
    G.remove_nodes_from([n for n in list(G.nodes) if G.degree(n)==0])
    # keep only top entities globally
    ents = [n for n,d in G.nodes(data=True) if d.get("kind")=="Entity"]
    keep_ents = set(n for n,_ in sorted(
        ((e,G.in_degree(e,weight="weight")) for e in ents),
        key=lambda x:x[1], reverse=True)[:top_entities])
    # also keep each book’s top-k entities
    for b in [n for n,d in G.nodes(data=True) if d.get("kind")=="Book"]:
        nbrs = sorted(((e,G[b][e]["weight"]) for e in G.successors(b)), key=lambda x:x[1], reverse=True)[:top_per_book]
        keep_ents.update(e for e,_ in nbrs)
    keep = [n for n in G.nodes if G.nodes[n].get("kind")=="Book" or n in keep_ents]
    return G.subgraph(keep).copy()

def draw(G):
    books  = [n for n,d in G.nodes(data=True) if d.get("kind")=="Book"]
    ents   = [n for n,d in G.nodes(data=True) if d.get("kind")=="Entity"]
    pos = {}
    # two columns layout
    for i,b in enumerate(sorted(books, key=lambda n: G.out_degree(n), reverse=True)):
        pos[b] = (0, i)
    for i,e in enumerate(sorted(ents, key=lambda n: G.in_degree(n,weight="weight"), reverse=True)):
        pos[e] = (1, i)
    widths = [1 + math.log(d["weight"]) for _,_,d in G.edges(data=True)]
    plt.figure(figsize=(14,10))
    nx.draw_networkx_nodes(G, pos, nodelist=books, node_color="tab:blue", node_size=220)
    nx.draw_networkx_nodes(G, pos, nodelist=ents,  node_color="tab:green", node_size=140)
    nx.draw_networkx_edges(G, pos, width=widths, alpha=0.35, arrows=False)
    nx.draw_networkx_labels(G, pos, {n:G.nodes[n]["label"][:40] for n in books}, font_size=8)
    # label only high-degree entities
    hi = [e for e in ents if G.in_degree(e, weight="weight")>=5]
    nx.draw_networkx_labels(G, pos, {n:G.nodes[n]["label"][:30] for n in hi}, font_size=7)
    plt.axis("off"); plt.tight_layout(); plt.show()

if __name__ == "__main__":
    import sys
    rdf = load_rdf(sys.argv[1] if len(sys.argv)>1 else "all_books.jsonld")
    G = build_be(rdf)
    Gp = prune(G, min_w=6, top_entities=20, top_per_book=2)  # tweak knobs
    draw(Gp)
