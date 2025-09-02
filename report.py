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

def resolve_concept(user_input, concept_label):
    s = user_input.strip()
    if s.startswith("kg:"): return URIRef(str(KG) + s[3:])
    if s.startswith("http://") or s.startswith("https://"): return URIRef(s)
    for c, lbl in concept_label.items():
        if str(lbl).lower() == s.lower(): return c
    s_low = s.lower()
    cand = []
    for c, lbl in concept_label.items():
        if str(c).lower().endswith("/" + s_low) or s_low in str(lbl).lower():
            cand.append(c)
    if not cand: return None
    if len(cand) == 1: return cand[0]
    cand.sort(key=lambda c: len(str(c)), reverse=True)
    return cand[0]

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

def build_counts_concepts(rdf):
    """Return:
       bc[(book, concept)] -> count
       book_label[book], concept_label[concept]
    """
    bc = {}
    book_label, concept_label = {}, {}
    for h, b in rdf.subject_objects(KG.inBook):
        book_label.setdefault(b, str(rdf.value(b, SCHEMA.name) or b))
        for c in rdf.objects(h, KG.refersToConcept):
            # label from skos:prefLabel or schema:name
            concept_label.setdefault(c, str(rdf.value(c, SKOS.prefLabel) or rdf.value(c, SCHEMA.name) or c))
            bc[(b, c)] = bc.get((b, c), 0) + 1
    return bc, book_label, concept_label

def top_concepts_global(bc, k=15):
    totals = {}
    for (_, c), cnt in bc.items():
        totals[c] = totals.get(c, 0) + cnt
    return sorted(totals.items(), key=lambda x: x[1], reverse=True)[:k]

def books_for_concept(bc, c):
    rows = [(b, cnt) for (b, c2), cnt in bc.items() if c2 == c]
    return sorted(rows, key=lambda x: x[1], reverse=True)

def top_concepts_for_book(bc, b, k=20):
    rows = [(c, cnt) for (b2, c), cnt in bc.items() if b2 == b]
    return sorted(rows, key=lambda x: x[1], reverse=True)[:k]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="all_books.jsonld")
    ap.add_argument("--top-entities", type=int, help="top N entities (global)")
    ap.add_argument("--list-books", action="store_true", help="list all books")
    ap.add_argument("--top-in-book", type=str, help="book id/label/slug to list top entities for")
    ap.add_argument("--books-for-entity", type=str, help="entity id/label/slug to list books mentioning it")
    ap.add_argument("--plot-entity", type=str, help="plot a single entity across books")
    ap.add_argument("--plot-book", type=str, help="plot top entities for a single book")
    ap.add_argument("--top-concepts", type=int, help="top N concepts (global)")
    ap.add_argument("--concepts-in-book", type=str, help="book id/label/slug to list top concepts for")
    ap.add_argument("--books-for-concept", type=str, help="concept id/label/slug to list books mentioning it")
    ap.add_argument("--plot-concept", type=str, help="plot a single concept across books")
    args = ap.parse_args()
    rdf = load_rdf(args.path)
    be, book_label_e, entity_label = build_counts(rdf)
    bc, book_label_c, concept_label = build_counts_concepts(rdf)
    book_label = {**book_label_e, **book_label_c}

    # 0) list books
    if args.list_books:
        print("Books:")
        for b, lbl in sorted(book_label.items(), key=lambda x: x[1].lower()):
            print(f"- {lbl} id:{b}")

    # 1) global top entities
    if args.top_entities:
        print(f"\nTop entities (global, top {args.top_entities}):")
        for e, tot in top_entities_global(be, k=args.top_entities):
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

    # 5) global top concepts
    if args.top_concepts:
        print(f"\nTop concepts (global, top {args.top_concepts}):")
        for c, tot in top_concepts_global(bc, k=args.top_concepts):
            print(f"{tot:>4}  {concept_label[c]}")

    # 6) top concepts in a given book
    if args.concepts_in_book:
        b = resolve_book(args.concepts_in_book, book_label)
        if not b:
            print("\n[!] Could not resolve book:", args.concepts_in_book)
        else:
            print(f"\nTop concepts in book: {book_label[b]}")
            rows = top_concepts_for_book(bc, b, k=25)
            for c, cnt in rows:
                print(f"{cnt:>4}  {concept_label[c]}")

    # 7) books for a given concept
    if args.books_for_concept:
        c = resolve_concept(args.books_for_concept, concept_label)
        if not c:
            print("\n[!] Could not resolve concept:", args.books_for_concept)
        else:
            print(f"\nBooks mentioning concept {concept_label[c]}:")
            rows = books_for_concept(bc, c)
            for b, cnt in rows:
                print(f"{cnt:>4}  {book_label[b]}")

    # 8) plot concept across books
    if args.plot_concept:
        c = resolve_concept(args.plot_concept, concept_label)
        if not c:
            print("\n[!] Could not resolve concept for plot:", args.plot_concept)
        else:
            rows = books_for_concept(bc, c)[:20]
            if not rows:
                print("\nNo mentions for", args.plot_concept)
            else:
                labs = [book_label[b] for b, _ in rows]
                vals = [cnt for _, cnt in rows]
                plot_barh(labs, vals, f"Books mentioning concept {concept_label[c]}")
