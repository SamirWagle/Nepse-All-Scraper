# NEPSE News Digest — n8n Setup

## Install
```bash
pip install requests beautifulsoup4 --break-system-packages
```

## Run standalone
```bash
python3 nepse_news_digest.py --hours 24
```
Prints a JSON object to stdout and writes `nepse_digest.md` alongside the script.

## Wiring into n8n
1. **Execute Command** node → `python3 /path/to/nepse_news_digest.py --hours 24`
2. Parse stdout as JSON (n8n does this automatically if you set the node's
   output parsing, or pipe through a **Code** node: `JSON.parse($input.item.json.stdout)`)
3. Feed `items` into whatever delivery node you want — Telegram, Gmail, a
   Slack webhook, etc. Each item has `source`, `title`, `url`, `published`.
4. Schedule with a **Cron** node (e.g. daily 7:00 AM Kathmandu time).

## Customizing
- `--keywords "NEPSE,IPO,rights share"` — override the default keyword list
- `--hours 12` — shorten/lengthen the lookback window
- Edit `REDDIT_SUBREDDITS` in the script to add/remove subreddits
- Edit `FACEBOOK_PAGES` + pass `--fb-token YOUR_TOKEN` to include specific
  **public Facebook pages** (not groups — see note below)

## On Facebook groups
There's no reliable or ToS-compliant way to scrape Facebook group posts via
script — Meta's Graph API doesn't expose group content to third-party apps,
and browser-automation scraping breaks constantly and risks account bans.
The script supports public **pages** only (via Graph API + your own access
token). If specific groups matter to you, the realistic option is manually
forwarding posts of interest, not automating it.

## Known fragility
- Sharesansar/Merolagani are scraped via CSS selectors on their HTML, which
  **will break if they redesign their site** — the `.select(...)` calls in
  `fetch_sharesansar()` / `fetch_merolagani()` are the first place to check
  if output goes empty.
- Reddit's public `.json` endpoints are unauthenticated and can be rate
  limited if called too frequently — daily/hourly cron is fine, tighter
  loops are not.
