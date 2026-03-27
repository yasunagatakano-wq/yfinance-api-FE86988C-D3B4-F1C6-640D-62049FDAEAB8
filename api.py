from flask import Flask, request, jsonify
from flask_cors import CORS
import yfinance as yf

app = Flask(__name__)
CORS(app)  # ← これが重要！

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

    # 1ヶ月分の日足データ
    data = yf.Ticker(symbol).history(period="1mo", interval="1d")
    return data.to_json()
