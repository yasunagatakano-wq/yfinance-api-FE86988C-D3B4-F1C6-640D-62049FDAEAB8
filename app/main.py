from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import yfinance as yf
import math
import aiohttp
import asyncio

app = FastAPI()

# ============================
# CORS 設定
# ============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 必要なら ["https://yasunagatakano-wq.github.io"] に変更可
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================
# 銘柄リスト読み込み
# ============================
ticker_list = []

def load_ticker_list():
    global ticker_list
    df = pd.read_excel("app/data/data_j.xlsx")
    ticker_list = df.to_dict(orient="records")

load_ticker_list()


# ============================
# Yahoo Finance JSON API（async）
# ============================
YF_URL = "https://query1.finance.yahoo.com/v7/finance/quote?symbols={}"

async def fetch_quote(session, symbol, retries=3):
    url = YF_URL.format(symbol)

    for attempt in range(retries):
        async with session.get(url) as resp:
            # 成功
            if resp.status == 200:
                data = await resp.json()
                result_list = data.get("quoteResponse", {}).get("result", [])
                return result_list[0] if result_list else {"error": "no result"}

            # レート制限 → 少し待ってリトライ
            if resp.status == 429:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue

            # その他の HTTP エラー
            return {"error": f"HTTP {resp.status}"}

    return {"error": "too many retries"}


@app.get("/quote")
async def quote(ticker: str):
    symbol = f"{ticker}.T"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Referer": "https://finance.yahoo.com/",
        "Cookie": "B=dummy; yfin-usr=1"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        result = await fetch_quote(session, symbol)

    return result


# ============================
# 分割ダウンロード版スクリーニング API（検証用）
# ============================
@app.api_route("/screening", methods=["GET", "HEAD"])
def screening(volume_ratio: float = 5, shadow_ratio: float = 5):
    # 検証用：先頭 50 銘柄だけに限定
    subset = ticker_list[:50]

    results = []

    for row in subset:
        code = str(row["コード"])
        name = row["銘柄名"]
        symbol = f"{code}.T"

        try:
            df = yf.download(symbol, period="2d", interval="1d", progress=False)
            if len(df) < 2:
                continue

            today = df.iloc[-1]
            yesterday = df.iloc[-2]

            vol_ratio = today["Volume"] / yesterday["Volume"] if yesterday["Volume"] > 0 else 0

            high = today["High"]
            open_ = today["Open"]
            close = today["Close"]

            upper_shadow = high - max(open_, close)
            real_body = abs(close - open_)
            shadow_ratio_value = upper_shadow / real_body if real_body > 0 else 0

            if vol_ratio >= volume_ratio and shadow_ratio_value >= shadow_ratio:
                results.append({
                    "コード": code,
                    "銘柄名": name,
                    "出来高倍率": round(vol_ratio, 2),
                    "上髭実体比": round(shadow_ratio_value, 2),
                    "出来高": int(today["Volume"]),
                    "上髭": round(upper_shadow, 2),
                    "実体": round(real_body, 2),
                })

        except Exception:
            continue

    return results


# ============================
# チャート API（単銘柄モード強制）
# ============================
@app.get("/chart")
def chart(ticker: str):
    symbol = f"{ticker}.T"

    df = yf.download(symbol, period="200d", interval="1d", progress=False)
    if df.empty:
        return {"error": "no data"}

    # ★ 複数銘柄モードの DataFrame を単銘柄に強制変換
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs(symbol, level=1, axis=1)

    df.index = df.index.strftime("%Y-%m-%d")

    return {
        "Open": df["Open"].to_dict(),
        "High": df["High"].to_dict(),
        "Low": df["Low"].to_dict(),
        "Close": df["Close"].to_dict(),
        "Volume": df["Volume"].to_dict(),
    }
