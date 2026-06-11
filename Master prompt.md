# Desktop Widget — Master Rebuild Prompt

> **Purpose**: Rebuild this project from scratch. Every section is a self-contained spec. The project is a fullscreen desktop dashboard for a legacy Windows laptop, displaying a 7-segment digital clock and a live stock portfolio table with SQLite-backed price caching.

---

## PAGE 1 — PROJECT OVERVIEW & ARCHITECTURE

### 1.1 What This Project Is

A single-page web dashboard served by a local Flask Python server, designed to run fullscreen on low-power hardware. Two widgets:

- **Clock Widget** — 7-segment digital clock, day/night PNG digit themes, blinking colon, server-synced time.
- **Portfolio Widget** — Live stock/ETF/cash position table with P&L, prices from Yahoo Finance, positions from `input.csv`, persistent fallback prices in SQLite.

### 1.2 Runtime Architecture

```
[Windows Laptop] → Python Flask (single-threaded)
    ├── /          → renders index.html with Jinja2 config
    ├── /api/data  → JSON portfolio payload (polled by frontend)
    └── /api/time  → JSON server time + day/night mode (separate poll)
```

```
CSV → parse positions → sync SQLite → Yahoo API per ticker
    → on success: rotate price in DB, serve live (white text)
    → on failure: serve fallback from DB (grey text)
    → calculate P&L → JSON → AJAX → HTML table
```

- **Backend**: Python 3.x, Flask (`threaded=False`, `debug=False`), requests, sqlite3 (stdlib).
- **Frontend**: Vanilla HTML/CSS/JS — no frameworks, no npm, no CDN. Jinja2 for config injection.
- **Two independent polling loops**: portfolio at `DATA_REFRESH_INTERVAL_MS` (default 10s), clock at hardcoded 15s.

### 1.3 Design Constraints

- Flask **single-threaded** — no concurrency, no async.
- Video backgrounds: **H.264 Base Profile, ≤720p** to avoid CPU lock on legacy hardware.
- JS uses **XMLHttpRequest** for broad browser compatibility.
- All dependencies local — no CDN, no external services except Yahoo Finance.

---

## PAGE 2 — BACKEND: app.py COMPLETE SPECIFICATION

### 2.1 Library Auto-Installer

At startup, before any real imports, check and auto-install missing libs:

```
Required: flask→Flask, requests→requests
For each: try __import__ → [OK] or [MISSING]
If any missing → subprocess pip install each → continue
```

### 2.2 Imports

```python
import csv, json, requests, sqlite3
from datetime import datetime
from flask import Flask, render_template, jsonify
import config
```

### 2.3 Global State

```python
portfolio_widget_ready = True    # False if CSV missing
clock_widget_ready = True        # always ready
portfolio_error_msg = ""
clock_error_msg = ""
```

### 2.4 Startup Self-Tests — `run_startup_self_tests()`

Check `os.path.exists(config.CSV_PATH)`. If missing → `portfolio_widget_ready = False`, `portfolio_error_msg = "input.csv not found"`. Clock is always ready.

### 2.5 Helper — `clean_numeric_value(val)`

Strips `$`, `,`, spaces from string. Returns `float` or `0.0` on empty/ValueError.

### 2.6 CSV Parser — `parse_csv_positions()`

Returns `(positions: list[dict], start_balance: float)`.

```
1. Read all rows via csv.reader, encoding='utf-8-sig'
2. Find "Start ball" → row[5]=='Start ball', next row[5]=balance
3. Find header → row[1]=='Price' AND row[2]=='My aver', header_index=row+1
4. Parse from header_index:
   - Stop: row[0] in ('History','Start') OR row[1]=='Price'
   - Skip: ticker==""
   - Extract: ticker=row[0], csv_price=clean(row[1]), avg_price=clean(row[2]), quantity=clean(row[3])
   - Append: {"ticker","csv_price","avg_price","quantity"}
```

### 2.7 Yahoo Finance API — `fetch_yahoo_price(ticker)`

Returns `(current_price, prev_close, success_flag)`.

```
URL: https://query1.finance.yahoo.com/v8/finance/chart/{ticker}
Params: range=2d, interval=1d
Headers: User-Agent=Mozilla/5.0…Chrome/56.0…
Timeout: 10s

Extraction (two paths, tried in order):
  PATH A — indicators.quote[0].close array:
    closes = data['chart']['result'][0]['indicators']['quote'][0]['close']
    If length>=2 AND both non-None → current=closes[-1], prev=closes[-2]

  PATH B — meta node:
    current = meta['regularMarketPrice'], prev = meta['previousClose']

  Any failure → return ("N/A","N/A",False)
```

