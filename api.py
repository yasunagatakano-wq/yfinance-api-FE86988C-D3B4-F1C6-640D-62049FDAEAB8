from flask import Flask, request, jsonify
import yfinance as yf

app = Flask(__name__)

@app.route("/chart")
def chart():
    symbol = request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "symbol required"}), 400

    data = yf.Ticker(symbol).history(period="7d")
    return data.to_json()
