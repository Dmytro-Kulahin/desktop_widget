var POLLING_INTERVAL_MS = 10000;
var CLOCK_POLLING_INTERVAL_MS = 15000;
var colonVisible = true;
var currentClockMode = "night";

function fetchServerTime() {
    var xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/time", true);
    
    xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
            if (xhr.status === 200) {
                try {
                    var timeData = JSON.parse(xhr.responseText);
                    currentClockMode = timeData.clock_mode;
                    updateClockImages(timeData.hours_str, timeData.minutes_str, timeData.clock_mode);
                } catch (e) {
                    console.log("Failed to parse server time response");
                }
            } else {
                console.log("Failed to fetch server time - status: " + xhr.status);
            }
        }
    };
    
    xhr.onerror = function() {
        console.log("Network error fetching server time");
    };
    
    xhr.send();
}

function updateClockImages(hours_str, minutes_str, clock_mode) {
    var h1 = document.getElementById("clk-h1");
    var h2 = document.getElementById("clk-h2");
    var m1 = document.getElementById("clk-m1");
    var m2 = document.getElementById("clk-m2");
    var colon = document.getElementById("clk-colon");
    
    if (h1 && h2 && m1 && m2 && colon) {
        h1.src = "/static/digits/" + clock_mode + "/" + hours_str.charAt(0) + ".png";
        h2.src = "/static/digits/" + clock_mode + "/" + hours_str.charAt(1) + ".png";
        m1.src = "/static/digits/" + clock_mode + "/" + minutes_str.charAt(0) + ".png";
        m2.src = "/static/digits/" + clock_mode + "/" + minutes_str.charAt(1) + ".png";
        
        // Store colon paths for blinking
        colon.colonVisiblePath = "/static/digits/" + clock_mode + "/colon.png";
        colon.colonBlankPath = "/static/digits/" + clock_mode + "/colon_blank.png";
        
        // Start with visible colon
        colon.src = colon.colonVisiblePath;
        colonVisible = true;
    }
}

function blinkColon() {
    var colon = document.getElementById("clk-colon");
    if (colon && colon.colonVisiblePath && colon.colonBlankPath) {
        colonVisible = !colonVisible;
        if (colonVisible) {
            colon.src = colon.colonVisiblePath;
        } else {
            colon.src = colon.colonBlankPath;
        }
    }
}

function requestPortfolioDataUpdate() {
    var xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/data", true);
    
    xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
            if (xhr.status === 200) {
                try {
                    var payload = JSON.parse(xhr.responseText);
                    processInterfaceRender(payload);
                } catch (e) {
                    switchToFallbackState();
                }
            } else {
                switchToFallbackState();
            }
        }
    };
    
    xhr.onerror = function() {
        switchToFallbackState();
    };
    
    xhr.send();
}

function processInterfaceRender(data) {
    var indicator = document.getElementById("network-status-indicator");
    
    if (data.network_status === "offline") {
        if (indicator) indicator.style.display = "block";
    } else {
        if (indicator) indicator.style.display = "none";
    }
    
    var table = document.getElementById("widget-portfolio-table");
    var summary = document.getElementById("portfolio-summary-row");
    
    if (!table) return;
    
    var html = "<tr>" +
        "<th>Ticker</th>" +
        "<th>Price</th>" +
        "<th>Avg Cost</th>" +
        "<th>Quantity</th>" +
        "<th>Current Value</th>" +
        "<th>Invested</th>" +
        "<th>P&L</th>" +
        "<th>P&L%</th>" +
        "</tr>";
    
    for (var i = 0; i < data.positions.length; i++) {
        var pos = data.positions[i];
        
        var priceText = (pos.last_price === "N/A") ? "N/A" : Number(pos.last_price).toFixed(2);
        var avgText = Number(pos.avg_price).toFixed(2);
        var qtyText = Number(pos.quantity).toFixed(0);
        var valText = Number(pos.current_value).toFixed(2);
        var invText = Number(pos.invested_value).toFixed(2);
        var pnlText = Number(pos.pnl).toFixed(2);
        var pnlPctText = Number(pos.pnl_pct).toFixed(2) + "%";
        
        var pnlClass = "pnl-neutral";
        if (pos.pnl > 0) pnlClass = "pnl-positive";
        else if (pos.pnl < 0) pnlClass = "pnl-negative";
        
        html += "<tr>" +
            "<td>" + pos.ticker + "</td>" +
            "<td>" + priceText + "</td>" +
            "<td>" + avgText + "</td>" +
            "<td>" + qtyText + "</td>" +
            "<td>" + valText + "</td>" +
            "<td>" + invText + "</td>" +
            "<td class='" + pnlClass + "'>" + pnlText + "</td>" +
            "<td class='" + pnlClass + "'>" + pnlPctText + "</td>" +
            "</tr>";
    }
    
    table.innerHTML = html;
    
    if (summary) {
        var t = data.totals;
        summary.innerHTML = "Total Balance: $" + Number(t.total_current_value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
}

function switchToFallbackState() {
    var indicator = document.getElementById("network-status-indicator");
    if (indicator) indicator.style.display = "block";
    
    var table = document.getElementById("widget-portfolio-table");
    if (!table) return;
    
    var rows = table.getElementsByTagName("tr");
    for (var i = 1; i < rows.length; i++) {
        var cells = rows[i].getElementsByTagName("td");
        if (cells.length >= 8) {
            cells[1].innerHTML = "N/A";
            cells[4].innerHTML = "0.00";
            cells[6].innerHTML = "0.00";
            cells[7].innerHTML = "0.00%";
            cells[6].className = "pnl-neutral";
            cells[7].className = "pnl-neutral";
        }
    }
}

// Blinking colon: toggle between colon.png and colon_blank.png every 500ms
setInterval(blinkColon, 500);

// Clock: poll server every 15 seconds for accurate time
setInterval(fetchServerTime, CLOCK_POLLING_INTERVAL_MS);

// Portfolio: poll server every 10 seconds for data
setInterval(requestPortfolioDataUpdate, POLLING_INTERVAL_MS);

// Initial calls on page load
fetchServerTime();
requestPortfolioDataUpdate();