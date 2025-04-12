import uvicorn
from fastapi import FastAPI, Query, HTTPException
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
import json
from pydantic import BaseModel
import openai
import os
from dotenv import load_dotenv
from fastapi.responses import StreamingResponse
import numpy as np

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
    embedding: Optional[List[float]] = None

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

def cosine_similarity(a, b):
    """
    Calculate cosine similarity between two vectors.
    
    Args:
        a: First vector
        b: Second vector
        
    Returns:
        Cosine similarity score between 0 and 1
    """
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

async def load_kindle_highlights(file_path="kindle_highlights_04062025_with_embeddings.jsonl"):
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

async def retrieve_relevant_highlights(query: str, use_semantic: bool = True, similarity_threshold: float = 0.2):
    """
    Retrieve highlights relevant to a query using either semantic or keyword search
    
    Args:
        query: The search query
        use_semantic: Whether to use semantic search with embeddings
        similarity_threshold: Threshold for semantic similarity (0-1)
        
    Returns:
        List of (book, highlight, similarity_score) tuples sorted by relevance
    """
    books = await load_kindle_highlights()
    results = []
    query_embedding = None
    
    if use_semantic and query:
        try:
            client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            query_embedding = response.data[0].embedding
        except Exception as e:
            print(f"Error generating embedding for query: {e}")
    
    for book in books:
        for highlight in book.highlights:
            similarity = 0.0
            
            if use_semantic and query and query_embedding and highlight.embedding:
                similarity = cosine_similarity(query_embedding, highlight.embedding)
                if similarity > similarity_threshold:
                    results.append((book, highlight, similarity))
            elif not use_semantic or not query_embedding:
                if not query or query.lower() in highlight.text.lower():
                    # For keyword search, use a simple match score
                    similarity = 1.0 if query and query.lower() in highlight.text.lower() else 0.5
                    results.append((book, highlight, similarity))
    
    # Sort results by similarity score in descending order
    results.sort(key=lambda x: x[2], reverse=True)
    return results

@app.get("/search", response_model=SearchResponse)
async def search_notes(
    query: Optional[str] = Query(None, description="Search term"),
    use_semantic: bool = Query(True, description="Use semantic search")
):
    """
    Search the reading notes with optional filters:
    - Free text search across title and content
    - Title filter for specific books
    Returns results in KindleBook format
    """
    results_tuples = await retrieve_relevant_highlights(query, use_semantic)
    
    # Group results by book
    book_highlights = {}
    for book, highlight, _ in results_tuples:
        if book.id not in book_highlights:
            book_highlights[book.id] = {
                "title": book.title,
                "cover_url": book.cover_url,
                "id": book.id,
                "highlights": []
            }
        book_highlights[book.id]["highlights"].append(highlight)
    
    # Convert to KindleBook objects
    results = [
        KindleBook(
            title=book_data["title"],
            highlights=book_data["highlights"],
            cover_url=book_data["cover_url"],
            id=book_data["id"]
        )
        for book_data in book_highlights.values()
    ]
    
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

class AnswerResponse(BaseModel):
    answer: str
    sources: List[dict]

@app.get("/answer")
async def answer_question_stream(
    question: str = Query(..., description="Question to answer")
):
    """
    Stream an answer to a question based on the reading notes
    """
    # Get relevant highlights using the retrieve function
    relevant_results = await retrieve_relevant_highlights(question, use_semantic=True, similarity_threshold=0.3)
    top_k = 5
    
    # Format sources for citation
    sources = [
        {
            "book_title": book.title,
            "book_id": book.id,
            "highlight_text": highlight.text,
            "relevance": float(score)
        }
        for book, highlight, score in relevant_results[:top_k]
    ]
    
    if not relevant_results:
        return StreamingResponse(
            iter([f"data: {json.dumps({'content': 'I couldn find any relevant information in your reading notes to answer this question.'})}\n\n",
                  f"data: {json.dumps({'done': True, 'sources': []})}\n\n"]),
            media_type="text/event-stream"
        )
    
    # Format context from highlights with citation markers
    context_with_citations = []
    for i, (book, highlight, _) in enumerate(relevant_results[:top_k]):
        citation_marker = f"[{i+1}]"
        context_with_citations.append(f"From '{book.title}' {citation_marker}:\n\"{highlight.text}\"")
    
    context = "\n\n".join(context_with_citations)
    
    async def generate_stream():
        try:
            client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            stream = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that answers questions based on the user's reading notes. Use only the provided context to answer questions. When you reference information from the context, include the citation number in square brackets [1], [2], etc. that corresponds to the source."},
                    {"role": "user", "content": f"Context from my reading notes:\n{context}\n\nBased only on this context, please answer my question and include citation numbers [1], [2], etc. when referencing specific sources: {question}"}
                ],
                max_tokens=500,
                temperature=0.7,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield f"data: {json.dumps({'content': chunk.choices[0].delta.content})}\n\n"
            
            # Send sources at the end
            yield f"data: {json.dumps({'done': True, 'sources': sources})}\n\n"
            
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream"
    )

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
