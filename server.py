import uvicorn
from fastapi import FastAPI, Query
from typing import List, Dict, Any, Optional
import asyncio
from fastapi.middleware.cors import CORSMiddleware
import json
from pydantic import BaseModel, Field


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

# Pydantic models for Kindle highlights data
class KindleHighlight(BaseModel):
    text: str
    note: Optional[str] = ""

class KindleBook(BaseModel):
    title: str
    highlights: List[KindleHighlight]
    id: Optional[str] = None

class Highlight(BaseModel):
    id: int
    title: str
    content: str
    location: str = Field(default="No location")

class SearchResponse(BaseModel):
    results: List[Highlight]
    count: int

async def load_kindle_highlights(file_path="kindle_highlights_02032025.jsonl"):
    await asyncio.sleep(0.1)
    highlights = []
    id_counter = 1
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                try:
                    book_data_dict = json.loads(line.strip())
                    # Validate with Pydantic model
                    book_data = KindleBook(**book_data_dict)
                    
                    for highlight in book_data.highlights:
                        highlights.append({
                            "id": id_counter,
                            "title": book_data.title,
                            "content": highlight.text,
                            "location": highlight.note or "No location"
                        })
                        id_counter += 1
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"Error processing highlight: {e}")
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
