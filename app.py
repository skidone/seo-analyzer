from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import os

app = Flask(__name__)
# Allow your site + local for testing; widen if you embed on multiple domains
CORS(app, resources={r"/*": {"origins": ["https://dividojo.com", "https://www.dividojo.com", "*"]}})

UA = "Mozilla/5.0 (compatible; DiviDojoSEO/1.0; +https://dividojo.com)"
TIMEOUT = 10

def fetch(url):
    return requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)

@app.route("/")
def home():
    return "Divi Dojo SEO Analyzer API is running successfully!"

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    keyword = (data.get("keyword") or "").strip().lower()

    if not url:
        return jsonify({"error": "Missing URL"}), 400

    # Normalize URL
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urlparse(url)

    try:
        r = fetch(url)
    except Exception as e:
        return jsonify({"error": f"Fetch failed: {e}"}), 400

    if r.status_code != 200:
        return jsonify({"error": f"Unable to fetch URL (status {r.status_code})"}), 400

    html = r.text
    soup = BeautifulSoup(html, "html.parser")

    # ---------- Extract signals ----------
    # Title
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""

    # Meta description
    md = soup.find("meta", attrs={"name": "description"})
    description = (md.get("content") or "").strip() if md else ""

    # H1 tags
    h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]

    # Word count (visible text heuristic)
    for t in soup(["script", "style", "noscript"]):
        t.extract()
    text = soup.get_text(separator=" ")
    words = [w for w in text.split() if w.isalpha() or any(c.isalnum() for c in w)]
    word_count = len(words)

    # Images without alt
    imgs = soup.find_all("img")
    imgs_without_alt = sum(1 for im in imgs if not (im.get("alt") or "").strip())

    # Viewport (mobile)
    viewport = soup.find("meta", attrs={"name": "viewport"})
    viewport_ok = bool(viewport)

    # HTTPS
    https_ok = (parsed.scheme.lower() == "https")

    # robots.txt / sitemap.xml
    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_ok = False
    sitemap_ok = False
    try:
        rr = requests.head(urljoin(base, "/robots.txt"), headers={"User-Agent": UA}, timeout=TIMEOUT, allow_redirects=True)
        if rr.status_code == 200:
            robots_ok = True
    except Exception:
        pass
    try:
        sr = requests.head(urljoin(base, "/sitemap.xml"), headers={"User-Agent": UA}, timeout=TIMEOUT, allow_redirects=True)
        if sr.status_code == 200:
            sitemap_ok = True
    except Exception:
        pass

    # Keyword presence
    keyword_in_title = bool(keyword and title and keyword in title.lower())
    keyword_in_desc = bool(keyword and description and keyword in description.lower())
    keyword_in_h1 = bool(keyword and any(keyword in h1.lower() for h1 in h1_tags))
    keyword_in_body = bool(keyword and (keyword in text.lower()))
    keyword_found_in_list = []
    if keyword:
        if keyword_in_title: keyword_found_in_list.append("Title")
        if keyword_in_desc:  keyword_found_in_list.append("Meta")
        if keyword_in_h1:    keyword_found_in_list.append("H1")
        if keyword_in_body:  keyword_found_in_list.append("Body")

    # ---------- Scoring (weights sum to ~100) ----------
    score = 0
    # Core on-page
    if title:                score += 10
    if description:          score += 10
    if h1_tags:              score += 10

    # Keyword targeting
    if keyword_in_title:     score += 12
    if keyword_in_desc:      score += 6
    if keyword_in_h1:        score += 6
    if keyword_in_body:      score += 6

    # Technical basics
    if https_ok:             score += 10
    if viewport_ok:          score += 8
    if robots_ok:            score += 6
    if sitemap_ok:           score += 6

    # Content depth
    if word_count >= 1200:   score += 12
    elif word_count >= 600:  score += 8
    elif word_count >= 300:  score += 4

    # Image alt coverage (reward if most images have alt)
    total_imgs = len(imgs)
    if total_imgs > 0:
        covered = total_imgs - imgs_without_alt
        coverage_ratio = covered / total_imgs
        if coverage_ratio >= 0.9:      score += 8
        elif coverage_ratio >= 0.7:    score += 4
        elif coverage_ratio >= 0.5:    score += 2

    # Bound score
    seo_score = max(0, min(100, int(round(score))))

    verdict = ("Excellent ✅" if seo_score >= 85
               else "Good 👍" if seo_score >= 70
               else "Needs Improvement ⚠️")

    # ---------- Pretty fields for the v17 UI ----------
    def check_str(ok, yes="✅ Yes", no="❌ No"):
        return yes if ok else no

    title_field = "✅ Present — {} chars".format(len(title)) if title else "❌ Missing"
    desc_field  = "✅ Present — {} chars".format(len(description)) if description else "❌ Missing"
    viewport_field = "✅ Present" if viewport_ok else "❌ Missing"
    https_field = check_str(https_ok)
    robots_field = check_str(robots_ok, yes="✅ Found", no="❌ Not Found")
    sitemap_field = check_str(sitemap_ok, yes="✅ Found", no="❌ Not Found")
    kw_where = ", ".join(keyword_found_in_list) if keyword_found_in_list else "Not Found"

    # Optional authority metrics (set to N/A unless you wire an API)
    estimated_visitors = "N/A"
    backlinks_domains = "N/A"

    # Response payload: include both neutral values and ✅/❌ for your icon logic
    payload = {
        "URL": url,
        # headline metrics
        "SEO Score (0–100)": seo_score,
        "Verdict": verdict,
        "Estimated Monthly Visitors": estimated_visitors,
        "Backlinks (Referring Domains)": backlinks_domains,

        # details (your v17 loops these into cards; emoji enable green/red icons)
        "Title": title_field,
        "Title Tag": title or "",
        "Meta Description": desc_field if desc_field else "❌ Missing",
        "H1 Count": len(h1_tags),
        "Word Count": word_count,
        "Images Without ALT": imgs_without_alt,
        "Viewport (Mobile Friendly)": viewport_field,
        "HTTPS Enabled": https_field,
        "robots.txt Found": robots_field,
        "Sitemap Found": sitemap_field,
        "Keyword Found In": kw_where
    }

    return jsonify(payload)