**Only fields actually used by the code:**

| Path | Used for |
|------|----------|
| `indicators.quote[0].close[-1]` | Current price (Path A) |
| `indicators.quote[0].close[-2]` | Previous close (Path A) |
| `meta.regularMarketPrice` | Current price (Path B) |
| `meta.previousClose` | Previous close (Path B) |

**Rate limit**: ~100–120 req/min per IP (empirical, unofficial). No auth token required.

### 2.8 SQLite Price Cache

Schema (`prices.db`, auto-created on first run):

| Column | Type | Purpose |
|--------|------|---------|
| `ticker` | TEXT PK | Ticker symbol |
| `current_price` | REAL | Latest API price |
| `fallback_price` | REAL | Previous price (backup) |
| `from_input` | INT (0/1) | 1 = ticker exists in current CSV |

**`init_db()`** — `CREATE TABLE IF NOT EXISTS`.

**`sync_db_from_csv(positions)`** — Set all `from_input=0`, then upsert each CSV ticker with `from_input=1`. Cash tickers auto-set both prices to `1.0`. New tickers inserted with `0.0`.

**`prompt_fallback_overrides()`** — Queries `from_input=1` non-cash tickers. Asks: "Override fallback prices? (y/n)". If yes, loops each ticker showing current fallback, user types new price or Enter to keep.

**`rotate_db_price(ticker, new_price)`** — Moves `current_price` → `fallback_price`, writes new API price → `current_price`.

**`get_fallback_price(ticker)`** — Returns `fallback_price` from DB or `None`.

### 2.9 Cash Detection — `is_cash_ticker(ticker)`

`ticker.upper()` contains 'USD', 'USDT', or 'CASH' → skip API, price always `1.0`.

### 2.10 Position Calculator — `calculate_position(position, current_price, prev_close)`

Returns `(dict, success_bool)`. Output keys: `ticker, last_price, avg_price, quantity, current_value, invested_value, pnl, pnl_pct`.

**Cash**: last_price=1.0, current_value=csv_price×qty, invested=avg×qty, pnl=0, pnl_pct=0.

**Stock/ETF** (current_price is valid float):
- `last_price = current_price`
- `current_value = current_price × qty`
- `invested_value = avg_price × qty`
- **Long** (qty≥0): `pnl = (current-avg) × qty`, `pnl_pct = ((current-avg)/avg) × 100`
- **Short** (qty<0): `pnl = (avg-current) × abs(qty)`, `pnl_pct = ((avg-current)/avg) × 100`
- Guard: `avg_price==0` → `pnl_pct=0`

**API failure** (current_price="N/A"): last_price="N/A", all values 0.0, success=False.

### 2.11 Totals Aggregator — `calculate_totals(positions_data, start_balance)`

```
total_current_value = sum(current_value)
total_invested = sum(invested_value)
total_pnl = sum(pnl)
total_pnl_pct = weighted avg: sum(pnl_pct × |invested|) / sum(|invested|)
actual_pnl_usd = total_current_value - start_balance
actual_pnl_pct = (actual_pnl_usd / start_balance) × 100  (0 if start_balance==0)
```

### 2.12 Data Pipeline — `collect_portfolio_data()`

```
1. positions_raw, start_balance = parse_csv_positions()
2. If empty → return offline payload with empty positions []
3. sync_db_from_csv(positions_raw)
4. For each position:
     Cash → calculate with price=1.0, online=True
     Stock → fetch_yahoo_price(ticker):
       Success → rotate_db_price, calculate with live price, online=True
       Failure → get_fallback_price(ticker):
         Has fallback → calculate with fallback, online=False
         No fallback → calculate with "N/A", online=False
5. calculate_totals → build JSON payload
```

JSON payload per position now includes `"online": true/false`.

```json
{
  "network_status": "online"|"offline",
  "timestamp": "YYYY-MM-DD HH:MM:SS",
  "widget_errors": {"portfolio":"...", "clock":"..."},
  "totals": {"total_current_value", "total_invested", "total_pnl",
             "total_pnl_pct", "start_balance", "actual_pnl_usd", "actual_pnl_pct"},
  "positions": [{"ticker","last_price","avg_price","quantity",
                 "current_value","invested_value","pnl","pnl_pct","online"}, ...]
}
```

