import uvicorn
from fastapi import FastAPI, Query
from typing import List, Dict, Any, Optional
import asyncio
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI(
    title="Reading Notes API",
    description="Simple async API for searching reading notes",
    version="1.0.0"
)

# Add CORS middleware to allow requests from the React app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def load_kindle_highlights(file_path="kindle_highlights_02032025.jsonl"):
    await asyncio.sleep(0.1)
    highlights = []
    id_counter = 1
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                try:
                    book_data = json.loads(line.strip())
                    title = book_data.get("title", "Unknown Book")
                    
                    for highlight in book_data.get("highlights", []):
                        highlights.append({
                            "id": id_counter,
                            "title": title,
                            "content": highlight.get("text", ""),
                            "location": highlight.get("note", "") or "No location"
                        })
                        id_counter += 1
                except json.JSONDecodeError:
                    # Skip malformed lines
                    continue
    except Exception as e:
        print(f"Error loading highlights: {e}")
    
    return highlights

@app.get("/search", response_model=List[Dict[str, Any]])
async def search_notes(
    query: Optional[str] = Query(None, description="Search term"),
    title: Optional[str] = Query(None, description="Filter by book title")
):
    """
    Search the reading notes with optional filters:
    - Free text search across title and content
    - Title filter for specific books
    """
    notes = await load_kindle_highlights()
    results = notes
    if query:
        query = query.lower()
        results = [note for note in results if 
                  query in note["title"].lower() or 
                  query in note["content"].lower()]
    
    if title:
        title = title.lower()
        results = [note for note in results if title in note["title"].lower()]
    
    return results

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
