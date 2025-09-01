import openai, os, re
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def extract_concepts(highlight_text: str)-> list[tuple[str,str]]:
    """
    Extract 1–2 key concepts from a highlight using GPT.
    Returns list of (concept_id, label).
    """
    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract 1-2 main abstract concepts or topics from this highlight. \
Return them as Wikipedia article title only. If unsure, return the closest broad category e.g. 'Economics', 'Philosophy'.\
Comma separated list and no explanations."},
                {"role": "user", "content": highlight_text}
            ],
            temperature=0.3,
            max_tokens=50
        )
        raw = resp.choices[0].message.content
        topics = [t.strip() for t in raw.split(",") if t.strip()]
        
        out = []
        for t in topics:
            cid = f"kg:concept/{slugify(t)}"
            out.append((cid, t))
        return out
    except Exception as e:
        print(f"Error extracting concepts: {e}")
        return []

if __name__ == "__main__":
    test = extract_concepts('The American revolutionaries were steeped in the creed of libertarianism.')
    print(test)
