from flask import Flask, request, jsonify
from flask_cors import CORS
import yfinance as yf

app = Flask(__name__)
CORS(app)  # ← CORS 有効化

@app.route("/chart")
def chart():
    symbol = request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "symbol required"}), 400

    data = yf.Ticker(symbol).history(period="7d")
    return data.to_json()

@app.route("/chart_full")
def chart_full():
    symbol = request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "symbol required"}), 400

    # ★ 200日分の日足データ（MA 計算用）
    data = yf.Ticker(symbol).history(period="200d", interval="1d")
    return data.to_json()