# ---------- Lead capture ----------
@app.route("/lead", methods=["POST"])
def lead():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    message = (data.get("message") or "").strip()

    # If a Brevo API key is set, send an email; otherwise return ok without error.
    brevo_api_key = os.environ.get("BREVO_API_KEY", "").strip()
    to_email = os.environ.get("TO_EMAIL", "dividojo@gmail.com").strip()

    if brevo_api_key:
        try:
            resp = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "accept": "application/json",
                    "api-key": brevo_api_key,
                    "content-type": "application/json",
                },
                json={
                    "sender": {"name": "Divi Dojo SEO Analyzer", "email": to_email},
                    "to": [{"email": to_email, "name": "Divi Dojo"}],
                    "subject": "New SEO Lead from Analyzer",
                    "htmlContent": f"""
                        <h3>New Lead</h3>
                        <p><strong>Name:</strong> {name or '(not provided)'}<br/>
                        <strong>Email:</strong> {email or '(not provided)'}<br/>
                        <strong>Message:</strong> {message or '(none)'}<br/></p>
                    """,
                },
                timeout=TIMEOUT,
            )
            if resp.status_code >= 300:
                # Log but don't fail UX
                print("Brevo error:", resp.status_code, resp.text)
        except Exception as e:
            print("Brevo send exception:", e)

    # Always OK for front-end UX
    return jsonify({"ok": True})
    

if __name__ == "__main__":
    # Render will run via gunicorn, but this helps local testing
    app.run(host="0.0.0.0", port=5000)