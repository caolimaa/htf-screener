import yfinance as yf
import pandas as pd
import requests
import json
from datetime import datetime

# --- Fetch tickers from NASDAQ, NYSE, NYSE Arca ---
def get_tickers():
    urls = {
        "NASDAQ": "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/nasdaq/nasdaq_tickers.txt",
        "NYSE": "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/nyse/nyse_tickers.txt",
        "NYSE Arca": "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/nyse/nyse_tickers.txt",
    }
    tickers = set()
    for exchange, url in urls.items():
        try:
            r = requests.get(url, timeout=10)
            for line in r.text.strip().split("\n"):
                t = line.strip()
                if t:
                    tickers.add(t)
        except:
            pass
    return list(tickers)

def compute_adr(high, low, n=20):
    if len(high) < n or len(low) < n:
        return 0
    avg_high = high[-n:].mean()
    avg_low = low[-n:].mean()
    if avg_low == 0:
        return 0
    return ((avg_high - avg_low) / avg_low) * 100

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def sma(series, period):
    return series.rolling(window=period).mean()

def screen_ticker(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Exchange filter
        exchange = info.get("exchange", "")
        valid_exchanges = ["NMS", "NYQ", "PCX", "NGM", "NCM"]  # NASDAQ, NYSE, NYSE Arca equivalents
        if exchange not in valid_exchanges:
            return None

        # Market cap filter >= $300M
        mktcap = info.get("marketCap", 0) or 0
        if mktcap < 300_000_000:
            return None

        # Price filter >= $3
        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        if price < 3:
            return None

        # Historical data (need ~210 days for SMA200)
        hist = stock.history(period="1y")
        if hist.empty or len(hist) < 50:
            return None

        close = hist["Close"]
        high  = hist["High"]
        low   = hist["Low"]
        vol   = hist["Volume"]

        latest_close = close.iloc[-1]
        latest_vol   = vol.iloc[-1]

        # Price * Volume > $20M
        if latest_close * latest_vol < 20_000_000:
            return None

        # ADR > 4%
        adr = compute_adr(high.values, low.values, n=20)
        if adr <= 4:
            return None

        # Moving averages
        e13  = ema(close, 13).iloc[-1]
        e21  = ema(close, 21).iloc[-1]
        e50  = ema(close, 50).iloc[-1]
        s150 = sma(close, 150).iloc[-1]
        s200 = sma(close, 200).iloc[-1]

        # MA filters
        if not (latest_close > e13): return None
        if not (latest_close > e21): return None
        if not (latest_close > e50): return None
        if not (latest_close > s150): return None
        if not (latest_close > s200): return None
        if not (e13 > e21): return None

        name = info.get("shortName", ticker)
        sector = info.get("sector", "N/A")

        return {
            "Ticker": ticker,
            "Name": name,
            "Sector": sector,
            "Exchange": exchange,
            "Price": round(latest_close, 2),
            "Market Cap ($M)": round(mktcap / 1_000_000, 1),
            "ADR (%)": round(adr, 2),
            "Price×Vol ($M)": round(latest_close * latest_vol / 1_000_000, 1),
            "EMA13": round(e13, 2),
            "EMA21": round(e21, 2),
            "EMA50": round(e50, 2),
            "SMA150": round(s150, 2),
            "SMA200": round(s200, 2),
        }
    except:
        return None

if __name__ == "__main__":
    print("Fetching ticker list...")
    tickers = get_tickers()
    print(f"Total tickers to scan: {len(tickers)}")

    results = []
    for i, ticker in enumerate(tickers):
        if i % 100 == 0:
            print(f"Progress: {i}/{len(tickers)}")
        result = screen_ticker(ticker)
        if result:
            results.append(result)

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values("Market Cap ($M)", ascending=False)

    # Save as JSON for the website
    output = {
        "last_updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "count": len(df),
        "results": df.to_dict(orient="records") if not df.empty else []
    }
    with open("screener_results.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nDone! {len(df)} stocks passed all filters.")
