import os
import sys
import subprocess

# Auto-install missing dependencies
required_libraries = {
    'flask': 'Flask',
    'requests': 'requests'
}

missing_libraries = []
for import_name, pip_name in required_libraries.items():
    try:
        __import__(import_name)
        print(f"[OK] Library '{import_name}' is installed.")
    except ImportError:
        missing_libraries.append(pip_name)
        print(f"[MISSING] Library '{import_name}' is NOT installed.")

if missing_libraries:
    print(f"\n{'=' * 50}\nINSTALLING MISSING LIBRARIES...\n{'=' * 50}")
    for lib in missing_libraries:
        print(f"Installing: {lib}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", lib])
    print(f"{'=' * 50}\nALL LIBRARIES INSTALLED. CONTINUING...\n{'=' * 50}\n")

import csv
import json
import sqlite3
import requests
from contextlib import contextmanager
from datetime import datetime
from flask import Flask, render_template, jsonify

import config

# Flask app instance
app = Flask(__name__)

# Widget state — set once at startup, read-only thereafter
_portfolio_ready = True
_portfolio_error = ""
_clock_ready = True
_clock_error = ""

# Yahoo Finance API constants
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"
YAHOO_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/56.0.2924.76 Safari/537.36')
}
YAHOO_PARAMS = {'range': '2d', 'interval': '1d'}

# CSV column indices
COL_TICKER, COL_PRICE, COL_AVG, COL_QTY, COL_START_BALL = 0, 1, 2, 3, 5


