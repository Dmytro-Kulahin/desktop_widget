import os
import sys
import subprocess

# ==============================================================================
# LIBRARY DEPENDENCY CHECKER & AUTO-INSTALLER
# ==============================================================================
required_libraries = {
    'flask': 'Flask',
    'requests': 'requests'
}

missing_libraries = []

for import_name, pip_name in required_libraries.items():
    try:
        __import__(import_name)
        print("[OK] Library '" + import_name + "' is installed.")
    except ImportError:
        missing_libraries.append(pip_name)
        print("[MISSING] Library '" + import_name + "' is NOT installed.")

if missing_libraries:
    print("\n" + "=" * 50)
    print("INSTALLING MISSING LIBRARIES...")
    print("=" * 50)
    for lib in missing_libraries:
        print("Installing: " + lib)
        subprocess.check_call([sys.executable, "-m", "pip", "install", lib])
    print("=" * 50)
    print("ALL LIBRARIES INSTALLED. CONTINUING...")
    print("=" * 50 + "\n")

# Now import all required modules
import csv
import json
import requests
from datetime import datetime
from flask import Flask, render_template, jsonify

import config

# ==============================================================================
# FLASK APPLICATION INSTANCE (SINGLE-THREADED)
# ==============================================================================
app = Flask(__name__)

# ==============================================================================
# GLOBAL WIDGET STATE FLAGS (SET DURING STARTUP)
# ==============================================================================
portfolio_widget_ready = True
clock_widget_ready = True
portfolio_error_msg = ""
clock_error_msg = ""

# ==============================================================================
# HELPER PURE FUNCTION: CLEAN NUMERIC VALUES
# ==============================================================================
def clean_numeric_value(val):
    """Remove commas, spaces, currency symbols, return float or 0.0"""
    if val is None or str(val).strip() == "":
        return 0.0
    cleaned = str(val).strip()
    cleaned = cleaned.replace("$", "").replace(",", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

# ==============================================================================
# DECENTRALIZED STARTUP SELF-TESTS
# ==============================================================================
def run_startup_self_tests():
    global portfolio_widget_ready, portfolio_error_msg
    
    # TEST: Portfolio CSV file existence
    if not os.path.exists(config.CSV_PATH):
        portfolio_widget_ready = False
        portfolio_error_msg = "input.csv not found"
        print("[WIDGET ERROR - PORTFOLIO]: Input file 'input.csv' not found.")
    else:
        portfolio_widget_ready = True
        portfolio_error_msg = ""
    
    # Clock widget no longer has asset test - images are in day/night subfolders
    # Clock widget is always considered ready
    global clock_widget_ready, clock_error_msg
    clock_widget_ready = True
    clock_error_msg = ""

# ==============================================================================
# CSV PARSING ENGINE (LEGACY BACKWARD COMPATIBLE)
# ==============================================================================
def parse_csv_positions():
    """Extract positions and start_balance from input.csv"""
    positions = []
    start_balance = 0.0
    
    if not os.path.exists(config.CSV_PATH):
        return positions, start_balance
    
    with open(config.CSV_PATH, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)
    
    # Find "Start ball" balance marker
    for i, row in enumerate(rows):
        if len(row) >= 6 and row[5] == 'Start ball':
            if i + 1 < len(rows):
                balance_str = rows[i + 1][5].strip()
                start_balance = clean_numeric_value(balance_str)
            break
    
    # Find position table header
    header_index = -1
    for i, row in enumerate(rows):
        if len(row) > 2 and row[1] == 'Price' and row[2] == 'My aver':
            header_index = i + 1
            break
    
    if header_index == -1:
        return positions, start_balance
    
    # Parse positions sequentially
    for i in range(header_index, len(rows)):
        row = rows[i]
        
        # Break conditions
        if len(row) > 0:
            if row[0] == 'History' or row[0] == 'Start':
                break
            if len(row) > 1 and row[1] == 'Price':
                break
        
        if len(row) >= 4:
            ticker = row[0].strip()
            if ticker == "":
                continue
            
            csv_price = clean_numeric_value(row[1])
            avg_price = clean_numeric_value(row[2])
            quantity = clean_numeric_value(row[3])
            
            positions.append({
                "ticker": ticker,
                "csv_price": csv_price,
                "avg_price": avg_price,
                "quantity": quantity
            })
    
    return positions, start_balance

# ==============================================================================
# YAHOO FINANCE API INGESTION (LEGACY REST ENDPOINT)
# ==============================================================================
def fetch_yahoo_price(ticker):
    """Fetch live price from Yahoo Finance REST API. Returns (current_price, prev_close, success_flag)"""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + ticker
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.76 Safari/537.36'
    }
    params = {'range': '2d', 'interval': '1d'}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code != 200:
            return "N/A", "N/A", False
        
        data = response.json()
        
        # Primary extraction path: indicators quote close array
        try:
            closes = data['chart']['result'][0]['indicators']['quote'][0]['close']
            if closes and len(closes) >= 2:
                current_price = closes[-1]
                prev_close = closes[-2]
                if current_price is not None and prev_close is not None:
                    return float(current_price), float(prev_close), True
        except (KeyError, IndexError, TypeError):
            pass
        
        # Fallback extraction path: meta node
        try:
            meta = data['chart']['result'][0]['meta']
            current_price = float(meta['regularMarketPrice'])
            prev_close = float(meta['previousClose'])
            return current_price, prev_close, True
        except (KeyError, IndexError, TypeError, ValueError):
            pass
        
        return "N/A", "N/A", False
        
    except (requests.exceptions.RequestException, ValueError, KeyError, IndexError):
        return "N/A", "N/A", False

