import re, spacy
nlp = spacy.load("en_core_web_sm")

WHITELIST = {"PERSON","ORG","GPE","LOC","PRODUCT","WORK_OF_ART","EVENT"}
def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9\-]+","-", s.lower()).strip("-")

def extract_entities(text: str):
    """Return list of (id, label) for whitelisted entities in text."""
    ents = []
    doc = nlp(text)
    seen = set()
    for ent in doc.ents:
        if ent.label_ in WHITELIST:
            lab = ent.text.strip()
            sid = f"kg:entity/{slug(lab)}"
            if sid not in seen:
                ents.append((sid, lab))
                seen.add(sid)
    return ents
