import uvicorn
from fastapi import FastAPI, Query, HTTPException
from typing import List, Optional
import asyncio
from fastapi.middleware.cors import CORSMiddleware
import json
from pydantic import BaseModel
import openai
import os
from dotenv import load_dotenv
from fastapi.responses import StreamingResponse

load_dotenv()

try:
    openai.api_key = os.getenv("OPENAI_API_KEY")
    assert openai.api_key is not None, "OpenAI API key is not set"
except Exception as e:
    print(f"Error loading OpenAI API key: {e}")

app = FastAPI(
    title="Reading Notes API",
    description="Simple async API for searching reading notes",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class KindleHighlight(BaseModel):
    id: str
    text: str
    note: Optional[str] = ""
    location: Optional[int] = None
    page: Optional[int] = None

class KindleBook(BaseModel):
    title: str
    highlights: List[KindleHighlight]
    cover_url: Optional[str] = None
    id: Optional[str] = None

class SearchResponse(BaseModel):
    results: List[KindleBook]
    count: int

class ExplainRequest(BaseModel):
    bookId: str
    highlightIndex: int
    text: str

class ExplainResponse(BaseModel):
    explanation: str

async def load_kindle_highlights(file_path="kindle_highlights_04062025.jsonl"):
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
        print(f"Error loding highlights: {e}")
    
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
        title_match = True if not title else title.lower() in book.title.lower()
        if title_match:
            for highlight in book.highlights:
                content_match = True if not query else query.lower() in highlight.text.lower()
                if content_match:
                    matching_highlights.append(highlight)
        if matching_highlights:
            filtered_book = KindleBook(
                title=book.title,
                highlights=matching_highlights,
                cover_url=book.cover_url,
                id=book.id
            )
            results.append(filtered_book)
    return SearchResponse(results=results, count=len(results))

@app.get("/books/{book_id}", response_model=KindleBook)
async def get_book(book_id: str):
    """
    Get a single book by ID with all its highlights
    """
    books = await load_kindle_highlights()
    for book in books:
        if book.id == book_id:
            return book
    raise HTTPException(status_code=404, detail="Book not found")

@app.get("/explain")
async def explain_highlight(
    bookId: str = Query(..., description="Book ID"),
    highlightIndex: int = Query(..., description="Highlight index"),
    text: str = Query(..., description="Text to explain")
):
    """
    Generate a streaming explanation for a highlight
    """
    books = await load_kindle_highlights()
    book = next((b for b in books if b.id == bookId), None)

    if not book or highlightIndex >= len(book.highlights):
        raise HTTPException(status_code=404, detail="Book or highlight not found")
    
    async def generate_stream():
        try:
            client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            stream = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that explains reading highlights clearly and concisely."},
                    {"role": "user", "content": f"Please explain this highlight from '{book.title}': \"{text}\""}
                ],
                max_tokens=300,
                temperature=0.7,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield f"data: {json.dumps({'content': chunk.choices[0].delta.content})}\n\n"
            
            yield f"data: {json.dumps({'done': True})}\n\n"
            
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream"
    )

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
