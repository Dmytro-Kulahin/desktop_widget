# Desktop Widget

A fullscreen dashboard that turns an old laptop into a live clock and stock portfolio display. Served by a local Flask server with vanilla HTML/CSS/JS — no frameworks, no CDN, no cloud dependencies. Live prices are fetched from Yahoo Finance and cached to SQLite so your positions stay visible even when the API is unavailable. Configure everything in `config.py` and `input.csv`, then run `python app.py`.