@contextmanager
def get_db():
    """Context manager for SQLite connections — guarantees close."""
    conn = sqlite3.connect(config.DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def clean_numeric_value(val):
    """Strip currency symbols, commas, spaces; return float or 0.0."""
    if val is None or str(val).strip() == "":
        return 0.0
    cleaned = str(val).strip().replace("$", "").replace(",", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def is_cash_ticker(ticker):
    """Return True if ticker is a cash/stablecoin (skip API calls)."""
    ticker_upper = ticker.upper()
    return any(x in ticker_upper for x in ['USD', 'USDT', 'CASH'])


# ── Startup self-tests ──────────────────────────────────────────────────────

def run_startup_self_tests():
    """Verify prerequisites. Returns (portfolio_ready: bool, error_msg: str)."""
    if not os.path.exists(config.CSV_PATH):
        return False, "input.csv not found"
    return True, ""


# ── CSV parser ──────────────────────────────────────────────────────────────

def parse_csv_positions():
    """Extract positions and start_balance from input.csv."""
    positions = []
    start_balance = 0.0

    if not os.path.exists(config.CSV_PATH):
        return positions, start_balance

    with open(config.CSV_PATH, 'r', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))

    # Locate start balance marker
    for i, row in enumerate(rows):
        if len(row) >= 6 and row[COL_START_BALL] == 'Start ball':
            if i + 1 < len(rows):
                start_balance = clean_numeric_value(rows[i + 1][COL_START_BALL])
            break

    # Locate position table header
    header_index = -1
    for i, row in enumerate(rows):
        if len(row) > 2 and row[COL_PRICE] == 'Price' and row[COL_AVG] == 'My aver':
            header_index = i + 1
            break

    if header_index == -1:
        return positions, start_balance

    # Parse position rows
    for i in range(header_index, len(rows)):
        row = rows[i]
        if len(row) > 0:
            if row[0] in ('History', 'Start'):
                break
            if len(row) > 1 and row[1] == 'Price':
                break

        if len(row) >= 4:
            ticker = row[COL_TICKER].strip()
            if ticker == "":
                continue
            positions.append({
                "ticker": ticker,
                "csv_price": clean_numeric_value(row[COL_PRICE]),
                "avg_price": clean_numeric_value(row[COL_AVG]),
                "quantity": clean_numeric_value(row[COL_QTY])
            })

    return positions, start_balance


# ── Yahoo Finance API ───────────────────────────────────────────────────────

def fetch_yahoo_price(ticker):
    """Fetch live price from Yahoo Finance.
    Returns (current_price, prev_close, success_flag)."""
    url = YAHOO_CHART_URL + ticker

    try:
        response = requests.get(url, headers=YAHOO_HEADERS, params=YAHOO_PARAMS, timeout=10)
        if response.status_code != 200:
            return "N/A", "N/A", False

        data = response.json()

        # Path A: indicators.quote[0].close array
        try:
            closes = data['chart']['result'][0]['indicators']['quote'][0]['close']
            if closes and len(closes) >= 2:
                current_price = closes[-1]
                prev_close = closes[-2]
                if current_price is not None and prev_close is not None:
                    return float(current_price), float(prev_close), True
        except (KeyError, IndexError, TypeError):
            pass

        # Path B: meta node
        try:
            meta = data['chart']['result'][0]['meta']
            return float(meta['regularMarketPrice']), float(meta['previousClose']), True
        except (KeyError, IndexError, TypeError, ValueError):
            pass

        return "N/A", "N/A", False

    except (requests.exceptions.RequestException, ValueError, KeyError, IndexError):
        return "N/A", "N/A", False


# ── SQLite price cache ──────────────────────────────────────────────────────

def init_db():
    """Create prices table if it does not exist (one-time init)."""
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS prices (
            ticker TEXT PRIMARY KEY,
            current_price REAL,
            fallback_price REAL,
            from_input INTEGER DEFAULT 0
        )''')
        conn.commit()


def sync_db_from_csv(conn, positions):
    """Reset from_input flags, upsert tickers from parsed CSV."""
    c = conn.cursor()
    c.execute("UPDATE prices SET from_input = 0")
    for pos in positions:
        ticker = pos['ticker']
        if is_cash_ticker(ticker):
            c.execute('''INSERT OR REPLACE INTO prices (ticker, current_price, fallback_price, from_input)
                         VALUES (?, 1.0, 1.0, 1)''', (ticker,))
        else:
            c.execute('''INSERT OR IGNORE INTO prices (ticker, current_price, fallback_price, from_input)
                         VALUES (?, 0.0, 0.0, 1)''', (ticker,))
            c.execute("UPDATE prices SET from_input = 1 WHERE ticker = ?", (ticker,))
    conn.commit()


def prompt_fallback_overrides(conn):
    """Interactive prompt to override fallback prices for non-cash tickers.
    Degrades gracefully when stdin is unavailable (e.g. background launch)."""
    c = conn.cursor()
    c.execute("SELECT ticker, fallback_price FROM prices WHERE from_input = 1")
    rows = c.fetchall()

    non_cash = [(t, p) for t, p in rows if not is_cash_ticker(t)]
    if not non_cash:
        return

    try:
        answer = input("\nOverride fallback prices? (y/n): ").strip().lower()
    except (EOFError, OSError):
        print("(skipping — no interactive input available)")
        return

    if answer != 'y':
        return

    c = conn.cursor()
    for ticker, current_fallback in non_cash:
        prompt_text = f"{ticker} [fallback: {current_fallback}] Enter new price (Enter to keep): "
        try:
            user_input = input(prompt_text).strip()
        except (EOFError, OSError):
            print("(skipping remaining overrides — input unavailable)")
            break
        if user_input:
            try:
                new_price = float(user_input)
                c.execute('''UPDATE prices SET current_price = ?, fallback_price = ?
                             WHERE ticker = ?''', (new_price, new_price, ticker))
            except ValueError:
                print("  Invalid number, keeping existing.")
    conn.commit()


def rotate_db_price(conn, ticker, new_price):
    """Shift current_price → fallback_price, write new API price."""
    conn.execute('''UPDATE prices
                    SET fallback_price = current_price, current_price = ?
                    WHERE ticker = ?''', (new_price, ticker))
    conn.commit()


def get_fallback_price(conn, ticker):
    """Return fallback_price from DB, or None if ticker not found."""
    c = conn.cursor()
    c.execute("SELECT fallback_price FROM prices WHERE ticker = ?", (ticker,))
    row = c.fetchone()
    return row[0] if row else None


# ── Position calculations ───────────────────────────────────────────────────

def _pos_dict(ticker, last_price, avg_price, quantity,
              current_value, invested_value, pnl, pnl_pct):
    """Build position result dict — single source of truth for output shape."""
    return {
        "ticker": ticker,
        "last_price": last_price,
        "avg_price": avg_price,
        "quantity": quantity,
        "current_value": current_value,
        "invested_value": invested_value,
        "pnl": pnl,
        "pnl_pct": pnl_pct
    }


def calculate_position(position, current_price, prev_close):
    """Compute financial metrics for one position.
    Returns (result_dict, success_bool)."""
    ticker = position['ticker']
    avg = position['avg_price']
    qty = position['quantity']

    # Cash position
    if is_cash_ticker(ticker):
        return _pos_dict(ticker, 1.0, avg, qty,
                         position['csv_price'] * qty, avg * qty,
                         0.0, 0.0), True

    # API failure — no usable price
    if current_price == "N/A" or not isinstance(current_price, (int, float)):
        return _pos_dict(ticker, "N/A", avg, qty, 0.0, 0.0, 0.0, 0.0), False

    # Live position (long or short)
    current_value = current_price * qty
    invested_value = avg * qty

    if qty < 0:
        # Short position — profit when price drops below average
        pnl = (avg - current_price) * abs(qty)
        pnl_pct = ((avg - current_price) / avg) * 100.0 if avg != 0 else 0.0
    else:
        # Long position — profit when price rises above average
        pnl = (current_price - avg) * qty
        pnl_pct = ((current_price - avg) / avg) * 100.0 if avg != 0 else 0.0

    return _pos_dict(ticker, current_price, avg, qty,
                     current_value, invested_value, pnl, pnl_pct), True


def calculate_totals(positions_data, start_balance):
    """Aggregate totals across all positions with weighted-average P&L%."""
    total_current_value = sum(p['current_value'] for p in positions_data)
    total_invested = sum(p['invested_value'] for p in positions_data)
    total_pnl = sum(p['pnl'] for p in positions_data)

    # Weighted-average P&L percentage
    weighted_sum = 0.0
    weight_total = 0.0
    for pos in positions_data:
        if pos['invested_value'] != 0 and pos['pnl_pct'] != 0:
            weighted_sum += pos['pnl_pct'] * abs(pos['invested_value'])
            weight_total += abs(pos['invested_value'])

    total_pnl_pct = weighted_sum / weight_total if weight_total != 0 else 0.0

    # Actual P&L vs start balance
    actual_pnl_usd = total_current_value - start_balance
    actual_pnl_pct = (actual_pnl_usd / start_balance) * 100.0 if start_balance != 0 else 0.0

    return {
        "total_current_value": total_current_value,
        "total_invested": total_invested,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "start_balance": start_balance,
        "actual_pnl_usd": actual_pnl_usd,
        "actual_pnl_pct": actual_pnl_pct
    }


# ── Data pipeline ───────────────────────────────────────────────────────────

def _process_position(conn, pos):
    """Fetch price (API or cache) and calculate one position.
    Returns position dict with 'online' flag set."""
    ticker = pos['ticker']

    if is_cash_ticker(ticker):
        calculated, _ = calculate_position(pos, 1.0, 1.0)
        calculated['online'] = True
        return calculated

    current_price, prev_close, api_ok = fetch_yahoo_price(ticker)
    if api_ok:
        rotate_db_price(conn, ticker, current_price)
        calculated, _ = calculate_position(pos, current_price, prev_close)
        calculated['online'] = True
        return calculated

    print(f"[API WARNING]: No live data for {ticker}, using fallback price.")
    fallback = get_fallback_price(conn, ticker)
    if fallback is not None and fallback != 0.0:
        calculated, _ = calculate_position(pos, fallback, fallback)
    else:
        calculated, _ = calculate_position(pos, "N/A", "N/A")
    calculated['online'] = False
    return calculated


def _empty_payload(start_balance):
    """Payload returned when CSV is empty or missing."""
    return {
        "network_status": "offline",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "widget_errors": {"portfolio": _portfolio_error, "clock": _clock_error},
        "totals": {
            "total_current_value": 0.0, "total_invested": 0.0,
            "total_pnl": 0.0, "total_pnl_pct": 0.0,
            "start_balance": start_balance,
            "actual_pnl_usd": 0.0, "actual_pnl_pct": 0.0
        },
        "positions": []
    }


def _build_payload(network_online, totals, positions_data):
    """Assemble the final JSON-ready portfolio payload."""
    return {
        "network_status": "online" if network_online else "offline",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "widget_errors": {"portfolio": _portfolio_error, "clock": _clock_error},
        "totals": totals,
        "positions": positions_data
    }


def collect_portfolio_data():
    """Orchestrate full data pipeline: CSV → API → cache → calculate → JSON."""
    positions_raw, start_balance = parse_csv_positions()

    if not positions_raw:
        return _empty_payload(start_balance)

    with get_db() as conn:
        sync_db_from_csv(conn, positions_raw)
        positions_data = [_process_position(conn, p) for p in positions_raw]

    network_online = all(p.get('online', False) for p in positions_data)
    totals = calculate_totals(positions_data, start_balance)
    return _build_payload(network_online, totals, positions_data)


# ── Flask routes ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Main dashboard — injects config and widget error states via Jinja2."""
    return render_template('index.html',
                           BACKGROUND_TYPE=config.BACKGROUND_TYPE,
                           BACKGROUND_COLOR=config.BACKGROUND_COLOR,
                           BACKGROUND_IMAGE_FILE=config.BACKGROUND_IMAGE_FILE,
                           BACKGROUND_VIDEO_FILE=config.BACKGROUND_VIDEO_FILE,
                           TABLE_WIDGET_WIDTH=config.TABLE_WIDGET_WIDTH,
                           TABLE_FONT_SIZE=config.TABLE_FONT_SIZE,
                           TABLE_BACKGROUND_COLOR=config.TABLE_BACKGROUND_COLOR,
                           TABLE_TEXT_DEFAULT_COLOR=config.TABLE_TEXT_DEFAULT_COLOR,
                           TABLE_HEADER_TEXT_COLOR=config.TABLE_HEADER_TEXT_COLOR,
                           TABLE_BORDER_COLOR=config.TABLE_BORDER_COLOR,
                           CLOCK_DIGIT_WIDTH=config.CLOCK_DIGIT_WIDTH,
                           CLOCK_DIGIT_HEIGHT=config.CLOCK_DIGIT_HEIGHT,
                           CLOCK_WIDGET_MARGIN_TOP=config.CLOCK_WIDGET_MARGIN_TOP,
                           DATA_REFRESH_INTERVAL_MS=config.DATA_REFRESH_INTERVAL_MS,
                           portfolio_error=_portfolio_error if not _portfolio_ready else "",
                           clock_error=_clock_error if not _clock_ready else "")


@app.route('/api/data')
def api_data():
    """Portfolio JSON endpoint polled by frontend."""
    return jsonify(collect_portfolio_data())


@app.route('/api/ping')
def ping():
    """Lightweight heartbeat for frontend server-down detection."""
    return jsonify({"status": "ok"})


@app.route('/api/time')
def get_server_time():
    """Return server time and day/night mode for the clock widget."""
    now = datetime.now()
    hours, minutes = now.hour, now.minute

    hours_str = f"0{hours}" if hours < 10 else str(hours)
    minutes_str = f"0{minutes}" if minutes < 10 else str(minutes)

    # Day/night mode from config thresholds
    current_minutes = hours * 60 + minutes
    day_start = config.DAY_START_HOUR * 60 + config.DAY_START_MINUTE
    day_end = config.DAY_END_HOUR * 60 + config.DAY_END_MINUTE

    clock_mode = "day" if day_start <= current_minutes < day_end else "night"

    print(f"[CLOCK DEBUG]: Server time is {hours_str}:{minutes_str} - mode: {clock_mode}")

    return jsonify({
        "hours": hours,
        "minutes": minutes,
        "hours_str": hours_str,
        "minutes_str": minutes_str,
        "clock_mode": clock_mode
    })


# ── Entry point ─────────────────────────────────────────────────────────────

def _seed_cache():
    """Populate DB from CSV on first run; optionally prompt for overrides."""
    positions_init, _ = parse_csv_positions()
    if positions_init:
        with get_db() as conn:
            sync_db_from_csv(conn, positions_init)
            prompt_fallback_overrides(conn)


def _print_banner(portfolio_ready, portfolio_error):
    """Print startup status banner."""
    print("=" * 50)
    print("PORTFOLIO DASHBOARD SERVER")
    print("=" * 50)
    print("Widget Status:")
    print(f"  - Portfolio Widget: {'READY' if portfolio_ready else 'FAILED'}")
    if not portfolio_ready:
        print(f"    ({portfolio_error})")
    print("  - Clock Widget: READY")
    print(f"  - Background Type: {config.BACKGROUND_TYPE}")
    print(f"  - Polling Interval: {config.DATA_REFRESH_INTERVAL_MS}ms")
    print("=" * 50)
    print("Starting Flask server on http://127.0.0.1:5000")
    print("Press CTRL+C to stop")
    print("=" * 50)


def _api_smoke_test():
    """Pre-flight check: can we reach Yahoo Finance?"""
    print("Running API smoke test (SPY)...")
    price, _, ok = fetch_yahoo_price("SPY")
    if ok:
        print(f"[OK] Yahoo Finance reachable. SPY = {price}")
    else:
        print("[WARN] Yahoo Finance unreachable — all tickers will use fallback prices.")
    return ok


if __name__ == '__main__':
    try:
        _portfolio_ready, _portfolio_error = run_startup_self_tests()
        init_db()
        _seed_cache()
        _api_smoke_test()
        _print_banner(_portfolio_ready, _portfolio_error)

        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)

    except Exception as e:
        print(f"\n{'=' * 50}\nFATAL ERROR:\n{'=' * 50}\n{e}\n{'=' * 50}")

    finally:
        print(f"\n{'=' * 50}")
        try:
            input("Press ENTER to close this window...")
        except (EOFError, OSError):
            pass
        print("=" * 50)
