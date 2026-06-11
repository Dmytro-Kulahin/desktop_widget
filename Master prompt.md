# Desktop Widget — Master Prompt

> Fullscreen desktop dashboard for a legacy Windows laptop. Two widgets: 7-segment digital clock (day/night PNG themes) and live stock portfolio table with SQLite-backed price caching. Flask backend, vanilla frontend.

---

## 1. Architecture

```
Flask (single-threaded, host=0.0.0.0:5000, threaded=False)
  ├── GET /            → Jinja2 dashboard (all config.* injected as CSS vars)
  ├── GET /api/data    → Portfolio JSON (polled at DATA_REFRESH_INTERVAL_MS)
  ├── GET /api/time    → Server time + day/night mode (clock polls at 15s)
  └── GET /api/ping    → Heartbeat (frontend shows overlay if server unreachable)
```

**Data pipeline per poll cycle:**
```
parse_csv_positions()
  → with get_db() as conn:                    # one connection per cycle
      sync_db_from_csv(conn, positions)        # upsert tickers, set from_input=1
      [_process_position(conn, p) per ticker]:
        Cash  → calculate with price=1.0, online=True
        Stock → fetch_yahoo_price() →
          success → rotate_db_price(conn), calculate live, online=True
          failure → get_fallback_price(conn), calculate cached, online=False
  → calculate_totals() → _build_payload() → JSON
```

**Key design choices:**
- All DB functions take `conn` as parameter — `@contextmanager get_db()` owns lifecycle
- Single `_pos_dict()` builder is the one source of truth for position output shape
- `calculate_position` is pure (no I/O); DB writes isolated in `_process_position`
- Widget state set once at module level on startup; no `global` keyword anywhere
- Yahoo API constants and CSV column indices are named module-level constants
- API smoke test at boot (`fetch_yahoo_price("SPY")`)
- All `input()` calls wrapped in `except (EOFError, OSError)` for non-interactive mode

---

## 2. Backend: app.py (~340 lines)

### Startup sequence
```
run_startup_self_tests() → (ready: bool, error: str)
init_db() → CREATE TABLE IF NOT EXISTS prices
_seed_cache() → parse CSV → sync DB → prompt_fallback_overrides (graceful)
_api_smoke_test() → fetch SPY to verify Yahoo reachable
_print_banner() → console status
app.run(host='0.0.0.0', port=5000, threaded=False, debug=False)
```

### SQLite cache (prices.db, auto-created)

| Column | Purpose |
|--------|---------|
| `ticker` TEXT PK | Symbol |
| `current_price` REAL | Latest API price |
| `fallback_price` REAL | Previous price — served when API fails |
| `from_input` INT | 1 = ticker present in current CSV |

**DB functions** (all receive `conn`, all commit internally):

| Function | What it does |
|----------|-------------|
| `sync_db_from_csv(conn, positions)` | Reset all `from_input=0`, upsert CSV tickers with `from_input=1`. Cash tickers get prices locked at 1.0 |
| `rotate_db_price(conn, ticker, price)` | `fallback ← current`, `current ← price` |
| `get_fallback_price(conn, ticker)` | Return `fallback_price` or `None` |
| `prompt_fallback_overrides(conn)` | Interactive fallback entry; skips gracefully without stdin |

### Core functions

**`fetch_yahoo_price(ticker)`** → `(current, prev_close, success_flag)`  
Chart API `v8/finance/chart/{ticker}`. Range 2d, interval 1d, timeout 10s. Two extraction paths: indicators quote close array (Path A), then meta node (Path B). Rate limit ~100 req/min, no auth.

**`calculate_position(position, current_price, prev_close)`** → `(dict, success_bool)`  
Pure function. Cash (USD/USDT/CASH): price=1.0, P&L=0. API failure ("N/A"): zeros. Long: P&L=(current-avg)×qty. Short: P&L=(avg-current)×|qty|. Guard: avg=0 → P&L%=0. Output always 9 keys via `_pos_dict()`.

**`calculate_totals(positions_data, start_balance)`**  
Weighted-average P&L% + actual P&L vs start balance.

**`collect_portfolio_data()`** — main pipeline, composes: `parse → sync → [_process_position per ticker] → all(online) → totals → JSON`.

### `/api/time` day/night logic
Convert to minutes since midnight. `DAY_START ≤ current < DAY_END` → `"day"`, else `"night"`. Default: 6:00–20:59 day, 21:00–5:59 night.

### JSON payload
```json
{
  "network_status": "online"|"offline",
  "timestamp": "YYYY-MM-DD HH:MM:SS",
  "widget_errors": {"portfolio": "...", "clock": "..."},
  "totals": {"total_current_value", "total_invested", "total_pnl",
             "total_pnl_pct", "start_balance", "actual_pnl_usd", "actual_pnl_pct"},
  "positions": [{"ticker","last_price","avg_price","quantity",
                 "current_value","invested_value","pnl","pnl_pct","online"}]
}
```

---

## 3. config.py — All user settings