### 2.13 Flask Routes

| Route | Description |
|-------|-------------|
| `GET /` | Renders `index.html`, injects ALL config values + error messages via Jinja2 |
| `GET /api/data` | Calls `collect_portfolio_data()`, returns JSON |
| `GET /api/time` | Returns `{hours, minutes, hours_str, minutes_str, clock_mode}` |

**`/api/time` day/night logic**: Convert current time to total minutes. If `DAY_START ≤ current < DAY_END` → `"day"`, else `"night"`. Hours/minutes zero-padded to 2 digits.

### 2.14 Entry Point

```
1. run_startup_self_tests()
2. init_db()
3. Parse CSV → if positions exist → sync_db_from_csv + prompt_fallback_overrides()
4. Print startup banner (widget status, background type, polling interval)
5. app.run(host='0.0.0.0', port=5000, threaded=False, debug=False)
6. On exception → print FATAL ERROR
7. Finally → input("Press ENTER...") keeps console open
```

---

## PAGE 3 — CONFIGURATION & CSV FORMAT

### 3.1 config.py — Complete Spec

```python
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "input.csv")
DB_PATH = os.path.join(BASE_DIR, "prices.db")
CLOCK_ASSET_DIR = os.path.join(BASE_DIR, "static", "digits")
BACKGROUND_ASSET_DIR = os.path.join(BASE_DIR, "static", "bg")

# Day/Night Clock (24h)
DAY_START_HOUR = 6
DAY_START_MINUTE = 0
DAY_END_HOUR = 21
DAY_END_MINUTE = 0

# Polling — portfolio only (clock is hardcoded 15s in dashboard.js)
DATA_REFRESH_INTERVAL_MS = 10000

# Background: "color" | "image" | "video"
BACKGROUND_TYPE = "color"
BACKGROUND_COLOR = "#000000"
BACKGROUND_IMAGE_FILE = "img_background.jpg"
BACKGROUND_VIDEO_FILE = "video_background.mp4"

# Portfolio Table
TABLE_WIDGET_WIDTH = "800px"
TABLE_FONT_SIZE = "12px"
TABLE_BACKGROUND_COLOR = "rgba(0,0,0,0.75)"
TABLE_TEXT_DEFAULT_COLOR = "#FFFFFF"
TABLE_HEADER_TEXT_COLOR = "#FFFF00"
TABLE_BORDER_COLOR = "#333333"

# Clock Widget
CLOCK_DIGIT_WIDTH = "180px"
CLOCK_DIGIT_HEIGHT = "230px"
CLOCK_WIDGET_MARGIN_TOP = "40px"
```

All values injected into HTML via Jinja2. Clock polling (`15000ms`) is the only hardcoded JS value.

### 3.2 input.csv — Format

15 comma columns, UTF-8 with BOM.

```
Row 0–3:  Empty filler
Row 4:    Headers — "Price","My aver","Quantity","Invested","Current Cost","Return %","Return USD" at cols 1–7
Row 5+:   Positions — col0=ticker, col1=price, col2=avg cost, col3=quantity
          Examples: "USD Br",,1,1   or   "TQQQ",,70,1
Row N:    "Start ball" at col5 → next row col5 = starting balance
```

Parsing markers: `row[5]=='Start ball'`, `row[1]=='Price' and row[2]=='My aver'`, stop at `'History'` or `'Start'` in col0. Cash tickers contain USD/USDT/CASH (case-insensitive).

---

## PAGE 4 — FRONTEND: HTML, CSS, JAVASCRIPT

### 4.1 index.html (Jinja2 Template)

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Portfolio Dashboard</title>
    <link rel="stylesheet" href="/static/css/style.css">
    <style>
        body { background-color: {{ BACKGROUND_COLOR }}; }
        #widget-clock-container { margin-top: {{ CLOCK_WIDGET_MARGIN_TOP }}; }
        #widget-clock-container img { width: {{ CLOCK_DIGIT_WIDTH }}; height: {{ CLOCK_DIGIT_HEIGHT }}; }
        #widget-portfolio-container { width: {{ TABLE_WIDGET_WIDTH }}; background-color: {{ TABLE_BACKGROUND_COLOR }};
            font-size: {{ TABLE_FONT_SIZE }}; color: {{ TABLE_TEXT_DEFAULT_COLOR }}; }
        #widget-portfolio-table th { color: {{ TABLE_HEADER_TEXT_COLOR }}; }
        #widget-portfolio-table, td, th { border: 1px solid {{ TABLE_BORDER_COLOR }}; }
    </style>
