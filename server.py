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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class KindleHighlight(BaseModel):
    text: str
    note: Optional[str] = ""

class KindleBook(BaseModel):
    title: str
    highlights: List[KindleHighlight]
    cover_url: Optional[str] = None
    id: Optional[str] = None

class Highlight(BaseModel):
    id: int
    title: str
    content: str
    location: str = Field(default="No location")
    cover_url: Optional[str] = None
class SearchResponse(BaseModel):
    results: List[KindleBook]
    count: int

async def load_kindle_highlights(file_path="kindle_highlights_02032025.jsonl"):
    await asyncio.sleep(0.1)
    books = {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                try:
                    book_data_dict = json.loads(line.strip())
                    book_data = KindleBook(**book_data_dict)
                    if book_data.id is None:
                        book_data.id = str(hash(book_data.title))
                    books[book_data.id] = book_data
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"Error processing book: {e}")
    except Exception as e:
        print(f"Error loading highlights: {e}")
    
    return list(books.values())

@app.get("/books", response_model=List[KindleBook])
async def get_books():
    """
    Get all books and stats 
    """
    books = await load_kindle_highlights()
    return books

@app.get("/search", response_model=SearchResponse)
async def search_notes(
    query: Optional[str] = Query(None, description="Search term"),
    title: Optional[str] = Query(None, description="Filter by book title")
):
    """
    Search the reading notes with optional filters:
    - Free text search across title and content
    - Title filter for specific books
    Returns results in KindleBook format
    """
    books = await load_kindle_highlights()
    results = []
    
    for book in books:
        matching_highlights = []
        
        # Apply filters
        title_match = True if not title else title.lower() in book.title.lower()
        
        if title_match:
            for highlight in book.highlights:
                content_match = True if not query else query.lower() in highlight.text.lower()
                
                if content_match:
                    matching_highlights.append(highlight)
        
        # If we have matching highlights, include this book in results
        if matching_highlights:
            # Create a copy of the book with only matching highlights
            filtered_book = KindleBook(
                title=book.title,
                highlights=matching_highlights,
                cover_url=book.cover_url,
                id=book.id
            )
            results.append(filtered_book)
    
    return SearchResponse(results=results, count=len(results))

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
