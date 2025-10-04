from flask import Flask, request, jsonify, make_response
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

app = Flask(__name__)

# ---------- Helpers ----------
def normalize_url(u):
    u = (u or "").strip()
    if not u:
        return ""
    parsed = urlparse(u)
    if not parsed.scheme:
        u = "https://" + u
    return u

def get(url, timeout=10):
    try:
        return requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (DiviDojoSEO/1.0)"},
            allow_redirects=True,
        )
    except:
        return None

# ---------- Main Analyzer ----------
def seo_audit(url, keyword=None):
    results = {}
    url = normalize_url(url)
    if not url:
        return {"Error": "No URL provided."}

    resp = get(url)
    if not resp or not resp.ok:
        code = getattr(resp, "status_code", "N/A")
        return {"Error": f"Could not fetch URL (status {code})."}

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else None
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_desc = meta_desc_tag.get("content").strip() if meta_desc_tag and meta_desc_tag.get("content") else None
    h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]
    viewport = soup.find("meta", attrs={"name": "viewport"})
    text = soup.get_text(separator=" ", strip=True)
    first200 = text[:200].lower() if text else ""
    word_count = len(text.split())
    images = soup.find_all("img")
    missing_alt = sum(1 for img in images if not (img.get("alt") or "").strip())
    is_https = urlparse(resp.url).scheme == "https"

    robots = get(url.rstrip("/") + "/robots.txt")
    sitemap = get(url.rstrip("/") + "/sitemap.xml")

    # ---------- Keyword & Scoring ----------
    keyword_found = []
    score = 0
    keyword = (keyword or "").lower().strip()
    if keyword:
        if keyword in (title or "").lower():
            keyword_found.append("Title"); score += 20
        if keyword in (meta_desc or "").lower():
            keyword_found.append("Meta Description"); score += 20
        if any(keyword in h.lower() for h in h1_tags):
            keyword_found.append("H1 Tag"); score += 20
        if keyword in first200:
            keyword_found.append("First Paragraph"); score += 20

    # Fundamental factors
    if title: score += 5
    if meta_desc: score += 5
    if is_https: score += 5
    if viewport: score += 5
    if sitemap and sitemap.status_code == 200: score += 5
    if robots and robots.status_code == 200: score += 5
    if missing_alt == 0: score += 5

    # Cap score at 100
    score = min(score, 100)

    # Verdict
    if score >= 80:
        verdict = "Excellent ✅"
    elif score >= 50:
        verdict = "Needs Improvement ⚠️"
    else:
        verdict = "Poor ❌"

    # ---------- Results ----------
    results.update({
        "Final URL": resp.url,
        "HTTPS Enabled": "✅ Yes" if is_https else "❌ No",
        "Title": title or "❌ Missing Title",
        "Meta Description": meta_desc or "❌ Missing Description",
        "H1 Count": len(h1_tags),
        "First H1": h1_tags[0] if h1_tags else "❌ No H1 found",
        "Word Count": word_count,
        "Images Without ALT": missing_alt,
        "robots.txt Found": "✅ Yes" if robots and robots.status_code == 200 else "❌ No",
        "Sitemap Found": "✅ Yes" if sitemap and sitemap.status_code == 200 else "❌ No",
        "Viewport (Mobile Friendly)": "✅ Present" if viewport else "❌ Missing",
        "Keyword": keyword or "N/A",
        "Keyword Found In": ", ".join(keyword_found) if keyword_found else "❌ Not Found",
        "SEO Score (0–100)": score,
        "Verdict": verdict
    })

    return results

# ---------- CORS ----------
@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    allowed = ["https://dividojo.com", "https://www.dividojo.com"]
    if origin in allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

# ---------- Routes ----------
@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    if request.method == "OPTIONS":
        return make_response("", 200)
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    keyword = data.get("keyword")
    return jsonify(seo_audit(url, keyword))

@app.route("/")
def home():
    return "✅ Divi Dojo SEO Analyzer with Keyword Scoring is live!"