</head>
<body>
    {% if BACKGROUND_TYPE == "image" %}
        <img src="/static/bg/{{ BACKGROUND_IMAGE_FILE }}" id="layout-backdrop" />
    {% elif BACKGROUND_TYPE == "video" %}
        <video autoplay loop muted playsinline id="layout-backdrop">
            <source src="/static/bg/{{ BACKGROUND_VIDEO_FILE }}" type="video/mp4">
        </video>
    {% endif %}

    <div id="dashboard-center-alignment-zone">
        <div id="widget-clock-container">
            {% if clock_error %}
                <div class="widget-error-fallback">[Widget Error: {{ clock_error }}]</div>
            {% else %}
                <img id="clk-h1" src="/static/digits/0.png" />
                <img id="clk-h2" src="/static/digits/0.png" />
                <img id="clk-colon" />
                <img id="clk-m1" src="/static/digits/0.png" />
                <img id="clk-m2" src="/static/digits/0.png" />
            {% endif %}
        </div>
        <br><br><br><br>
        <div id="widget-portfolio-container">
            {% if portfolio_error %}
                <div class="widget-error-fallback">[Widget Error: {{ portfolio_error }}]</div>
            {% else %}
                <div id="portfolio-data-mount">
                    <table id="widget-portfolio-table" cellpadding="6" cellspacing="0"><tr></table>
                    <div id="portfolio-summary-row"></div>
                </div>
            {% endif %}
        </div>
    </div>

    <script>var POLLING_INTERVAL_MS = {{ DATA_REFRESH_INTERVAL_MS }};</script>
    <script src="/static/js/dashboard.js"></script>
</body>
</html>
```

### 4.2 style.css — All Rules

| Selector | Properties |
|----------|------------|
| `html, body` | margin:0, padding:0, w/h:100%, overflow:hidden, font:Arial |
| `#layout-backdrop` | position:fixed, top/left:0, min-w/h:100%, z-index:-1 |
| `#dashboard-center-alignment-zone` | relative, w/h:100%, z-index:10, text-align:center, padding-top:5% |
| `#widget-portfolio-container` | inline-block, margin:0 auto, padding:20px |
| `#widget-portfolio-table` | width:100%, border-collapse:collapse, text-align:left |
| `#portfolio-summary-row` | margin-top:15px, text-align:left, font-weight:bold |
| `#widget-clock-container` | inline-block, margin:0 auto, text-align:center |
| `#widget-clock-container img` | inline-block, vertical-align:middle, margin:0 2px |
| `.widget-error-fallback` | color:#F00, bold, padding:20px, bg:#000, border:2px dashed #F00 |
| `.pnl-positive` | color:#00FF00 !important |
| `.pnl-negative` | color:#FF0000 !important |
| `.pnl-neutral` | color:#FFFFFF !important |
| `.offline-row td` | color:#888888 |

P&L classes use `!important` to override the `.offline-row td` grey — so P&L stays green/red even when a ticker is offline.

### 4.3 dashboard.js — Complete Logic

**State:**
```javascript
var POLLING_INTERVAL_MS = 10000;        // overridden by Jinja2
var CLOCK_POLLING_INTERVAL_MS = 15000;  // hardcoded, independent of portfolio
var colonVisible = true;
var currentClockMode = "night";
```

**`fetchServerTime()`** — XHR GET `/api/time` → parse → `updateClockImages(hours_str, minutes_str, clock_mode)`.

**`updateClockImages(hours_str, minutes_str, clock_mode)`** — Set each digit `<img>` src to `/static/digits/{mode}/{digit}.png`. Store colon paths as DOM properties, start visible.

**`blinkColon()`** — Toggle `colonVisible`, swap colon src between visible/blank PNG.

**`requestPortfolioDataUpdate()`** — XHR GET `/api/data` → on success/200 → `processInterfaceRender`. On error/parse fail → `switchToFallbackState()`.

**`processInterfaceRender(data)`**:
- Build table header: Ticker, Price, Avg Cost, Quantity, Current Value, Invested, P&L, P&L%.
- Per position: format numbers (2 dec, qty as int). `pos.online===false` → `<tr class="offline-row">`, else `<tr>`. Price shows "N/A" if `last_price==="N/A"`.
- P&L class: `pnl-positive` (green) / `pnl-negative` (red) / `pnl-neutral` (white) based on sign.
- Summary: "Total Balance: $X,XXX.XX".

