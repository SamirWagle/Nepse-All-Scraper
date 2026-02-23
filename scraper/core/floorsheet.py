import requests
from bs4 import BeautifulSoup
import json
import csv
import time
import logging
import os
import re
import random
from datetime import date as dt_date

# Setup logging
debug_dir = os.path.join(os.path.dirname(__file__), 'debug_output')
os.makedirs(debug_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(debug_dir, "headless_scraper.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class FloorsheetScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Origin": "https://merolagani.com",
            "Referer": "https://merolagani.com/Floorsheet.aspx"
        })
        self.url = "https://merolagani.com/Floorsheet.aspx"
        
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()
        
    def get_hidden_fields(self, soup):
        fields = {}
        for item in soup.find_all("input", type="hidden"):
            # Include all hidden inputs (VIEWSTATE, EVENTVALIDATION, etc.)
            # Also include any other hidden fields the page might have
            if item.get("name"):
                 fields[item.get("name")] = item.get("value")
        return fields

    def scrape_floorsheet(self, max_pages=None):
        logger.info(f"Fetching {self.url}...")
        try:
            # Initial GET request
            response = self.session.get(self.url, timeout=30)
            if response.status_code != 200:
                logger.error(f"Failed to load page: {response.status_code}")
                return []
                
            soup = BeautifulSoup(response.text, 'html.parser')
            all_records = []
            page_num = 1
            
            while True:
                logger.info(f"Processing page {page_num}...")
                
                # Extract data
                table = soup.find('table', class_='table-bordered')
                if not table:
                    logger.error("Table not found!")
                    break
                    
                rows = table.find('tbody').find_all('tr')
                page_records = []
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 8: continue
                    
                    try:
                        record = {
                            'date': str(dt_date.today()),   # YYYY-MM-DD
                            'sn': cols[0].get_text(strip=True),
                            'contract_no': cols[1].get_text(strip=True),
                            'stock_symbol': cols[2].get_text(strip=True),
                            'buyer': cols[3].get_text(strip=True),
                            'seller': cols[4].get_text(strip=True),
                            'quantity': cols[5].get_text(strip=True),
                            'rate': cols[6].get_text(strip=True),
                            'amount': cols[7].get_text(strip=True)
                        }
                        page_records.append(record)
                    except IndexError:
                        continue
                        
                all_records.extend(page_records)
                logger.info(f"Page {page_num}: Found {len(page_records)} records. Total: {len(all_records)}")
                
                # Check max pages
                if max_pages and page_num >= max_pages:
                    logger.info("Reached max pages limit.")
                    break
                
                # Find Next button logic
                # Look for title='Next Page'
                next_btn = soup.find('a', title='Next Page')
                if not next_btn:
                    # Fallback text search
                    next_btn = soup.find('a', string='Next')
                
                if not next_btn:
                    logger.info("No 'Next Page' link found. End of data.")
                    break
                    
                # Extract onclick: changesPageIndex("2", "ctl00...", "ctl00...")
                onclick = next_btn.get('onclick', '')
                if 'changePageIndex' not in onclick:
                    logger.warning(f"Unknown pagination script: {onclick}")
                    break
                
                # Regex to parse arguments: verify it matches pattern
                match = re.search(r"changePageIndex\(['\"]([^'\"]+)['\"],\s*['\"]([^'\"]+)['\"],\s*['\"]([^'\"]+)['\"]", onclick)
                if not match:
                    # Try simpler regex if spaces vary
                     match = re.search(r"changePageIndex\(['\"](.*?)['\"],['\"](.*?)['\"],['\"](.*?)['\"]", onclick.replace(" ", ""))
                
                if not match:
                     logger.warning(f"Could not parse onclick arguments: {onclick}")
                     break
                     
                next_page_num = match.group(1)
                hidden_field_id = match.group(2)
                submit_btn_id = match.group(3)
                
                logger.info(f"Next Page: {next_page_num}")
                
                # Get the 'name' attributes for these IDs from the soup
                hidden_input = soup.find(id=hidden_field_id)
                submit_input = soup.find(id=submit_btn_id)
                
                if not hidden_input or not submit_input:
                    logger.error("Could not find hidden inputs for pagination.")
                    break
                    
                hidden_name = hidden_input.get('name')
                submit_name = submit_input.get('name')
                
                # Prepare POST payload
                payload = self.get_hidden_fields(soup)
                
                # Update the page number field
                payload[hidden_name] = next_page_num
                
                # Add the submit button trigger
                # Submit buttons usually send their value if clicked
                # Or if we simulate it, we just add the key
                payload[submit_name] = '' 
                
                # Add random sleep
                time.sleep(random.uniform(1, 2))
                
                # POST
                logger.info(f"Requesting page {next_page_num}...")
                response = self.session.post(self.url, data=payload, timeout=45)
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch page {next_page_num}: {response.status_code}")
                    break
                    
                soup = BeautifulSoup(response.text, 'html.parser')
                page_num += 1
                
            return all_records

        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-pages', type=int, default=None)
    args = parser.parse_args()

    scraper = FloorsheetScraper()
    data = scraper.scrape_floorsheet(max_pages=args.max_pages)

    if not data:
        print("No data scraped.")
    else:
        today = str(dt_date.today())   # e.g. 2026-02-21
        data_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
        os.makedirs(data_dir, exist_ok=True)

        # ------- CSV (append-safe, one file per day) -------
        csv_path = os.path.join(data_dir, f'floorsheet_{today}.csv')
        fieldnames = ['date', 'sn', 'contract_no', 'stock_symbol', 'buyer', 'seller', 'quantity', 'rate', 'amount']
        file_exists = os.path.isfile(csv_path)
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerows(data)

        # ------- JSON (full dump for the day, overwrites) -------
        json_path = os.path.join(data_dir, f'floorsheet_{today}.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        print(f"Saved {len(data)} records to:")
        print(f"  CSV:  {csv_path}")
        print(f"  JSON: {json_path}")
