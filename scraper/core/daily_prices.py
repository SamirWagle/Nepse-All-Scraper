
import requests
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DailySummaryUpdater:
    """
    Updates daily stock price data for all companies using ShareSansar's Today Price page.
    This is the simplest and most reliable method for daily updates.
    """
    
    def __init__(self):
        self.url = "https://www.sharesansar.com/today-share-price"
        self.data_dir = Path(__file__).parent.parent.parent / "data" / "company-wise"
        
    def update_all_companies(self, priority_only=True):
        """Fetch today's data and update all company CSVs"""
        logger.info(f"Fetching data from {self.url}...")
        
        # Load priority list if requested
        priority_list = None
        if priority_only:
            try:
                list_path = self.data_dir.parent / "company_list.json"
                if list_path.exists():
                    import json
                    with open(list_path, 'r') as f:
                        priority_list = set(json.load(f))
                    logger.info(f"Loaded {len(priority_list)} priority companies.")
            except Exception as e:
                logger.error(f"Failed to load priority list: {e}")
        
        try:
            # Fetch the page
            response = requests.get(self.url, timeout=30)
            html = response.text
            soup = BeautifulSoup(html, "lxml")
            
            # Extract today's date
            date_elem = soup.find("span", {"class": "text-org"})
            if not date_elem:
                logger.error("Could not find date on page. Market may be closed.")
                return 0
                
            today = date_elem.text.strip()
            logger.info(f"Market date: {today}")
            
            # Parse the price table using pandas
            tables = pd.read_html(html)
            if not tables:
                logger.error("No tables found on page")
                return 0
                
            price_table = tables[0]
            logger.info(f"Found {len(price_table)} companies in today's data")
            
            # Update each company's CSV
            updated_count = 0
            skipped_count = 0
            
            # Iterate through directories
            for symbol_dir in self.data_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue
                
                symbol = symbol_dir.name
                
                # Filter by priority list
                if priority_list and symbol not in priority_list:
                    continue
                
                csv_file = symbol_dir / "prices.csv"
                
                if not csv_file.exists():
                     # Skip if no price file
                     continue
                
                # Check if data already exists for today
                try:
                    existing_df = pd.read_csv(csv_file)
                    if len(existing_df) > 0:
                        last_date = str(existing_df.iloc[-1]['date'])
                        
                        if last_date == today:
                            skipped_count += 1
                            continue  # Already have today's data
                except (KeyError, FileNotFoundError) as e:
                    logger.warning(f"Error reading {symbol}/prices.csv: {e}")
                    continue
                
                # Find this symbol in today's data
                symbol_data = price_table.loc[price_table['Symbol'] == symbol]
                
                if len(symbol_data) == 1:
                    row = symbol_data.iloc[0]
                    
                    # Create new row matching our CSV format
                    new_row = pd.DataFrame([{
                        'date': today,
                        'open': float(row['Open']),
                        'high': float(row['High']),
                        'low': float(row['Low']),
                        'ltp': float(row['Close']),  # 'Close' maps to 'ltp'
                        'percent_change': float(row['Diff %']),
                        'qty': int(float(row['Vol'])),
                        'turnover': float(row['Turnover'])
                    }])
                    
                    # Append to CSV
                    new_row.to_csv(csv_file, mode='a', header=False, index=False)
                    updated_count += 1
                    
                elif len(symbol_data) == 0:
                    logger.debug(f"No data found for {symbol} (not traded today)")
                else:
                    logger.warning(f"Multiple rows found for {symbol}")
            
            logger.info(f"✅ Updated: {updated_count} companies")
            logger.info(f"⏭️  Skipped: {skipped_count} companies (already have today's data)")
            
            return updated_count
            
        except Exception as e:
            logger.error(f"Error updating daily prices: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0

if __name__ == "__main__":
    updater = DailySummaryUpdater()
    updater.update_all_companies()
