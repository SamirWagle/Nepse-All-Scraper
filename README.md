
```markdown
# Nepse-CAGR

A tool to calculate the CAGR (Compound Annual Growth Rate) of any NEPSE stock.

Forked from [SamirWagle/Nepse-All-Scraper](https://github.com/SamirWagle/Nepse-All-Scraper) — which handles all data scraping automatically via GitHub Actions every weekday.

---

## What I Added

A Python script `nepse_cagr.py` that calculates the CAGR of any NEPSE stock using the scraped data, accounting for:
- Bonus shares
- Right shares (units added + cost added to total investment)
- Cash dividends

A **Brave/Chrome browser extension** that provides a UI to run the calculator directly from your browser.

---

## CAGR Formula

```
(Today's Value / Total Invested) ^ (1 / years) - 1
```

Where:
- **Today's Value** = (total units today × LTP) + total cash dividends received
- **Total Invested** = initial investment + right share costs paid
- Units grow with each bonus share and right share
- Cash dividends = cumulative units × face value (Rs. 100) × cash %
- Cash dividend is calculated on units *before* bonus shares are applied on the same date

---

## Data Sources

Data is scraped automatically from NEPSE every weekday via GitHub Actions and stored in:

```
data/company-wise/{SYMBOL}/prices.csv
data/company-wise/{SYMBOL}/dividend.csv
data/company-wise/{SYMBOL}/right-share.csv
```

> **Note:** Data updates at ~8:30 PM NPT on weekdays, so LTP is always the previous day's closing price.

---

## How to Use

### Command Line

#### Setup
```bash
git clone https://github.com/karmataklu-bot/Nepse-CAGR.git
cd Nepse-CAGR
pip install pandas
```

#### Run
```bash
# Interactive mode
python nepse_cagr.py

# With flags
python nepse_cagr.py --symbol NABIL --years 5
python nepse_cagr.py --symbol NABIL --start-date 2018-01-15
python nepse_cagr.py --symbol NABIL --start-date 2018-01-15 --investment 200000
```

#### Flags

| Flag | Description | Default |
|---|---|---|
| `--symbol` | Stock symbol e.g. `NABIL` | prompted |
| `--years` | Years back from today e.g. `5` | prompted |
| `--start-date` | Specific start date `YYYY-MM-DD` | prompted |
| `--investment` | Initial investment in Rs. | 100,000 |
| `--data-dir` | Path to data folder | auto |
| `--quiet` | Print only the CAGR result | off |

---

### Browser Extension (Brave/Chrome)

The extension provides a popup UI to calculate CAGR without using the terminal.

#### How it works

```
Browser Extension (popup.html/popup.js)
        ↓  native messaging
nepse_host.py  (native messaging bridge)
        ↓  starts on first click
nepse_cagr_server.py  (HTTP server on localhost:5758)
        ↓  reads local data files
data/company-wise/{SYMBOL}/
```

The extension communicates with a local Python HTTP server via a **native messaging bridge** — no internet connection required, all data stays on your machine.

#### Extension files
```
extension/
├── manifest.json
├── popup.html
├── popup.js
├── analyse.html
├── background.js
└── icons/

nepse_cagr_server.py      # HTTP engine on localhost:5758
nepse_host.py             # native messaging bridge
nepse_host_wrapper.sh     # shell wrapper for native messaging
com.nepse.cagr.json       # native messaging host manifest
```

#### Setup (macOS)
1. Clone this repo locally — the extension reads data from your local clone
2. Install the native messaging manifest:
```bash
cp com.nepse.cagr.json \
  ~/Library/Application\ Support/BraveSoftware/Brave-Browser/NativeMessagingHosts/
```
3. Make scripts executable:
```bash
chmod +x nepse_host.py nepse_host_wrapper.sh nepse_cagr_server.py
```
4. Load the extension in Brave:
   - Go to `brave://extensions`
   - Enable **Developer mode**
   - Click **Load unpacked** → select the `extension/` folder
5. Click the extension icon — the server starts automatically

---

## Automation

GitHub Actions scrapes fresh data every weekday at ~8:30 PM NPT automatically.

To keep your local clone updated, set up a cron job:

```bash
30 21 * * 0-4 cd ~/CodingProjects/Nepse-CAGR && git pull
```

---

## Credits

- Data scraping by [SamirWagle/Nepse-All-Scraper](https://github.com/SamirWagle/Nepse-All-Scraper)
- Sources: ShareSansar, Merolagani
```

The main addition is the **Browser Extension** section which explains the architecture (extension → native messaging → HTTP server → data files), lists all the files, and gives step-by-step setup instructions for macOS.
