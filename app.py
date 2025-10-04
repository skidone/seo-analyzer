from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

# ✅ Allow your domain(s) explicitly
CORS(app, resources={r"/analyze": {"origins": [
    "https://dividojo.com",
    "https://www.dividojo.com"
]}})

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

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    url = data.get("url")
    return jsonify(seo_audit(url))

@app.route("/")
def home():
    return "✅ SEO Analyzer is running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
