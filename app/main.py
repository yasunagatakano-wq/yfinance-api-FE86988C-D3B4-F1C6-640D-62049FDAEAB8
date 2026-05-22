from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import requests
import json
import math
from io import BytesIO
import warnings

# yfinance の警告ログを無効化（/chart で使用）
import yfinance as yf
warnings.filterwarnings("ignore")

app = FastAPI()

# ============================
# CORS 設定
# ============================
app.add_middleware(
    CORSMiddleware,
    # allow_origins=["*"],
    allow_origins=["https://yasunagatakano-wq.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================
# 外部ファイルの URL（main ブランチを参照）
# ============================
DATA_JSON_URL = "https://raw.githubusercontent.com/yasunagatakano-wq/batch-F0AF5A52-4132-E578-F4A3-36FDFFACE338/main/data.json"
EXCEL_URL = "https://raw.githubusercontent.com/yasunagatakano-wq/batch-F0AF5A52-4132-E578-F4A3-36FDFFACE338/main/data_j.xlsx"

# ============================
# 銘柄リスト・data.json の読み込み
# ============================
ticker_list = []
data_json = {}

def load_ticker_list():
    global ticker_list
    resp = requests.get(EXCEL_URL)
    resp.raise_for_status()
    df = pd.read_excel(BytesIO(resp.content))
    ticker_list = df.to_dict(orient="records")

def load_data_json():
    global data_json
    resp = requests.get(DATA_JSON_URL)
    resp.raise_for_status()
    data_json = json.loads(resp.text)

load_ticker_list()
load_data_json()

# ============================
# /screening（data.json 利用版）
# ============================
@app.get("/screening")
def screening(volume_ratio: float = 5, shadow_ratio: float = 5):
    results = []

    for row in ticker_list:
        code = str(row["コード"])
        name = row["銘柄名"]
        symbol = f"{code}.T"

        # data.json に存在しない銘柄はスキップ
        if symbol not in data_json:
            continue

        entry = data_json[symbol]

        # error フィールドがある銘柄はスキップ
        if isinstance(entry, dict) and "error" in entry:
            continue

        prev = entry.get("prev")
        today = entry.get("today")

        if not prev or not today:
            continue

        try:
            prev_vol = prev.get("v")
            today_vol = today.get("v")

            if not prev_vol or prev_vol <= 0:
                continue

            vol_ratio = today_vol / prev_vol

            high = today.get("h")
            open_ = today.get("o")
            close = today.get("c")

            if high is None or open_ is None or close is None:
                continue

            upper_shadow = high - max(open_, close)
            real_body = abs(close - open_)

            if real_body <= 0:
                continue

            shadow_ratio_value = upper_shadow / real_body

            if vol_ratio >= volume_ratio and shadow_ratio_value >= shadow_ratio:
                results.append({
                    "コード": code,
                    "銘柄名": name,
                    "出来高倍率": round(vol_ratio, 2),
                    "上髭実体比": round(shadow_ratio_value, 2),
                    "出来高": int(today_vol),
                    "上髭": round(upper_shadow, 2),
                    "実体": round(real_body, 2),
                })

        except Exception:
            continue

    # ★ 銘柄コードの昇順でソート
    results.sort(key=lambda x: x["コード"])

    return results

# ============================
# /chart（単銘柄：従来通り yfinance 使用）
# ============================
@app.get("/chart")
def chart(ticker: str, timeframe: str = "1d"):
    symbol = f"{ticker}.T"

    # 日足200本に合わせる
    if timeframe == "1d":
        period = "200d"
    elif timeframe == "1wk":
        period = "1400d"   # 200週 ≒ 1400日
    elif timeframe == "1mo":
        period = "6000d"   # 200ヶ月 ≒ 6000日
    else:
        return {"error": "invalid timeframe"}

    df = yf.download(symbol, period=period, interval=timeframe, progress=False)
    if df.empty:
        return {"error": "no data"}

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