# ==============================================================================
# POSITION CALCULATION ENGINE (PURE FUNCTIONS)
# ==============================================================================
def is_cash_ticker(ticker):
    """Check if ticker represents cash (skip API calls)"""
    ticker_upper = ticker.upper()
    return any(x in ticker_upper for x in ['USD', 'USDT', 'CASH'])

def calculate_position(position, current_price, prev_close):
    """Calculate all financial metrics for a single position"""
    ticker = position['ticker']
    avg_price = position['avg_price']
    quantity = position['quantity']
    
    # Cash position handling
    if is_cash_ticker(ticker):
        last_price = 1.0
        current_value = position['csv_price'] * quantity
        invested_value = avg_price * quantity
        pnl = 0.0
        pnl_pct = 0.0
        return {
            "ticker": ticker,
            "last_price": last_price,
            "avg_price": avg_price,
            "quantity": quantity,
            "current_value": current_value,
            "invested_value": invested_value,
            "pnl": pnl,
            "pnl_pct": pnl_pct
        }, True
    
    # Stock/ETF position with valid price
    if current_price != "N/A" and isinstance(current_price, (int, float)):
        last_price = current_price
        current_value = current_price * quantity
        invested_value = avg_price * quantity
        
        if quantity < 0:  # Short position
            pnl = (avg_price - current_price) * abs(quantity)
            if avg_price != 0:
                pnl_pct = ((avg_price - current_price) / avg_price) * 100.0
            else:
                pnl_pct = 0.0
        else:  # Long position
            pnl = (current_price - avg_price) * quantity
            if avg_price != 0:
                pnl_pct = ((current_price - avg_price) / avg_price) * 100.0
            else:
                pnl_pct = 0.0
        
        return {
            "ticker": ticker,
            "last_price": last_price,
            "avg_price": avg_price,
            "quantity": quantity,
            "current_value": current_value,
            "invested_value": invested_value,
            "pnl": pnl,
            "pnl_pct": pnl_pct
        }, True
    else:
        # API failure fallback
        return {
            "ticker": ticker,
            "last_price": "N/A",
            "avg_price": avg_price,
            "quantity": quantity,
            "current_value": 0.0,
            "invested_value": 0.0,
            "pnl": 0.0,
            "pnl_pct": 0.0
        }, False

# ==============================================================================
# AGGREGATION AND TOTALS CALCULATION
# ==============================================================================
def calculate_totals(positions_data, start_balance):
    """Aggregate totals from all positions"""
    total_current_value = 0.0
    total_invested = 0.0
    total_pnl = 0.0
    
    # Weighted average P&L percentage calculation
    weighted_pnl_pct_sum = 0.0
    total_invested_for_pct = 0.0
    
    for pos in positions_data:
        total_current_value += pos['current_value']
        total_invested += pos['invested_value']
        total_pnl += pos['pnl']
        
        if pos['invested_value'] != 0 and pos['pnl_pct'] != 0:
            weighted_pnl_pct_sum += pos['pnl_pct'] * abs(pos['invested_value'])
            total_invested_for_pct += abs(pos['invested_value'])
    
    if total_invested_for_pct != 0:
        total_pnl_pct = weighted_pnl_pct_sum / total_invested_for_pct
    else:
        total_pnl_pct = 0.0
    
    # Calculate actual P&L from start balance
    actual_pnl_usd = total_current_value - start_balance
    if start_balance != 0:
        actual_pnl_pct = (actual_pnl_usd / start_balance) * 100.0
    else:
        actual_pnl_pct = 0.0
    
    return {
        "total_current_value": total_current_value,
        "total_invested": total_invested,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "start_balance": start_balance,
        "actual_pnl_usd": actual_pnl_usd,
        "actual_pnl_pct": actual_pnl_pct
    }

