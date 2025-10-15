from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return "Divi Dojo SEO Analyzer API is running successfully!"

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json()
        url = data.get("url")
        keyword = (data.get("keyword") or "").strip().lower()

        if not url:
            return jsonify({"error": "Missing URL"}), 400

        # --- Fetch page ---
        headers = {"User-Agent": "Mozilla/5.0 (compatible; DiviDojoBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return jsonify({"error": f"Unable to fetch URL (status {resp.status_code})"}), 400

        soup = BeautifulSoup(resp.text, "html.parser")

        # --- Extract elements ---
        title = (soup.title.string or "").strip() if soup.title else ""
        desc_tag = soup.find("meta", attrs={"name": "description"})
        description = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""
        h1_tags = [h1.get_text(strip=True) for h1 in soup.find_all("h1")]

        # --- Dynamic SEO scoring ---
        score = 0

        if title:
            score += 20
        if description:
            score += 20
        if keyword and keyword in title.lower():
            score += 20
        if keyword and keyword in description.lower():
            score += 10
        if h1_tags:
            score += 15
        if len(h1_tags) > 1:
            score += 5
        if keyword and any(keyword in h1.lower() for h1 in h1_tags):
            score += 10

        seo_score = min(100, int(score))

        verdict = (
            "Excellent ✅" if seo_score >= 85 else
            "Good 👍" if seo_score >= 70 else
            "Needs Improvement ⚠️"
        )

        return jsonify({
            "URL": url,
            "Title Tag": title,
            "Meta Description": description,
            "H1 Count": len(h1_tags),
            "Keyword In Title": bool(keyword and keyword in title.lower()),
            "SEO Score (0–100)": seo_score,
            "Verdict": verdict
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)