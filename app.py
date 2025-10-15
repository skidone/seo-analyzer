from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app, origins=["https://dividojo.com", "https://www.dividojo.com"])

@app.route("/")
def home():
    return "Divi Dojo SEO Analyzer API is running successfully!"

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    url = data.get("url")
    keyword = data.get("keyword", "")
    email = data.get("email", "")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        # Fetch website
        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        # Extract SEO data
        title = soup.title.string.strip() if soup.title else "No title tag found"
        meta_desc_tag = soup.find("meta", attrs={"name": "description"})
        meta_desc = meta_desc_tag["content"].strip() if meta_desc_tag else "No meta description found"

        # SEO score logic
       # --- inside your analyze route, after fetching the HTML ---
score = 0
factors = 0

if title: 
    score += 20
    factors += 1
if description:
    score += 20
    factors += 1
if keyword and keyword.lower() in title.lower():
    score += 20
    factors += 1
if keyword and keyword.lower() in description.lower():
    score += 10
    factors += 1
if h1_tags:
    score += 15
    factors += 1
if len(h1_tags) > 1:
    score += 5
    factors += 1
if keyword and any(keyword.lower() in h1.lower() for h1 in h1_tags):
    score += 10
    factors += 1

# normalize (cap at 100)
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
    "Keyword In Title": keyword.lower() in title.lower() if keyword else False,
    "SEO Score (0–100)": seo_score,
    "Verdict": verdict
})

        # Additional trust-building insights
        h1_tags = [h1.get_text().strip() for h1 in soup.find_all("h1")]
        h1_count = len(h1_tags)
        keyword_in_title = keyword.lower() in title.lower() if keyword else False

        report = {
            "Title Tag": title,
            "Meta Description": meta_desc,
            "H1 Count": h1_count,
            "H1 Tags": h1_tags,
            "Keyword": keyword,
            "Keyword In Title": keyword_in_title,
            "Verdict": verdict,
            "SEO Score (0–100)": score,
            "URL": url
        }

        return jsonify(report)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)