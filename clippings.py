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

def scrape_kindle_highlights(output_file='./kindle_highlights_02032025.jsonl'):
    """Scrape Kindle highlights from read.amazon.com
    """
    chrome_options = Options()
    chrome_options.add_argument("--window-size=1920,1080")
    driver = None
    books_to_parse = 10
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
            
            if i >= books_to_parse:
                break
                
        return books_data
        
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    scrape_kindle_highlights()