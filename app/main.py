from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import yfinance as yf

app = FastAPI()

# ============================
# CORS 設定（GitHub Pages からのアクセスを許可）
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
    # Render の構成に合わせたパス
    df = pd.read_excel("app/data/data_j.xlsx")
    ticker_list = df.to_dict(orient="records")

load_ticker_list()


# ============================
# 高速版スクリーニング API（全銘柄一括取得）
# ============================
@app.api_route("/screening", methods=["GET", "HEAD"])
def screening(volume_ratio: float = 5, shadow_ratio: float = 5):
    # 1. 銘柄コードをまとめて ".T" を付ける
    symbols = [f"{str(row['コード'])}.T" for row in ticker_list]

    # 2. 全銘柄を一括ダウンロード（2日分）
    df = yf.download(
        symbols,
        period="2d",
        interval="1d",
        group_by="ticker",
        progress=False,
        threads=True
    )

    results = []

    # 3. 各銘柄をループして条件判定
    for row in ticker_list:
        code = str(row["コード"])
        name = row["銘柄名"]
        symbol = f"{code}.T"

        try:
            data = df[symbol]

            if len(data) < 2:
                continue

            today = data.iloc[-1]
            yesterday = data.iloc[-2]

            # 出来高倍率
            vol_ratio = today["Volume"] / yesterday["Volume"] if yesterday["Volume"] > 0 else 0

            # 上髭実体比
            high = today["High"]
            open_ = today["Open"]
            close = today["Close"]

            upper_shadow = high - max(open_, close)
            real_body = abs(close - open_)
            shadow_ratio_value = upper_shadow / real_body if real_body > 0 else 0

            # 条件判定
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
# チャート API（個別銘柄）
# ============================
@app.get("/chart")
def chart(ticker: str):
    symbol = f"{ticker}.T"

    df = yf.download(symbol, period="200d", interval="1d", progress=False)

    if df.empty:
        return {"error": "no data"}

    # ★ 単銘柄モードを強制的にフラット化
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
