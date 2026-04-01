from flask import Flask, request, jsonify
from flask_cors import CORS
import yfinance as yf

app = Flask(__name__)
CORS(app)

@app.route("/chart")
def chart():
    symbol = request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "symbol required"}), 400

    data = yf.Ticker(symbol).history(period="7d", auto_adjust=False)
    return data.to_json()

@app.route("/chart_full")
def chart_full():
    symbol = request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "symbol required"}), 400

    # ★ 200日分のデータ（調整なしの Close を返す）
    data = yf.Ticker(symbol).history(
        period="200d",
        interval="1d",
        auto_adjust=False  # ← 楽天証券と一致させるために必須
    )

    return data.to_json()
