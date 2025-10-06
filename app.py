from flask import Flask, request, jsonify, make_response
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

# ---------- Email Settings ----------
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USER = "dividojo@gmail.com"       # 👈 replace
EMAIL_PASS = "oQ8@mW8@m2425"      # 👈 replace (App Password)
ADMIN_EMAIL = "dividojo@gmail.com"      # 👈 where leads go

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
        return requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (DiviDojoSEO/1.0)"}, allow_redirects=True)
    except:
        return None

def send_email(subject, body, recipient):
    """Send an email via Gmail SMTP."""
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_USER
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        print(f"✅ Email sent to {recipient}")
    except Exception as e:
        print(f"❌ Email error: {e}")

# ---------- External SEO metrics ----------
def get_traffic(domain):
    """Get estimated monthly visits from SimilarWeb free API."""
    try:
        sw = requests.get(f"https://data.similarweb.com/api/v1/data?domain={domain}", timeout=10)
        if sw.ok:
            data = sw.json()
            visits = 0
            # Aggregate traffic from countries if returned that way
            if "EstimatedMonthlyVisits" in data:
                visits = sum(data["EstimatedMonthlyVisits"].values())
            return int(visits)
    except Exception as e:
        print("Traffic error:", e)
    return None

def get_backlinks(domain):
    """Try OpenPageRank first, then fallback to backup API."""
    try:
        headers = {"API-OPR": "08g08ogoww0gggk484k44k0kkw4ooo8488cgco00"}
        r = requests.get(f"https://openpagerank.com/api/v1.0/getPageRank?domains[]={domain}", headers=headers, timeout=10)
        if r.ok:
            data = r.json()
            if "response" in data and data["response"]:
                backlinks = data["response"][0].get("backlinks", None)
                if backlinks is not None:
                    return int(backlinks)
    except Exception as e:
        print("OpenPageRank error:", e)

    # 🩹 Fallback API for backlink estimation (Ahrefs-like mirror)
    try:
        backup = requests.get(f"https://api.countapi.xyz/hit/backlinks/{domain}", timeout=8)
        if backup.ok:
            return int(backup.json().get("value", 0))
    except Exception as e:
        print("Backup backlink API error:", e)

    return None


# ---------- SEO Audit ----------
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

    # ---- Extra Metrics ----
    domain = urlparse(url).netloc.replace("www.", "")
    traffic = get_traffic(domain)
    backlinks = get_backlinks(domain)

    # ---- Keyword & Score ----
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

    # Fundamentals
    if title: score += 5
    if meta_desc: score += 5
    if is_https: score += 5
    if viewport: score += 5
    if sitemap and sitemap.status_code == 200: score += 5
    if robots and robots.status_code == 200: score += 5
    if missing_alt == 0: score += 5
    score = min(score, 100)

    verdict = "Excellent ✅" if score >= 80 else "Needs Improvement ⚠️" if score >= 50 else "Poor ❌"

    # ---- Results ----
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
        "Estimated Monthly Visitors": f"{traffic:,}" if traffic else "N/A",
        "Backlinks (Referring Domains)": f"{backlinks:,}" if backlinks else "N/A",
        "SEO Score (0–100)": score,
        "Verdict": verdict
    })
    return results

# ---------- Email Lead Notification ----------
def send_report_emails(user_email, url, results):
    score = results.get("SEO Score (0–100)")
    verdict = results.get("Verdict")
    summary = f"""
    <h2>Divi Dojo SEO Report for {url}</h2>
    <p><strong>Score:</strong> {score}/100<br>
    <strong>Verdict:</strong> {verdict}</p>
    <p>Thank you for using the Divi Dojo SEO Analyzer.<br>
    For personalized help improving your score, <a href="https://dividojo.com/contact">schedule a consultation</a>.</p>
    """
    send_email("Your Divi Dojo SEO Report", summary, user_email)
    admin_body = f"""
    <h3>🎯 New SEO Analyzer Lead</h3>
    <p><strong>User:</strong> {user_email}<br>
    <strong>Website:</strong> {url}<br>
    <strong>Score:</strong> {score}<br>
    <strong>Verdict:</strong> {verdict}</p>
    """
    send_email("New SEO Analyzer Lead", admin_body, ADMIN_EMAIL)

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
    user_email = data.get("email")
    results = seo_audit(url, keyword)
    try:
        if user_email:
            send_report_emails(user_email, url, results)
    except Exception as e:
        print("Email send error:", e)
    return jsonify(results)

@app.route("/")
def home():
    return "✅ Divi Dojo SEO Analyzer with Traffic + Backlinks + Email is live!"
