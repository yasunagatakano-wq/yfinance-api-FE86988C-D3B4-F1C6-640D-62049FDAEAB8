from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import yfinance as yf

app = FastAPI()

# 必要ならフロントのオリジンを指定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 必要に応じて絞る
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 起動時に Excel を読み込んでキャッシュ
TICKERS = []
CODE_TO_NAME = {}


@app.on_event("startup")
def load_ticker_list():
    global TICKERS, CODE_TO_NAME
    df = pd.read_excel("data/jpx_list.xlsx")
    # 列名は実際の Excel に合わせて調整
    code_col = "コード"
    name_col = "銘柄名"

    df[code_col] = df[code_col].astype(str).str.strip()
    df[name_col] = df[name_col].astype(str).str.strip()

    TICKERS = df[code_col].tolist()
    CODE_TO_NAME = dict(zip(df[code_col], df[name_col]))
    print(f"Loaded {len(TICKERS)} tickers")


@app.get("/screening")
def screening(
    volume_ratio: float = Query(5.0, alias="volume_ratio"),
    shadow_ratio: float = Query(5.0, alias="shadow_ratio"),
):
    """
    全銘柄を対象にサーバー側でスクリーニングして、
    条件に合った銘柄だけを返す。
    """
    if not TICKERS:
        return []

    # yfinance で全銘柄 200 日分をまとめて取得
    symbols = [f"{code}.T" for code in TICKERS]
    data = yf.download(
        symbols,
        period="200d",
        interval="1d",
        group_by="ticker",
        threads=True,
    )

    results = []

    for code in TICKERS:
        symbol = f"{code}.T"
        if symbol not in data:
            continue

        df = data[symbol].dropna()
        if len(df) < 2:
            continue

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        open_ = latest["Open"]
        close_ = latest["Close"]
        high_ = latest["High"]
        vol_today = latest["Volume"]
        vol_yest = prev["Volume"]

        if any(pd.isna(v) for v in [open_, close_, high_, vol_today, vol_yest]):
            continue

        real_body = abs(close_ - open_)
        upper_shadow = high_ - max(open_, close_)
        actual_volume_ratio = vol_today / vol_yest if vol_yest > 0 else 0
        actual_shadow_ratio = upper_shadow / real_body if real_body > 0 else 0

        if actual_volume_ratio >= volume_ratio and actual_shadow_ratio >= shadow_ratio:
            name = CODE_TO_NAME.get(code, "N/A")
            results.append(
                {
                    "コード": code,
                    "銘柄名": name,
                    "出来高倍率": round(actual_volume_ratio, 2),
                    "上髭実体比": round(actual_shadow_ratio, 2),
                    "出来高": int(vol_today),
                    "上髭": round(upper_shadow, 2),
                    "実体": round(real_body, 2),
                }
            )

    # 出来高倍率で降順ソートして返す
    results.sort(key=lambda x: x["出来高倍率"], reverse=True)
    return results


@app.get("/chart")
def chart(ticker: str = Query(..., alias="ticker")):
    """
    個別銘柄の 200 日分データを返す。
    chart.js / 旧 screening.js が期待していた形式に近づける。
    """
    symbol = f"{ticker}.T"
    df = yf.download(symbol, period="200d", interval="1d")
    if df.empty:
        return {}

    df = df.dropna()
    result = {
        "Open": {},
        "High": {},
        "Low": {},
        "Close": {},
        "Volume": {},
    }

    for idx, row in df.iterrows():
        date_str = idx.strftime("%Y-%m-%d")
        result["Open"][date_str] = float(row["Open"])
        result["High"][date_str] = float(row["High"])
        result["Low"][date_str] = float(row["Low"])
        result["Close"][date_str] = float(row["Close"])
        result["Volume"][date_str] = float(row["Volume"])

    return result