| Setting | Default | Controls |
|---------|---------|----------|
| `CSV_PATH` / `DB_PATH` | `input.csv` / `prices.db` | Data files |
| `DAY_START/END` | 6:00 / 21:00 (24h) | Clock theme switch |
| `DATA_REFRESH_INTERVAL_MS` | 30000 | Portfolio polling |
| `BACKGROUND_TYPE` | `"color"` | `"color"` / `"image"` / `"video"` |
| `BACKGROUND_COLOR` | `"#000000"` | CSS background |
| `TABLE_WIDGET_WIDTH` | `"800px"` | Table container |
| `TABLE_FONT_SIZE` | `"12px"` | Table text |
| `TABLE_BACKGROUND_COLOR` | `rgba(0,0,0,0.75)` | Table background |
| `TABLE_TEXT_DEFAULT_COLOR` | `"#FFFFFF"` | Body text |
| `TABLE_HEADER_TEXT_COLOR` | `"#FFFF00"` | Header text |
| `TABLE_BORDER_COLOR` | `"#333333"` | Cell borders |
| `CLOCK_DIGIT_WIDTH/HEIGHT` | `"180px"` / `"230px"` | Digit images |
| `CLOCK_WIDGET_MARGIN_TOP` | `"40px"` | Clock position |

Video mode: H.264 Base Profile, ≤720p — mandatory for legacy CPU.

---

## 4. input.csv format

UTF-8 with BOM. Heuristic structure:
- Rows 0–3: empty filler
- Row 4: `,Price,My aver,Quantity,...` (header)
- Rows 5+: `TICKER,price,avg_cost,quantity,...` (positions)
- Marker: `row[5]=='Start ball'` → next row[5] = starting balance
- Stop signals: `row[0]` is `'History'` or `'Start'`, or `row[1]=='Price'`
- Cash tickers: contain USD/USDT/CASH (case-insensitive, price always 1.0)

Parser extracts 4 columns: ticker[0], price[1], avg_cost[2], quantity[3], start_balance[5].

---

## 5. Frontend — vanilla HTML/CSS/JS, no frameworks, no CDN

### index.html (Jinja2 template)
All config values injected as `{{ VAR }}` inline CSS. Backdrop: color-only, `<img>`, or `<video>` based on `BACKGROUND_TYPE`. Clock: 5 `<img>` tags (4 digits + colon). Portfolio: empty `<table>` + `<div>`, populated by JS. Hidden server-down overlay (fullscreen black + warning).

### dashboard.js — Four polling loops

| Loop | Rate | Action |
|------|------|--------|
| `blinkColon` | 500ms | Toggle colon visible/blank PNG |
| `fetchServerTime` | 15s (hardcoded) | `/api/time` → update digit src to `/static/digits/{mode}/{digit}.png` |
| `requestPortfolioDataUpdate` | `POLLING_INTERVAL_MS` | `/api/data` → rebuild table HTML |
| `checkServerHeartbeat` | 5s | `/api/ping` → show/hide server-down overlay |

**`processInterfaceRender(data)`**: builds 8-column table (Ticker, Price, Avg Cost, Qty, Value, Invested, P&L, P&L%). CSS classes: `.pnl-positive` (green), `.pnl-negative` (red), `.pnl-neutral` (white) based on P&L sign; `.offline-row` (grey `#888888`) when `online=false`. P&L classes use `!important` to override offline grey. Summary row: `Total Balance: $X,XXX.XX`.

**Heartbeat**: on failure → fullscreen overlay at `z-index:99999`. On recovery → re-fetches both portfolio and time. All fetch failures → `switchToFallbackState()` (no-op, keeps last rendered data).

---

## 6. Directory structure

```
desktop_widget/
├── app.py                    # Flask backend
├── config.py                 # User settings
├── input.csv                 # Portfolio (user-maintained)
├── prices.db                 # SQLite cache (auto-created)
├── templates/index.html      # Jinja2 dashboard
└── static/
    ├── css/style.css
    ├── js/dashboard.js
    ├── bg/                   # Optional: img_background.jpg, video_background.mp4
    └── digits/
        ├── day/              # 0-9.png, colon.png, colon_blank.png
        └── night/            # same set, dark theme
```

---

## 7. Edge cases

| Scenario | Result |
|----------|--------|
| CSV missing | Portfolio widget shows error; `/api/data` returns empty payload |
| API success | Live price, white text, `online=True` |
| API fails, fallback exists | Cached price, grey text (`#888888`), P&L colors preserved |
| API fails, no fallback | `"N/A"`, values zeroed, grey |
| All tickers fail | All rows grey with last-known prices; no error badge |
| Flask server down | Last rendered table frozen; heartbeat overlay after 5s |
| Cash tickers | Price=1.0, never call API, always white |
| Ticker removed from CSV | `from_input=0`, not fetched, price kept in DB |
| Short positions (qty<0) | P&L inverted — profit when price drops |
| Avg=0 | P&L% = 0 (division guard) |
| Non-interactive launch | `input()` calls silently skipped |
| Malformed numbers | `clean_numeric_value()` returns 0.0 |
| Legacy hardware | Single-threaded Flask, constrained video codec, no heavy JS |

---

*Matches codebase as of refactored architecture (2026-06-11).*
