from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import requests
import json
import math
from io import BytesIO
import warnings

import yfinance as yf
warnings.filterwarnings("ignore")

app = FastAPI()

# ============================
# CORS 設定
# ============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yasunagatakano-wq.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================
# 外部ファイル URL
# ============================
DATA_JSON_URL = "https://raw.githubusercontent.com/yasunagatakano-wq/batch-F0AF5A52-4132-E578-F4A3-36FDFFACE338/main/data.json"
EXCEL_URL = "https://raw.githubusercontent.com/yasunagatakano-wq/batch-F0AF5A52-4132-E578-F4A3-36FDFFACE338/main/data_j.xlsx"

# ============================
# データ読み込み
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
# /dates（プルダウン用）
# ============================
@app.get("/dates")
def get_dates():
    all_dates = set()
    for symbol, entry in data_json.items():
        if isinstance(entry, dict):
            for d in entry.keys():
                if d.isdigit():  # "20240527" のようなキーのみ
                    all_dates.add(d)
    return sorted(all_dates, reverse=True)

# ============================
# /screening（2モード対応）
# ============================
@app.get("/screening")
def screening(
    mode: str = "ratio",
    volume_ratio: float = 5,
    shadow_ratio: float = 5,
    target_date: str = None
):
    results = []

    # ----------------------------
    # モード A：従来の出来高×上髭検索
    # ----------------------------
    if mode == "ratio":
        for row in ticker_list:
            code = str(row["コード"])
            name = row["銘柄名"]
            symbol = f"{code}.T"

            if symbol not in data_json:
                continue

            entry = data_json[symbol]
            if not isinstance(entry, dict):
                continue

            # ★ 最新日付と前日を取得
            dates = sorted([d for d in entry.keys() if d.isdigit()], reverse=True)
            if len(dates) < 2:
                continue

            today_key = dates[0]
            prev_key = dates[1]

            today = entry.get(today_key)
            prev = entry.get(prev_key)

            if not today or not prev:
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

        results.sort(key=lambda x: x["コード"])
        return results

    # ----------------------------
    # モード B：値上がり率ランキング
    # ----------------------------
    elif mode == "date_ranking":
        if not target_date:
            return {"error": "target_date is required"}

        for row in ticker_list:
            code = str(row["コード"])
            name = row["銘柄名"]
            symbol = f"{code}.T"

            if symbol not in data_json:
                continue

            entry = data_json[symbol]
            if not isinstance(entry, dict):
                continue

            # ★ target_date の前日を探す
            dates = sorted([d for d in entry.keys() if d.isdigit()])
            if target_date not in dates:
                continue

            idx = dates.index(target_date)
            if idx == 0:
                continue  # 前日がない

            prev_key = dates[idx - 1]

            today = entry[target_date]
            prev = entry[prev_key]

            if not today or not prev:
                continue

            try:
                today_close = today.get("c")
                prev_close = prev.get("c")

                if not prev_close or prev_close <= 0:
                    continue

                change_rate = (today_close - prev_close) / prev_close * 100

                results.append({
                    "コード": code,
                    "銘柄名": name,
                    "値上がり率": round(change_rate, 2),
                    "当日終値": today_close,
                    "前日終値": prev_close,
                    "日付": target_date
                })

            except Exception:
                continue

        # ★ 値上がり率の降順で上位100件
        results.sort(key=lambda x: x["値上がり率"], reverse=True)
        return results[:100]

    # ----------------------------
    # 不正モード
    # ----------------------------
    else:
        return {"error": "invalid mode"}

# ============================
# /chart（従来通り）
# ============================
@app.get("/chart")
def chart(ticker: str, timeframe: str = "1d"):
    symbol = f"{ticker}.T"

    # まずは「十分長い」日足だけを取る
    # 週足・月足はここから集計する
    df = yf.download(symbol, period="6000d", interval="1d", progress=False)
    if df.empty:
        return {"error": "no data"}

    # MultiIndex 対応（銘柄列を抽出）
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs(symbol, level=1, axis=1)

    # DatetimeIndex に統一
    df.index = pd.to_datetime(df.index)

    # ---- 週足（W-FRI：金曜終値ベース）----
    df_week = df.resample("W-FRI").agg({
        "Open": "first",   # 週の最初の営業日の始値
        "High": "max",     # 週内の高値の最大
        "Low": "min",      # 週内の安値の最小
        "Close": "last",   # 週の最後の営業日の終値
        "Volume": "sum",   # 週内出来高の合計
    }).dropna(how="any")

    # ---- 月足（暦月ベース）----
    df_month = df.resample("M").agg({
        "Open": "first",   # 月初の営業日の始値
        "High": "max",     # 月内の高値の最大
        "Low": "min",      # 月内の安値の最小
        "Close": "last",   # 月末の営業日の終値
        "Volume": "sum",   # 月内出来高の合計
    }).dropna(how="any")

    # ---- timeframe に応じて出力を選択 ----
    if timeframe == "1d":
        df_out = df.tail(200)          # 直近 200 本
    elif timeframe == "1wk":
        df_out = df_week.tail(200)
    elif timeframe == "1mo":
        df_out = df_month.tail(200)
    else:
        return {"error": "invalid timeframe"}

    # 軽量な JSON に変換
    df_out.index = df_out.index.strftime("%Y-%m-%d")

    return {
        "Open": df_out["Open"].to_dict(),
        "High": df_out["High"].to_dict(),
        "Low": df_out["Low"].to_dict(),
        "Close": df_out["Close"].to_dict(),
        "Volume": df_out["Volume"].to_dict(),
    }
