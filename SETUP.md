# NEPSE CAGR Extension — Setup Instructions

## Folder Structure
```
~/CodingProjects/Nepse-CAGR/
├── nepse_cagr_server.py       ← HTTP server (the engine)
├── nepse_host.py              ← Native messaging bridge
├── nepse_host_wrapper.sh      ← Shell wrapper for native messaging
├── com.nepse.cagr.json        ← Native messaging manifest
├── data/                      ← Stock data (auto-updated by GitHub Actions)
└── extension/                 ← Browser extension files
    ├── manifest.json
    ├── popup.html
    ├── popup.js
    ├── analyse.html
    ├── background.js
    └── icons/
        ├── icon16.png
        ├── icon32.png
        ├── icon48.png
        └── icon128.png
```

---

## Step 1 — Copy files into your repo

```bash
cp nepse_cagr_server.py ~/CodingProjects/Nepse-CAGR/
cp nepse_host.py ~/CodingProjects/Nepse-CAGR/
cp nepse_host_wrapper.sh ~/CodingProjects/Nepse-CAGR/
cp com.nepse.cagr.json ~/CodingProjects/Nepse-CAGR/
cp -r extension ~/CodingProjects/Nepse-CAGR/
```

---

## Step 2 — Make scripts executable

```bash
chmod +x ~/CodingProjects/Nepse-CAGR/nepse_host_wrapper.sh
chmod +x ~/CodingProjects/Nepse-CAGR/nepse_host.py
```

---

## Step 3 — Load extension in Brave

1. Open Brave → go to `brave://extensions`
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**
4. Select `~/CodingProjects/Nepse-CAGR/extension/`
5. **Copy the Extension ID** shown under the extension name

---

## Step 4 — Update Extension ID in com.nepse.cagr.json

Open `com.nepse.cagr.json` and replace `REPLACE_WITH_YOUR_EXTENSION_ID` with the actual ID:

```json
"allowed_origins": [
  "chrome-extension://abcdefghijklmnopqrstuvwxyz123456/"
]
```

---

## Step 5 — Install Native Messaging manifest

```bash
cp ~/CodingProjects/Nepse-CAGR/com.nepse.cagr.json \
   ~/Library/Application\ Support/BraveSoftware/Brave-Browser/NativeMessagingHosts/
```

---

## Step 6 — Add icons

Place your NEPSE CAGR icon image into the extension/icons/ folder as:
- `icon16.png`  (16×16)
- `icon32.png`  (32×32)
- `icon48.png`  (48×48)
- `icon128.png` (128×128)

You can resize from the original icon image using Preview on Mac.

---

## Step 7 — Test it!

1. Click the NEPSE CAGR icon in Brave toolbar
2. Type a symbol e.g. `NABIL`
3. Click **Calculate CAGR**
4. First run starts the engine (~5-15s), subsequent runs are instant

---

## Notes
- The engine starts automatically when you first click Calculate
- It stays running in background until you restart your Mac
- Check `nepse_engine.log` in the repo folder if something goes wrong
