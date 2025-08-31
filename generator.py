import json, re

CONTEXT_PATH = "./context.jsonld"
BASE = "kg:"
HIGHLIGHT_ID_PREFIX = "h-"

def book_iri(book_id):             return f"{BASE}book/{book_id}"
def highlight_iri(book_id, hid):   return f"{BASE}highlight/{book_id}#{HIGHLIGHT_ID_PREFIX}{hid}"

def to_jsonld_graph(books, ctx_obj):
    graph = []
    seen = set()

    for b in books:
        bid = b["id"]
        bnode = {"id": book_iri(bid), "type": "Book", "name": b["title"]}
        if b.get("cover_url"): bnode["image"] = b["cover_url"]
        key = ("Book", bnode["id"])
        if key not in seen: graph.append(bnode); seen.add(key)

        for h in b.get("highlights", [])[:5]:
            hid = h["id"]
            hnode = {
                "id": highlight_iri(bid, hid),
                "type": "Highlight",
                "inBook": book_iri(bid),
                "highlightText": h["text"],
            }
            graph.append(hnode)

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

    with open("read_graph.jsonld", "w", encoding="utf-8") as wf:
        json.dump(out, wf, ensure_ascii=False, indent=2)

    print(f"wrote all_books.jsonld with {len(out['@graph'])} nodes from {len(books)} books")

