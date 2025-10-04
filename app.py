from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

# ✅ Enable CORS for everything (test mode)
CORS(app, resources={r"/*": {"origins": "*"}})

def seo_audit(url):
    results = {}
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(response.text, "html.parser")

        results["Title"] = soup.title.string if soup.title else "❌ Missing Title"
        meta_desc = soup.find("meta", attrs={"name": "description"})
        results["Meta Description"] = meta_desc["content"] if meta_desc else "❌ Missing Description"
        h1_tags = soup.find_all("h1")
        results["H1 Count"] = len(h1_tags)
        results["First H1"] = h1_tags[0].get_text() if h1_tags else "❌ No H1 found"
        text = soup.get_text()
        results["Word Count"] = len(text.split())
        images = soup.find_all("img")
        missing_alt = sum(1 for img in images if not img.get("alt"))
        results["Images Without ALT"] = missing_alt

    except Exception as e:
        results["Error"] = str(e)
    return results

@app.after_request
def add_cors_headers(response):
    """Force CORS headers on every response, including OPTIONS."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    if request.method == "OPTIONS":
        # Explicitly respond to preflight
        return make_response(jsonify({"status": "CORS preflight OK"}), 200)
    data = request.json
    url = data.get("url")
    return jsonify(seo_audit(url))

@app.route("/")
def home():
    return "✅ SEO Analyzer is running!"