# ==============================================================================
# MAIN DATA COLLECTION PIPELINE
# ==============================================================================
def collect_portfolio_data():
    """Orchestrate full data collection: CSV parse -> API fetch -> Calculate -> Return JSON-ready dict"""
    # Parse CSV
    positions_raw, start_balance = parse_csv_positions()
    
    if not positions_raw:
        return {
            "network_status": "offline",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "widget_errors": {
                "portfolio": portfolio_error_msg,
                "clock": clock_error_msg
            },
            "totals": {
                "total_current_value": 0.0,
                "total_invested": 0.0,
                "total_pnl": 0.0,
                "total_pnl_pct": 0.0,
                "start_balance": start_balance,
                "actual_pnl_usd": 0.0,
                "actual_pnl_pct": 0.0
            },
            "positions": []
        }
    
    # Fetch prices and calculate positions
    positions_data = []
    network_online = True
    
    for pos in positions_raw:
        ticker = pos['ticker']
        
        if is_cash_ticker(ticker):
            # Cash position: skip API
            calculated, success = calculate_position(pos, 1.0, 1.0)
            positions_data.append(calculated)
        else:
            # Fetch from Yahoo
            current_price, prev_close, success = fetch_yahoo_price(ticker)
            if not success:
                network_online = False
                print("[API WARNING]: Failed to fetch live data for ticker " + ticker + ". Switching to fallback state.")
            calculated, _ = calculate_position(pos, current_price, prev_close)
            positions_data.append(calculated)
    
    # Calculate totals
    totals = calculate_totals(positions_data, start_balance)
    
    # Build final payload
    return {
        "network_status": "online" if network_online else "offline",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "widget_errors": {
            "portfolio": portfolio_error_msg,
            "clock": clock_error_msg
        },
        "totals": totals,
        "positions": positions_data
    }

# ==============================================================================
# FLASK ROUTES
# ==============================================================================
@app.route('/')
def index():
    """Main dashboard route - injects config and widget error states"""
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
                         portfolio_error=portfolio_error_msg if not portfolio_widget_ready else "",
                         clock_error=clock_error_msg if not clock_widget_ready else "")

@app.route('/api/data')
def api_data():
    """Real-time JSON data endpoint for AJAX polling"""
    data_payload = collect_portfolio_data()
    return jsonify(data_payload)

# ==============================================================================
# CLOCK TIME ENDPOINT (ADDED FOR STABLE TIME SYNC)
# ==============================================================================
@app.route('/api/time')
def get_server_time():
    """Return current server time and day/night mode for clock widget"""
    now = datetime.now()
    hours = now.hour
    minutes = now.minute
    
    # Format hours and minutes as two-digit strings
    hours_str = ("0" + str(hours)) if hours < 10 else str(hours)
    minutes_str = ("0" + str(minutes)) if minutes < 10 else str(minutes)
    
    # Determine if day or night mode using hours AND minutes
    # Convert current time to total minutes since midnight for easier comparison
    current_total_minutes = (hours * 60) + minutes
    day_start_total_minutes = (config.DAY_START_HOUR * 60) + config.DAY_START_MINUTE
    day_end_total_minutes = (config.DAY_END_HOUR * 60) + config.DAY_END_MINUTE
    
    if day_start_total_minutes <= current_total_minutes < day_end_total_minutes:
        clock_mode = "day"
    else:
        clock_mode = "night"
    
    print("[CLOCK DEBUG]: Server time is " + hours_str + ":" + minutes_str + " - mode: " + clock_mode)
    
    return jsonify({
        "hours": hours,
        "minutes": minutes,
        "hours_str": hours_str,
        "minutes_str": minutes_str,
        "clock_mode": clock_mode
    })

# ==============================================================================
# APPLICATION ENTRY POINT
# ==============================================================================
if __name__ == '__main__':
    try:
        # Run startup self-tests before booting server
        run_startup_self_tests()
        
        # Print startup confirmation
        print("=" * 50)
        print("PORTFOLIO DASHBOARD SERVER")
        print("=" * 50)
        print("Widget Status:")
        print("  - Portfolio Widget: " + ("READY" if portfolio_widget_ready else "FAILED"))
        print("  - Clock Widget: " + ("READY" if clock_widget_ready else "FAILED"))
        print("  - Background Type: " + config.BACKGROUND_TYPE)
        print("  - Polling Interval: " + str(config.DATA_REFRESH_INTERVAL_MS) + "ms")
        print("=" * 50)
        print("Starting Flask server on http://127.0.0.1:5000")
        print("Press CTRL+C to stop")
        print("=" * 50)
        
        # Single-threaded Flask server for Atom CPU
        # ==============================================================================
        app.run(host='0.0.0.0', port=5000, threaded=False, debug=False)
        
    except Exception as e:
        print("\n" + "=" * 50)
        print("FATAL ERROR:")
        print("=" * 50)
        print(str(e))
        print("=" * 50)
    
    finally:
        print("\n" + "=" * 50)
        input("Press ENTER to close this window...")
        print("=" * 50)