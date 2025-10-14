# ============================================
#  Divi Dojo SEO Analyzer – Backend (Render)
# ============================================

from flask import Flask, request, jsonify
from flask_cors import CORS
import smtplib
from email.mime.text import MIMEText

# --- Flask setup ---
app = Flask(__name__)
# Allow browser requests from your Divi site
CORS(app, origins=["https://dividojo.com"])


# --------------------------------------------
#  Example /analyze route (placeholder)
#  Replace this logic later with your full SEO analysis code.
# --------------------------------------------
@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    url = data.get("url")
    keyword = data.get("keyword")

    # Simple mock analysis response
    results = {
        "SEO Score (0–100)": 87,
        "Verdict": "Good",
        "Meta Description": "Example meta description detected.",
        "Title Tag": "Example title tag found.",
        "Keyword": keyword or "N/A",
        "URL": url,
    }
    return jsonify(results)


# --------------------------------------------
#  /lead route – sends email using Brevo SMTP
# --------------------------------------------
@app.route("/lead", methods=["POST"])
def lead():
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    message = data.get("message")

    sender = "hello@dividojo.com"      # Your verified sender on Brevo
    receiver = "dividojo@gmail.com"      # Where you want to receive leads
    smtp_user = "dividojo@gmail.com"    # Brevo SMTP login (usually your email)
    smtp_pass = "8jXb3fNEBmp1IWv7"    # Brevo SMTP key from dashboard

    msg = MIMEText(
        f"New SEO Analyzer Lead\n\nName: {name}\nEmail: {email}\n\nMessage:\n{message}"
    )
    msg["Subject"] = f"New SEO Analyzer Lead from {name}"
    msg["From"] = sender
    msg["To"] = receiver

    try:
        server = smtplib.SMTP("smtp-relay.brevo.com", 587)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(sender, receiver, msg.as_string())
        server.quit()
        return jsonify({"ok": True})
    except Exception as e:
        print("Email send error:", e)
        return jsonify({"ok": False, "error": str(e)}), 500


# --------------------------------------------
#  Health check root
# --------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "OK", "message": "Divi Dojo SEO Analyzer API running"})


# --------------------------------------------
#  Run locally (Render ignores this; it's for testing on Mac)
# --------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)