**`switchToFallbackState()`** — No-op (keeps last rendered data). Logs to console.

**Intervals:**
```javascript
setInterval(blinkColon, 500);
setInterval(fetchServerTime, 15000);
setInterval(requestPortfolioDataUpdate, POLLING_INTERVAL_MS);
fetchServerTime();
requestPortfolioDataUpdate();
```

---

## PAGE 5 — ASSETS, DIRECTORY STRUCTURE & DEPLOYMENT

### 5.1 Directory Structure

```
desktop_widget/
├── app.py
├── config.py
├── input.csv                       # User-maintained portfolio
├── prices.db                       # Auto-created SQLite price cache
├── templates/
│   └── index.html
├── static/
│   ├── css/style.css
│   ├── js/dashboard.js
│   ├── bg/                         # User-provided backgrounds
│   │   ├── img_background.jpg
│   │   └── video_background.mp4
│   └── digits/
│       ├── day/   (0-9.png, colon.png, colon_blank.png)
│       └── night/ (0-9.png, colon.png, colon_blank.png)
```

### 5.2 Digital Assets

**24 clock PNGs** — 7-segment style, matching `CLOCK_DIGIT_WIDTH×HEIGHT`. `colon_blank.png` is fully transparent for the blink effect. Day mode: 06:00–20:59. Night mode: 21:00–05:59.

**Background** (optional): `img_background.jpg` or `video_background.mp4` (H.264 Base Profile, ≤720p).

### 5.3 Deployment

1. Install Python 3.x on Windows.
2. Copy all files to a directory.
3. Run `python app.py` — auto-installs Flask + requests if missing, auto-creates `prices.db`.
4. First launch: respond to "Override fallback prices?" prompt.
5. Browser → `http://127.0.0.1:5000` → F11 for fullscreen.
6. Auto-launch: shortcut to `.bat` in Windows Startup:
   ```batch
   @echo off
   cd /d "D:\path\to\desktop_widget"
   python app.py
   ```

### 5.4 Config Quick Reference

| Parameter | Default | Controls |
|-----------|---------|----------|
| `DAY_START/END` | 6:00 / 21:00 | Clock day/night mode switch times |
| `DATA_REFRESH_INTERVAL_MS` | 10000 | Portfolio AJAX polling (clock is separate: 15000) |
| `BACKGROUND_TYPE` | "color" | "color" / "image" / "video" |
| `BACKGROUND_COLOR` | "#000000" | CSS background (color mode) |
| `TABLE_WIDGET_WIDTH` | "800px" | Table container width |
| `TABLE_FONT_SIZE` | "12px" | Table text size |
| `TABLE_BACKGROUND_COLOR` | `rgba(0,0,0,0.75)` | Table background |
| `TABLE_TEXT_DEFAULT_COLOR` | "#FFFFFF" | Table body text |
| `TABLE_HEADER_TEXT_COLOR` | "#FFFF00" | Table header text |
| `TABLE_BORDER_COLOR` | "#333333" | Cell borders |
| `CLOCK_DIGIT_WIDTH/HEIGHT` | 180px / 230px | Digit image size |
| `CLOCK_WIDGET_MARGIN_TOP` | 40px | Clock vertical position |

### 5.5 Edge Cases

- **Missing CSV** → portfolio widget shows error message.
- **API fails for a ticker** → serves fallback from SQLite, text goes grey (`#888888`). P&L colors preserved.
- **API fails, no fallback** → "N/A", values zeroed, grey text.
- **API fails for ALL tickers** → all rows grey with last known prices. Table visible, no error badge.
- **Flask server down** (XHR fails) → last rendered table stays on screen unchanged.
- **Cash tickers** → price always 1.0, never call API, always white text.
- **Ticker removed from CSV** → `from_input=0`, not fetched, not displayed, prices preserved in DB.
- **Ticker re-added later** → `from_input=1`, old fallback prices restored from DB.
- **Short positions** (qty<0) → P&L formula inverted.
- **Zero avg_price** → P&L% = 0 (division guard).
- **Malformed CSV numbers** → `clean_numeric_value` returns 0.0.
- **Console persistence** → `input("Press ENTER...")` in finally block.

---

*Master prompt — matches actual codebase as of 2026-06-11.*
