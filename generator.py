import json, re
from ai_utils import extract_concepts
from entities import extract_entities

CONTEXT_PATH = "./context.jsonld"
BASE = "kg:"
HIGHLIGHT_ID_PREFIX = "h-"

def book_iri(book_id):             return f"{BASE}book/{book_id}"
def highlight_iri(book_id, hid):   return f"{BASE}highlight/{book_id}#{HIGHLIGHT_ID_PREFIX}{hid}"

def to_jsonld_graph(books, ctx_obj):
    graph,seen = [], set()

    def add_entity(eid, label):
        key = ("Entity", eid)
        if key in seen: return
        graph.append({"id": eid, "type": "Entity", "prefLabel": label})
        seen.add(key)

    def add_concept(cid, label):
        key = ("Concept", cid)
        if key in seen: return
        graph.append({"id": cid, "type": "Concept", "prefLabel": label})
        seen.add(key)

    for b in books:
        bid = b["id"]
        bnode = {"id": book_iri(bid), "type": "Book", "name": b["title"]}
        if b.get("cover_url"): bnode["image"] = b["cover_url"]
        key = ("Book", bnode["id"])
        if key not in seen: graph.append(bnode); seen.add(key)

        for h in b.get("highlights", []):
            hid = h["id"]
            hnode = {
                "id": highlight_iri(bid, hid),
                "type": "Highlight",
                "inBook": book_iri(bid),
                "highlightText": h["text"],
            }
            graph.append(hnode)
            
            ents = extract_entities(h["text"])
            if ents:
                hnode["mentionsEntity"] = [eid for eid, _ in ents]
                for eid, label in ents:
                    add_entity(eid, label)

            concepts = extract_concepts(h["text"])
            if concepts:
                hnode["refersToConcept"] = [cid for cid,_ in concepts]
                for cid, label in concepts:
                    add_concept(cid,label)

    return {"@context": ctx_obj, "@graph": graph}

if __name__ == "__main__":
    with open(CONTEXT_PATH, "r", encoding="utf-8") as c:
        context_obj = json.load(c)

    books = []
    with open("./kindle_highlights_04062025.jsonl", "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line: books.append(json.loads(line))

    out = to_jsonld_graph(books, context_obj)

    with open("read_graph_09012025.jsonld", "w", encoding="utf-8") as wf:
        json.dump(out, wf, ensure_ascii=False, indent=2)

    print(f"wrote all_books.jsonld with {len(out['@graph'])} nodes from {len(books)} books")

