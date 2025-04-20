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

# Internal model with embeddings
class KindleHighlight(BaseModel):
    id: str
    text: str
    note: Optional[str] = ""
    location: Optional[int] = None
    page: Optional[int] = None
    embedding: Optional[List[float]] = None

# Response model without embeddings
class KindleHighlightResponse(BaseModel):
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

class KindleBookResponse(BaseModel):
    title: str
    highlights: List[KindleHighlightResponse]
    cover_url: Optional[str] = None
    id: str

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

async def load_kindle_highlights(file_path="kindle_highlights_04062025_with_embeddings.jsonl", load_embeddings: bool = False):
    """
    Load highlights with optional embedding loading
    
    Args:
        load_embeddings: Whether to load the embedding vectors
    """
    books = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                try:
                    book_data_dict = json.loads(line.strip())
                    if not load_embeddings:
                        # Skip loading embeddings for each highlight
                        for highlight in book_data_dict['highlights']:
                            highlight.pop('embedding', None)
                    
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

@app.get("/")
async def get_home():
    return {"status": "ok", "message": "hola mundo!"}

@app.get("/books")
async def get_books():
    """Get all books with summary statistics (no highlights)"""
    books = await load_kindle_highlights(load_embeddings=False)
    
    # Create summarized version of each book
    summarized_books = []
    for book in books:
        # Calculate statistics for highlights
        location_count = len([h for h in book.highlights if h.location is not None])
        page_count = len([h for h in book.highlights if h.page is not None])
        total_highlights = len(book.highlights)
        
        # Find min/max positions for distribution visualization
        positions = {}
        if location_count > 0:
            locations = [h.location for h in book.highlights if h.location is not None]
            positions["location"] = {"min": min(locations), "max": max(locations)}
        if page_count > 0:
            pages = [h.page for h in book.highlights if h.page is not None]
            positions["page"] = {"min": min(pages), "max": max(pages)}
        
        # Add summarized book without highlights
        summarized_books.append({
            "id": book.id,
            "title": book.title,
            "cover_url": book.cover_url,
            "highlight_count": total_highlights,
            "positions": positions,
            "preferred_position_type": "location" if location_count >= page_count else "page"
        })
    
    return summarized_books

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
    # Only load embeddings when doing semantic search
    books = await load_kindle_highlights(load_embeddings=use_semantic)
    
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
    
    if not relevant_results:
        return StreamingResponse(
            iter([f"data: {json.dumps({'content': 'I couldn find any relevant information in your reading notes to answer this question.'})}\n\n",
                  f"data: {json.dumps({'done': True, 'sources': []})}\n\n"]),
            media_type="text/event-stream"
        )

    # Cluster the results and get context + visualization
    context, graph_data = await cluster_relevant_highlights(relevant_results)
    if not context:
        context = "\n\n".join([f"From '{book.title}' [{i+1}]:\n\"{highlight.text}\""
                              for i, (book, highlight, _) in enumerate(relevant_results[:5])])

    # Format sources for citation
    sources = [
        {
            "book_title": book.title,
            "book_id": book.id,
            "highlight_text": highlight.text,
            "relevance": float(score)
        }
        for book, highlight, score in relevant_results[:5]
    ]
    
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
            
            # Send sources and visualization at the end
            yield f"data: {json.dumps({'done': True, 'sources': sources, 'topics_visualization': graph_data})}\n\n"
            
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream"
    )

