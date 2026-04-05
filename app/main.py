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

async def fetch_quote(session, symbol):
    url = YF_URL.format(symbol)
    async with session.get(url) as resp:
        data = await resp.json()
        return data["quoteResponse"]["result"][0] if data["quoteResponse"]["result"] else None


@app.get("/quote")
async def quote(ticker: str):
    symbol = f"{ticker}.T"

    async with aiohttp.ClientSession() as session:
        url = YF_URL.format(symbol)
        async with session.get(url) as resp:
            if resp.status != 200:
                return {"error": f"HTTP {resp.status}"}

            data = await resp.json()

    # 安全に result を取り出す
    try:
        result_list = data.get("quoteResponse", {}).get("result", [])
        if not result_list:
            return {"error": "no result from Yahoo Finance"}

        return result_list[0]

    except Exception as e:
        return {"error": f"parse error: {str(e)}"}


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
