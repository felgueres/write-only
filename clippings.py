import re
from datetime import datetime
import time
import hashlib
import json
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service

def generate_id(book_title):
    """Generate a deterministic ID based on book title, text content, and location."""
    seed = f"{book_title}"
    return hashlib.md5(seed.encode('utf-8')).hexdigest()[:12]

def scrape_highlights_from_clippings(file_path: str):
    books = {}
    
    with open(file_path, 'r', encoding='utf-8-sig') as file:
        content = file.read()
        clippings = content.split("==========")
        print(f"Found {len(clippings)} clippings")
        
        for clipping in clippings:
            clipping = clipping.strip()
            if not clipping:
                continue
                
            lines = clipping.split('\n')
            lines = [line.strip() for line in lines if line.strip()]
            
            if len(lines) < 3:
                continue
            
            if "You have reached the clipping limit for this item" in clipping:
                continue
                
            book_info = lines[0]
            metadata_line = lines[1]
            highlight_text = '\n'.join(lines[2:])
            if "(" in book_info and ")" in book_info:
                book_title, author = book_info.rsplit("(", 1)
                book_title = book_title.strip().replace('\ufeff', '')
                author = author.rstrip(")").strip()
            else:
                book_title = book_info.replace('\ufeff', '')
                author = "Unknown"
            
            entry_type = "note" if "Your Note" in metadata_line else "highlight"
            
            page_num = None
            location = None
            timestamp = None
            
            page_match = re.search(r'page (\d+)', metadata_line)
            if page_match:
                page_num = int(page_match.group(1))
                
            location_match = re.search(r'Location (\d+(?:-\d+)?)', metadata_line)
            if location_match:
                location = location_match.group(1)
                
            timestamp_match = re.search(r'Added on (.*)', metadata_line)
            if timestamp_match:
                try:
                    timestamp_str = timestamp_match.group(1)
                    timestamp = datetime.strptime(timestamp_str, "%A, %B %d, %Y %I:%M:%S %p")
                except ValueError:
                    timestamp = timestamp_match.group(1)
            
            book_id = generate_id(book_title, author, "")
            
            if book_id not in books:
                books[book_id] = {
                    "title": book_title,
                    "author": author,
                    "highlights": [],
                    "notes": [],
                    "id": book_id
                }
            
            entry = {
                "text": highlight_text,
                "page_num": page_num,
                "location": location,
                "timestamp": timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp,
                "id": generate_id(book_title, highlight_text, location)
            }
            
            if entry_type == "highlight":
                books[book_id]["highlights"].append(entry)
            else:
                books[book_id]["notes"].append(entry)
    
    return books

def scrape_kindle_highlights(output_file='./kindle_highlights_02032025.jsonl'):
    """Scrape Kindle highlights from read.amazon.com
    
    If use_user_profile is True, the script will use your default Chrome profile
    with all your existing cookies and login sessions.
    """
    chrome_options = Options()
    chrome_options.add_argument("--window-size=1920,1080")
    driver = None
    try:
        assert os.path.exists('./chromedriver'), "chromedriver not found"

        service = Service('./chromedriver')
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get("https://read.amazon.com/notebook")

        input("Press Enter after you've logged in...")
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "library"))
        )

        books_data = {}
        book_elements = driver.find_elements(By.CSS_SELECTOR, ".kp-notebook-library-each-book")
        total_books = len(book_elements)
        
        for i, book_element in enumerate(book_elements, 1):
            print(f"Processing book {i}/{total_books}")
            book_element.click()
            book_info = WebDriverWait(book_element, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".kp-notebook-searchable"))
            )
            book_title = book_info.text.strip()
            book_id = generate_id(book_title)
            if book_id not in books_data:
                books_data[book_id] = {
                    "title": book_info.text.strip() or "Title Error",
                    "highlights": [],
                    "id": book_id
                }
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "kp-notebook-annotations"))
            )
            time.sleep(7)
            highlight_elements = driver.find_elements(By.CSS_SELECTOR, ".kp-notebook-highlight")
            for highlight_element in highlight_elements:
                text_highlight = highlight_element.find_elements(By.CSS_SELECTOR, "#highlight")
                highlight_text = text_highlight[0].text.strip() if text_highlight else ""
                text_note = highlight_element.find_elements(By.CSS_SELECTOR, "#note")
                note_text = text_note[0].text.strip() if text_note else ""
                highlight_entry = {
                    "text": highlight_text,
                    "note": note_text,
                }
                books_data[book_id]["highlights"].append(highlight_entry)

            with open(output_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(books_data[book_id], ensure_ascii=False) + '\n')
                
        return books_data
        
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    books = scrape_kindle_highlights()
    print(books)