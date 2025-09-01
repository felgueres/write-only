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

def resolve_book(user_input, book_label):
    s = user_input.strip()
    if s.startswith("kg:"): return URIRef(str(KG) + s[3:])
    if s.startswith("http://") or s.startswith("https://"): return URIRef(s)

    # exact label
    for b, lbl in book_label.items():
        if str(lbl).lower() == s.lower(): return b

    # suffix on IRI or substring in title
    s_low = s.lower()
    cand = []
    for b, lbl in book_label.items():
        if str(b).lower().endswith("/" + s_low) or s_low in str(lbl).lower():
            cand.append(b)
    if not cand: return None
    if len(cand) == 1: return cand[0]
    cand.sort(key=lambda b: len(str(b)), reverse=True)
    return cand[0]

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
    totals = {}
    for (_, e), c in be.items():
        totals[e] = totals.get(e, 0) + c
    return sorted(totals.items(), key=lambda x: x[1], reverse=True)[:k]

def books_for_entity(be, e):
    rows = [(b, c) for (b, e2), c in be.items() if e2 == e]
    return sorted(rows, key=lambda x: x[1], reverse=True)

def top_entities_for_book(be, b, k=20):
    rows = [(e, c) for (b2, e), c in be.items() if b2 == b]
    return sorted(rows, key=lambda x: x[1], reverse=True)[:k]

def plot_barh(labels, values, title):
    import matplotlib.pyplot as plt
    plt.figure(figsize=(10, max(4, 0.4*len(labels))))
    plt.barh(labels[::-1], values[::-1])
    plt.title(title)
    plt.xlabel("Mentions (highlights)")
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="all_books.jsonld")
    ap.add_argument("--top", type=int, help="top N entities (global)")
    ap.add_argument("--list-books", action="store_true", help="list all books")
    ap.add_argument("--top-in-book", type=str, help="book id/label/slug to list top entities for")
    ap.add_argument("--books-for-entity", type=str, help="entity id/label/slug to list books mentioning it")
    ap.add_argument("--plot-entity", type=str, help="plot a single entity across books")
    ap.add_argument("--plot-book", type=str, help="plot top entities for a single book")
    args = ap.parse_args()
    rdf = load_rdf(args.path)
    be, book_label, entity_label = build_counts(rdf)

    # 0) list books
    if args.list_books:
        print("Books:")
        for b, lbl in sorted(book_label.items(), key=lambda x: x[1].lower()):
            print(f"- {lbl} id:{b}")

    # 1) global top entities
    if args.top:
        print(f"\nTop entities (global, top {args.top}):")
        for e, tot in top_entities_global(be, k=args.top):
            print(f"{tot:>4}  {entity_label[e]}")

    # 2) top entities in a given book
    if args.top_in_book:
        b = resolve_book(args.top_in_book, book_label)
        if not b:
            print("\n[!] Could not resolve book:", args.top_in_book)
        else:
            print(f"\nTop entities in book: {book_label[b]}")
            rows = top_entities_for_book(be, b, k=25)
            for e, c in rows:
                print(f"{c:>4}  {entity_label[e]}")

    # 3) books for a given entity
    if args.books_for_entity:
        e = resolve_entity(args.books_for_entity, entity_label)
        if not e:
            print("\n[!] Could not resolve entity:", args.books_for_entity)
        else:
            print(f"\nBooks mentioning {entity_label[e]}:")
            rows = books_for_entity(be, e)
            for b, c in rows:
                print(f"{c:>4}  {book_label[b]}")

    # 4) plots
    if args.plot_entity:
        e = resolve_entity(args.plot_entity, entity_label)
        if not e:
            print("\n[!] Could not resolve entity for plot:", args.plot_entity)
        else:
            rows = books_for_entity(be, e)[:20]
            if not rows:
                print("\nNo mentions for", args.plot_entity)
            else:
                labs = [book_label[b] for b, _ in rows]
                vals = [c for _, c in rows]
                plot_barh(labs, vals, f"Books mentioning {entity_label[e]}")

    if args.plot_book:
        b = resolve_book(args.plot_book, book_label)
        if not b:
            print("\n[!] Could not resolve book for plot:", args.plot_book)
        else:
            rows = top_entities_for_book(be, b, k=20)
            if not rows:
                print("\nNo entities for", args.plot_book)
            else:
                labs = [entity_label[e] for e, _ in rows]
                vals = [c for _, c in rows]
                plot_barh(labs, vals, f"Top entities in {book_label[b]}")
