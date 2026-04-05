from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import yfinance as yf
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
# バッチサイズ自動調整ロジック
# ============================


def get_batch_size(n: int) -> int:
    """
    Render 無償プラン（512MB / 1 shared core）を前提とした経験則ベースの自動調整。
    - 小規模なら大きめバッチ
    - 大規模（4000銘柄など）は 30 前後に抑える
    """
    if n <= 500:
        return 60
    if n <= 2000:
        return 40
    return 30  # 4000銘柄クラスは 30 が最適帯


MAX_CONCURRENCY = 3  # 並列バッチ数（CPU とレート制限のバランス）


# ============================
# 分割バッチ + 並列化（async）スクリーニング
# ============================


async def fetch_batch(batch, volume_ratio: float, shadow_ratio: float):
    """
    1バッチ分（例：30銘柄）の yfinance.download を実行し、
    条件に合う銘柄だけを返す。
    """
    symbols = [f"{row['コード']}.T" for row in batch]

    # yfinance は同期関数なので、スレッドプールで実行して async 化する
    df = await asyncio.to_thread(
        yf.download,
        symbols,
        None,
        None,
        period="2d",
        interval="1d",
        group_by="ticker",
        threads=True,
        progress=False,
    )

    results = []

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

            # 出来高倍率
            vol_ratio = (
                today["Volume"] / yesterday["Volume"]
                if yesterday["Volume"] > 0
                else 0
            )

            # 上髭実体比
            high = today["High"]
            open_ = today["Open"]
            close = today["Close"]

            upper_shadow = high - max(open_, close)
            real_body = abs(close - open_)
            shadow_ratio_value = (
                upper_shadow / real_body if real_body > 0 else 0
            )

            if vol_ratio >= volume_ratio and shadow_ratio_value >= shadow_ratio:
                results.append(
                    {
                        "コード": code,
                        "銘柄名": name,
                        "出来高倍率": round(vol_ratio, 2),
                        "上髭実体比": round(shadow_ratio_value, 2),
                        "出来高": int(today["Volume"]),
                        "上髭": round(upper_shadow, 2),
                        "実体": round(real_body, 2),
                    }
                )

        except Exception:
            continue

    # df はスコープを抜ければ GC 対象になる
    return results


@app.get("/screening")
async def screening(volume_ratio: float = 5, shadow_ratio: float = 5):
    """
    - 銘柄数に応じてバッチサイズを自動調整
    - 各バッチを async + スレッドプールで並列実行
    - Render 無償プランでも 4000 銘柄を現実的な時間で処理
    """
    n = len(ticker_list)
    batch_size = get_batch_size(n)

    batches = [
        ticker_list[i : i + batch_size] for i in range(0, n, batch_size)
    ]

    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def sem_fetch(batch):
        async with sem:
            return await fetch_batch(batch, volume_ratio, shadow_ratio)

    tasks = [sem_fetch(batch) for batch in batches]
    all_results = await asyncio.gather(*tasks)

    # フラットにする
    results = [item for sub in all_results for item in sub]
    return results


# ============================
# チャート API（単銘柄）
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
