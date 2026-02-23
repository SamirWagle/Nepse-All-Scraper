
import requests
from bs4 import BeautifulSoup
import json
import csv
import os
import time
import logging
from datetime import datetime
import random

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ShareSansarHistoryScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Connection': 'keep-alive',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="120", "Google Chrome";v="120"',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
            'sec-ch-ua-mobile': '?0',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        self.base_url = "https://www.sharesansar.com"
        
    def get_latest_date(self, symbol):
        """
        Read the latest (most recent) date already saved in prices.csv.
        Returns a date string 'YYYY-MM-DD' or None if no file exists.
        """
        filepath = os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'company-wise', symbol, 'prices.csv'
        )
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, 'r') as f:
                reader = csv.DictReader(f)
                dates = [row['date'] for row in reader if row.get('date')]
            return max(dates) if dates else None
        except Exception:
            return None

    def scrape_company_history(self, symbol, stop_date=None):
        """
        Scrape price history for a single company.
        If stop_date (YYYY-MM-DD) is given, stops fetching once it reaches
        records on or before that date — making incremental runs very fast.
        Returns list of dicts: date, open, high, low, ltp, percent_change, qty, turnover
        """
        url = f"{self.base_url}/company/{symbol.lower()}"
        ajax_url = f"{self.base_url}/company-price-history"
        
        logger.info(f"Scraping history for {symbol}...")
        
        try:
            # Initial page load to get session cookies and CSRF token
            response = self.session.get(url, timeout=30)
            if response.status_code != 200:
                logger.error(f"Failed to load {symbol}: {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Get CSRF token
            csrf_token = soup.find('meta', {'name': '_token'})
            if csrf_token:
                csrf_token = csrf_token.get('content')
            else:
                logger.warning("CSRF token not found")
                csrf_token = ""
            
            # Get company ID from the page
            company_id_elem = soup.find('div', {'id': 'companyid'})
            company_id = company_id_elem.text.strip() if company_id_elem else ""
            
            # Scrape via AJAX with proper POST format
            all_records = self._scrape_via_ajax_post(ajax_url, symbol, csrf_token, company_id, stop_date=stop_date)
            
            logger.info(f"[OK] Scraped {len(all_records)} records for {symbol}")
            return all_records
            
        except Exception as e:
            logger.error(f"Error scraping {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def _parse_row(self, cols):
        """Parse a table row into a dict"""
        try:
            return {
                'date': cols[1].text.strip(),
                'open': float(cols[2].text.strip().replace(',', '') or 0),
                'high': float(cols[3].text.strip().replace(',', '') or 0),
                'low': float(cols[4].text.strip().replace(',', '') or 0),
                'ltp': float(cols[5].text.strip().replace(',', '') or 0),
                'percent_change': float(cols[6].text.strip().replace('%', '').replace(',', '') or 0),
                'qty': int(cols[7].text.strip().replace(',', '') or 0),
                'turnover': float(cols[8].text.strip().replace(',', '') or 0)
            }
        except (ValueError, IndexError) as e:
            logger.warning(f"Error parsing row values: {e}")
            return None
    
    
    def _scrape_via_ajax_post(self, ajax_url, symbol, csrf_token, company_id, stop_date=None):
        """Scrape data via POST to AJAX endpoint with DataTables pagination.
        Stops early if stop_date is set and a fetched record date <= stop_date.
        """
        all_records = []
        start = 0
        length = 50  # Records per page
        draw = 1
        
        # Update headers for AJAX request
        self.session.headers.update({
            'X-CSRF-Token': csrf_token,
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        })
        
        while True:
            # DataTables POST format - use company ID not symbol
            post_data = {
                'draw': draw,
                'start': start,
                'length': length,
                'company': company_id,  # Use company ID from the page
            }
            
            try:
                logger.info(f"Fetching records {start} to {start + length}...")
                response = self.session.post(ajax_url, data=post_data, timeout=30)
                
                if response.status_code != 200:
                    logger.error(f"AJAX request failed: {response.status_code}")
                    break
                
                data = response.json()
                
                # DataTables response format: { data: [...], recordsTotal: N, recordsFiltered: N }
                records = data.get('data', [])
                records_total = data.get('recordsTotal', 0)
                
                if not records:
                    logger.info("No more records")
                    break
                
                logger.info(f"Got {len(records)} records (Total: {records_total})")
                
                # Parse records - ShareSansar returns dict format
                for record in records:
                    try:
                        # Record is a dict
                        if not isinstance(record, dict):
                            continue
                        
                        # Extract values - ShareSansar uses different key names
                        date_val = record.get('published_date', '').strip()
                        open_val = record.get('open', '0').strip()
                        high_val = record.get('high', '0').strip()
                        low_val = record.get('low', '0').strip()
                        close_val = record.get('close', '0').strip()  # Note: 'close' not 'ltp'
                        pct_val = record.get('per_change', '0').strip()
                        qty_val = record.get('traded_quantity', '0').strip()
                        turnover_val = record.get('traded_amount', '0').strip()
                        
                        if not date_val:
                            continue
                        
                        parsed = {
                            'date': date_val,
                            'open': float(open_val.replace(',', '') or 0),
                            'high': float(high_val.replace(',', '') or 0),
                            'low': float(low_val.replace(',', '') or 0),
                            'ltp': float(close_val.replace(',', '') or 0),  # Map 'close' to 'ltp' for consistency
                            'percent_change': float(pct_val.replace('%', '').replace(',', '') or 0),
                            'qty': int(float(qty_val.replace(',', '') or 0)),
                            'turnover': float(turnover_val.replace(',', '') or 0)
                        }
                        
                        all_records.append(parsed)

                        # Stop early if we've hit dates we already have
                        if stop_date and date_val <= stop_date:
                            logger.info(f"Reached stop date {stop_date} — stopping early")
                            return all_records
                            
                    except (ValueError, AttributeError) as e:
                        logger.warning(f"Error parsing record: {e}")
                        continue
                
                # Check if more pages exist
                if start + length >= records_total:
                    logger.info("Reached end of data")
                    break
                
                start += length
                draw += 1
                time.sleep(random.uniform(0.5, 1.5))  # Polite delay
                
            except Exception as e:
                logger.error(f"AJAX pagination error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                break
        
        return all_records
    
    def update_company_csv(self, symbol, records):
        """
        Append new records to company CSV file, avoiding duplicates.
        Saves to data/company-wise/{symbol}/prices.csv
        """
        base_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'company-wise', symbol)
        os.makedirs(base_dir, exist_ok=True)
        
        filepath = os.path.join(base_dir, "prices.csv")
        
        # Read existing dates to prevent duplicates
        existing_dates = set()
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    reader = csv.DictReader(f)
                    existing_dates = {row['date'] for row in reader}
            except Exception as e:
                logger.warning(f"Could not read existing prices.csv for {symbol}: {e}")
        
        # Filter out duplicates
        new_records = [r for r in records if r['date'] not in existing_dates]
        
        if not new_records:
            logger.info(f"No new records for {symbol}")
            return
        
        # Append to CSV
        file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0
        
        try:
            with open(filepath, 'a', newline='') as f:
                fieldnames = ['date', 'open', 'high', 'low', 'ltp', 'percent_change', 'qty', 'turnover']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                
                if not file_exists:
                    writer.writeheader()
                
                writer.writerows(new_records)
            
            logger.info(f"[OK] Added {len(new_records)} new records to {symbol}/prices.csv")
        except Exception as e:
            logger.error(f"Failed to write to {symbol}/prices.csv: {e}")

    def scrape_all_companies(self, company_list_file='company_list.json'):
        """
        Scrape historical data for all companies in the list.
        """
        # Load company list
        list_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', company_list_file)
        
        try:
            with open(list_path, 'r') as f:
                symbols = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load company list: {e}")
            return
        
        logger.info(f"Starting bulk scrape for {len(symbols)} companies...")
        
        for i, symbol in enumerate(symbols, 1):
            logger.info(f"[{i}/{len(symbols)}] Processing {symbol}...")
            
            records = self.scrape_company_history(symbol)
            if records:
                self.update_company_csv(symbol, records)
            
            # Polite delay between companies
            time.sleep(random.uniform(2, 4))
        
        logger.info("[DONE] Bulk scrape complete!")

if __name__ == "__main__":
    scraper = ShareSansarHistoryScraper()
    
    # Test with a single company first (UNCOMMENT TO TEST)
    # logger.info("Running test scrape on HIDCL...")
    # records = scraper.scrape_company_history('HIDCL')
    # if records:
    #     scraper.update_company_csv('HIDCL', records)
    #     logger.info(f"Test complete! Got {len(records)} records for HIDCL")
    # else:
    #     logger.error("Test failed - no records retrieved")
    
    # Run full scrape for all companies
    scraper.scrape_all_companies()
