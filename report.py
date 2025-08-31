# report_top_entities.py
# pip install rdflib networkx matplotlib
import argparse, matplotlib.pyplot as plt
from rdflib import Namespace
from rdflib.namespace import RDF
from nx_loader import load_rdf  # reuse your loader
from rdflib import URIRef

KG = Namespace("https://your.name/kg/")
SCHEMA = Namespace("http://schema.org/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

def resolve_entity(user_input, entity_label):
    """Return a URIRef for the entity. Accepts CURIE, full IRI, or a (partial) label/slug."""
    s = user_input.strip()

    # CURIE
    if s.startswith("kg:"):
        return URIRef(str(KG) + s[3:])

    # Full IRI
    if s.startswith("http://") or s.startswith("https://"):
        return URIRef(s)

    # Try exact label match (case-insensitive)
    for e, lbl in entity_label.items():
        if str(lbl).lower() == s.lower():
            return e

    # Try suffix match on IRI (slug) or substring of label
    s_low = s.lower()
    cand = []
    for e, lbl in entity_label.items():
        iri_low = str(e).lower()
        if iri_low.endswith("/" + s_low) or s_low in str(lbl).lower():
            cand.append(e)
    if len(cand) == 1:
        return cand[0]
    if len(cand) > 1:
        # pick the one with the longest common suffix match
        cand.sort(key=lambda e: len(str(e)), reverse=True)
        return cand[0]

    return None

def build_counts(rdf):
    """Return:
       be[(book, entity)] -> count
       book_label[book], entity_label[entity]
    """
    be = {}
    book_label, entity_label = {}, {}

    for h, b in rdf.subject_objects(KG.inBook):
        book_label.setdefault(b, str(rdf.value(b, SCHEMA.name) or b))
        for e in rdf.objects(h, KG.mentionsEntity):
            entity_label.setdefault(e, str(rdf.value(e, SKOS.prefLabel) or rdf.value(e, SCHEMA.name) or e))
            be[(b, e)] = be.get((b, e), 0) + 1

    return be, book_label, entity_label

def top_entities_global(be, k=15):
    # sum over books
    totals = {}
    for (b, e), c in be.items():
        totals[e] = totals.get(e, 0) + c
    return sorted(totals.items(), key=lambda x: x[1], reverse=True)[:k]

def books_for_entity(be, e):
    rows = [(b, c) for (b, e2), c in be.items() if e2 == e]
    return sorted(rows, key=lambda x: x[1], reverse=True)

def plot_entity(be, book_label, entity_label, user_input):
    e_key = resolve_entity(user_input, entity_label)
    if not e_key:
        print("Could not resolve entity:", user_input)
        # show some suggestions
        sugg = [lbl for _, lbl in list(entity_label.items())[:20]]
        print("Example entities:", ", ".join(map(str, sugg[:10])))
        return

    rows = books_for_entity(be, e_key)
    if not rows:
        print("No mentions for", user_input)
        return

    labs = [book_label[b] for b, _ in rows][:20][::-1]
    vals = [c for _, c in rows][:20][::-1]

    import matplotlib.pyplot as plt
    plt.figure(figsize=(10, 6))
    plt.barh(labs, vals)
    plt.xlabel("Mentions (highlights)")
    plt.title(f"Books mentioning {entity_label.get(e_key, str(e_key))}")
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="all_books.jsonld")
    ap.add_argument("--top", type=int, default=15, help="how many entities to list")
    ap.add_argument("--plot", type=str, help="plot [48;38;133;646;931ta single entity (CURIE like kg:entity/murray-rothbard)")
    args = ap.parse_args()

    rdf = load_rdf(args.path)
    be, book_label, entity_label = build_counts(rdf)

    # list top entities and their books
    print(f"Top entities (global, top {args.top}):")
    for e, total in top_entities_global(be, k=args.top):
        print(f"\n{total:>4}  {entity_label[e]}")
        for b, c in books_for_entity(be, e)[:8]:
            print(f"      - {c:>3} × {book_label[b]}")

    if args.plot:
        plot_entity(be, book_label, entity_label, args.plot)

