from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import yfinance as yf

app = FastAPI()

# ============================
# CORS 設定
# ============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
# /screening（最適化版）
# ============================
@app.get("/screening")
def screening(volume_ratio: float = 5, shadow_ratio: float = 5):

    batch_size = 30  # Render 無料枠の最適値
    results = []

    for i in range(0, len(ticker_list), batch_size):
        batch = ticker_list[i:i + batch_size]
        symbols = [f"{row['コード']}.T" for row in batch]

        try:
            df = yf.download(
                symbols,
                period="2d",
                interval="1d",
                group_by="ticker",
                threads=True,
                progress=False
            )
        except Exception:
            continue

        for row in batch:
            code = str(row["コード"])
            name = row["銘柄名"]
            symbol = f"{code}.T"

            try:
                data = df[symbol]
                if len(data) < 2:
                    continue

                today = data.iloc[-1]
                yesterday = data.iloc[-2]

                vol_ratio = (
                    today["Volume"] / yesterday["Volume"]
                    if yesterday["Volume"] > 0 else 0
                )

                high = today["High"]
                open_ = today["Open"]
                close = today["Close"]

                upper_shadow = high - max(open_, close)
                real_body = abs(close - open_)
                shadow_ratio_value = (
                    upper_shadow / real_body if real_body > 0 else 0
                )

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

        del df  # メモリ解放

    return results

# ============================
# /chart（単銘柄）
# ============================
@app.get("/chart")
def chart(ticker: str):
    symbol = f"{ticker}.T"

    df = yf.download(symbol, period="200d", interval="1d", progress=False)
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
