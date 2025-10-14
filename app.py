from flask import Flask, request, jsonify
# ... other imports like requests, BeautifulSoup, etc.

app = Flask(__name__)

@app.route("/analyze", methods=["POST"])
def analyze():
    # Your existing SEO analyzer code
    # It fetches the website and returns results
    return jsonify(results)


# ✅ Add this ONCE — only one copy of the lead route
@app.route("/lead", methods=["POST"])
def lead():
    from flask import request, jsonify
    import smtplib, ssl
    from email.mime.text import MIMEText

    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    message = data.get("message")

    sender = "dividojo@gmail.com"          # the Gmail you used for App Password
    receiver = "dividojo@gmail.com"          # where you want the leads sent
    password = "ppbx ehuc spov nagk"           # your 16-character app password

    msg = MIMEText(f"New SEO Analyzer Lead from {name}\nEmail: {email}\n\nMessage:\n{message}")
    msg["Subject"] = f"New SEO Analyzer Lead from {name}"
    msg["From"] = sender
    msg["To"] = receiver

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender, password)
            server.sendmail(sender, receiver, msg.as_string())
        return jsonify({"ok": True})
    except Exception as e:
        print("Email send error:", e)
        return jsonify({"ok": False, "error": str(e)}), 500