async def cluster_relevant_highlights(relevant_results, top_k=5):
    """
    Cluster the relevant highlights by topic before generating an answer
    Returns both topics and formatted context
    """
    # Take top K results
    top_results = relevant_results[:top_k]
    
    # Extract topics for each highlight
    topics_map = {}
    try:
        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        for i, (book, highlight, score) in enumerate(top_results):
            response = await client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Extract 1-2 main topics from this highlight. Return as comma-separated list. Be concise and consistent."},
                    {"role": "user", "content": highlight.text}
                ],
                temperature=0.3,
                max_tokens=50
            )
            topics = [t.strip() for t in response.choices[0].message.content.split(',')]
            
            for topic in topics:
                if topic not in topics_map:
                    topics_map[topic] = []
                topics_map[topic].append({
                    "book_title": book.title,
                    "text": highlight.text,
                    "citation": f"[{i+1}]",
                    "relevance": score
                })

    except Exception as e:
        print(f"Error clustering highlights: {e}")
        return None, None

    # Format context with topic grouping
    context = []
    for topic, highlights in topics_map.items():
        context.append(f"\nOn the topic of {topic}:")
        for h in highlights:
            context.append(f"From '{h['book_title']}' {h['citation']}:\n\"{h['text']}\"")
    
    # Enhanced graph structure to show cross-book connections
    graph_data = {
        "nodes": [],
        "links": []
    }
    
    # Track nodes to avoid duplicates
    added_nodes = set()
    
    # First pass: Add all topics and books as nodes
    for topic, highlights in topics_map.items():
        topic_id = f"topic_{hash(topic) % 1000}"
        
        if topic_id not in added_nodes:
            graph_data["nodes"].append({
                "id": topic_id,
                "name": topic,
                "type": "topic"
            })
            added_nodes.add(topic_id)
        
        # Add book nodes
        for h in highlights:
            book_id = f"book_{hash(h['book_title']) % 1000}"
            if book_id not in added_nodes:
                graph_data["nodes"].append({
                    "id": book_id,
                    "name": h['book_title'],
                    "type": "book"
                })
                added_nodes.add(book_id)
            
            # Add link between topic and book
            graph_data["links"].append({
                "source": topic_id,
                "target": book_id
            })
    
    # Second pass: Add connections between books that share topics
    book_topics = {}
    
    # Build book to topics mapping
    for topic, highlights in topics_map.items():
        topic_id = f"topic_{hash(topic) % 1000}"
        for h in highlights:
            book_id = f"book_{hash(h['book_title']) % 1000}"
            if book_id not in book_topics:
                book_topics[book_id] = set()
            book_topics[book_id].add(topic_id)
    
    # Connect books that share topics
    processed_pairs = set()
    for book_id, topics in book_topics.items():
        for other_book_id, other_topics in book_topics.items():
            if book_id != other_book_id:
                pair_key = tuple(sorted([book_id, other_book_id]))
                if pair_key not in processed_pairs:
                    common_topics = topics.intersection(other_topics)
                    if common_topics:  # If they share at least one topic
                        graph_data["links"].append({
                            "source": book_id,
                            "target": other_book_id,
                            "type": "book_to_book",  # Add type to distinguish link types
                            "strength": len(common_topics)  # Strength based on number of shared topics
                        })
                        processed_pairs.add(pair_key)
    
    return "\n\n".join(context), graph_data

@app.get("/book-thesis/{book_id}")
async def get_book_thesis(book_id: str):
    """Extract the core thesis and its consequences for a book"""
    books = await load_kindle_highlights()
    book = next((b for b in books if b.id == book_id), None)
    
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Get all highlights text
    highlights_text = "\n\n".join([h.text for h in book.highlights])
    
    # If text is too long, select a representative sample
    if len(highlights_text) > 12000:  # OpenAI context limit safety
        # Get first 20%, middle 30%, and last 20% of highlights to capture beginning, middle, and end
        highlight_count = len(book.highlights)
        first_part = book.highlights[:int(highlight_count * 0.2)]
        middle_part = book.highlights[int(highlight_count * 0.35):int(highlight_count * 0.65)]
        last_part = book.highlights[int(highlight_count * 0.8):]
        
        selected_highlights = first_part + middle_part + last_part
        highlights_text = "\n\n".join([h.text for h in selected_highlights])
    
    try:
        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are analyzing a book based on highlighted passages. Extract the main thesis of the book and its key consequences. Format as JSON with 'thesis' and 'consequences' (array of consequences). Be concise but precise."},
                {"role": "user", "content": f"These are highlights from '{book.title}':\n\n{highlights_text}\n\nBased on these highlights, what is the main thesis of the book and what are 3-5 key consequences of this thesis?"}
            ],
            temperature=0.5,
            response_format={"type": "json_object"}
        )
        
        analysis = json.loads(response.choices[0].message.content)
        
        # Format the response
        return {
            "book_title": book.title,
            "thesis": analysis.get("thesis", "Could not determine thesis"),
            "consequences": analysis.get("consequences", [])
        }
            
    except Exception as e:
        print(f"Error analyzing book: {e}")
        raise HTTPException(status_code=500, detail=f"Error extracting thesis: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
