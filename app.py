from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import os
import re
import time

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

# ---------- Existing Business Lead Generator ----------

CHAIN_HINTS = [
    "mcdonald", "burger king", "wendy", "taco bell", "subway", "starbucks",
    "dunkin", "chipotle", "panera", "domino", "pizza hut", "papa john",
    "walmart", "target", "costco", "sam's club", "walgreens", "cvs",
    "publix", "aldi", "whole foods", "home depot", "lowe", "best buy",
    "chase", "bank of america", "wells fargo", "truist", "td bank",
    "anytime fitness", "planet fitness", "orange theory", "orangetheory",
    "la fitness", "crunch fitness", "massage envy", "hand and stone",
    "great clips", "sport clips", "supercuts", "the ups store",
    "state farm", "allstate", "geico", "farmers insurance",
    "marriott", "hilton", "hyatt", "hampton inn", "holiday inn"
]

DIRECTORY_DOMAINS = [
    "facebook.com", "instagram.com", "linktr.ee", "yelp.com", "square.site",
    "sites.google.com", "business.site", "wixsite.com", "godaddysites.com",
    "booking.com", "opentable.com", "toasttab.com", "clover.com",
    "mindbodyonline.com", "vagaro.com", "schedulicity.com"
]

HIGH_VALUE_CATEGORIES = [
    "med spa", "medical spa", "dentist", "chiropractor", "attorney",
    "law firm", "roofing", "roofer", "hvac", "plumber", "electrician",
    "contractor", "remodeler", "interior designer", "landscaper",
    "pool service", "pest control", "veterinarian", "physical therapy",
    "wellness", "salon", "fitness", "senior care", "mobility"
]


def google_api_key():
    return os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()


def google_get(endpoint, params):
    key = google_api_key()
    if not key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not set")

    params["key"] = key
    response = requests.get(endpoint, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def geocode_market(market):
    data = google_get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        {"address": market}
    )

    if data.get("status") != "OK" or not data.get("results"):
        raise RuntimeError("Could not geocode market")

    loc = data["results"][0]["geometry"]["location"]
    return loc["lat"], loc["lng"]


def places_nearby_search(market, category, radius_miles=15, limit=20):
    lat, lng = geocode_market(market)
    radius_meters = max(1000, min(int(float(radius_miles) * 1609.34), 50000))

    # Text Search is usually better for prospecting queries like
    # "dentist in St. Petersburg, FL" than Nearby Search keyword matching.
    data = google_get(
        "https://maps.googleapis.com/maps/api/place/textsearch/json",
        {
            "query": f"{category} in {market}",
            "location": f"{lat},{lng}",
            "radius": radius_meters
        }
    )

    results = data.get("results", [])[:limit]
    return results


def place_details(place_id):
    fields = ",".join([
        "name",
        "formatted_address",
        "formatted_phone_number",
        "international_phone_number",
        "website",
        "rating",
        "user_ratings_total",
        "types",
        "url",
        "business_status"
    ])

    data = google_get(
        "https://maps.googleapis.com/maps/api/place/details/json",
        {
            "place_id": place_id,
            "fields": fields
        }
    )

    if data.get("status") != "OK":
        return {}

    return data.get("result", {})


def hostname_from_url(url):
    try:
        parsed = urlparse(url if url.startswith(("http://", "https://")) else "https://" + url)
        return parsed.netloc.lower().replace("www.", "")
    except Exception:
        return ""


def is_directory_or_social_site(url):
    host = hostname_from_url(url)
    if not host:
        return False

    return any(domain in host for domain in DIRECTORY_DOMAINS)


def likely_chain_business(name, website, address=""):
    blob = f"{name or ''} {website or ''} {address or ''}".lower()
    host = hostname_from_url(website or "")

    if any(hint in blob for hint in CHAIN_HINTS):
        return True

    chain_url_patterns = [
        "/locations/",
        "/location/",
        "/stores/",
        "/store-locator",
        "/find-a-location"
    ]

    if any(pattern in (website or "").lower() for pattern in chain_url_patterns):
        return True

    # Corporate-looking broad domains are not automatically chains, but this helps.
    if host and any(hint.replace(" ", "") in host for hint in CHAIN_HINTS):
        return True

    return False


def extract_city_from_address(address):
    if not address:
        return ""

    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 2:
        return parts[-3] if len(parts) >= 3 else parts[0]

    return ""


def find_contact_name_from_site(soup):
    if not soup:
        return {
            "name": "",
            "role": "",
            "confidence": "Unknown"
        }

    text = soup.get_text(" ", strip=True)
    patterns = [
        r"(?:Founder|Owner|President|Principal|CEO|Director|Practice Manager|Office Manager|General Manager)\s*[:\-–]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*,?\s*(?:Founder|Owner|President|Principal|CEO|Director|Practice Manager|Office Manager|General Manager)",
        r"(?:Dr\.|Doctor)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})"
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            role_match = re.search(r"(Founder|Owner|President|Principal|CEO|Director|Practice Manager|Office Manager|General Manager|Dr\.)", match.group(0))
            role = role_match.group(1) if role_match else "Possible contact"
            return {
                "name": name,
                "role": role,
                "confidence": "Medium"
            }

    return {
        "name": "",
        "role": "",
        "confidence": "Unknown"
    }


def scan_business_website(url):
    result = {
        "website_status": "No website found",
        "website_loads": False,
        "website_url": url or "",
        "is_directory_site": False,
        "detected_issues": [],
        "freshness_signals": [],
        "contact_name": "",
        "contact_role": "",
        "contact_confidence": "Unknown",
        "seo_score": 0,
        "website_opportunity_score": 75
    }

    if not url:
        result["detected_issues"].append("No website listed on Google Business Profile")
        result["website_opportunity_score"] = 92
        return result

    normalized = url.strip()
    if not normalized.startswith(("http://", "https://")):
        normalized = "https://" + normalized

    result["website_url"] = normalized
    result["is_directory_site"] = is_directory_or_social_site(normalized)

    if result["is_directory_site"]:
        result["website_status"] = "Directory / social page instead of full website"
        result["detected_issues"].append("Website points to a social, directory, booking, or temporary page")
        result["website_opportunity_score"] = 88
        return result

    try:
        r = fetch(normalized)
    except Exception as e:
        result["website_status"] = "Website did not load"
        result["detected_issues"].append(f"Website fetch failed: {str(e)[:90]}")
        result["website_opportunity_score"] = 86
        return result

    if r.status_code >= 400:
        result["website_status"] = f"Website returned status {r.status_code}"
        result["detected_issues"].append(f"Website returned HTTP status {r.status_code}")
        result["website_opportunity_score"] = 84
        return result

    result["website_status"] = "Website found"
    result["website_loads"] = True

    html = r.text or ""
    soup = BeautifulSoup(html, "html.parser")

    parsed = urlparse(normalized)
    https_ok = parsed.scheme.lower() == "https"

    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    md = soup.find("meta", attrs={"name": "description"})
    description = (md.get("content") or "").strip() if md else ""
    h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]
    viewport = soup.find("meta", attrs={"name": "viewport"})
    canonical = soup.find("link", attrs={"rel": "canonical"})
    schema_scripts = soup.find_all("script", attrs={"type": "application/ld+json"})

    imgs = soup.find_all("img")
    imgs_without_alt = sum(1 for im in imgs if not (im.get("alt") or "").strip())

    for t in soup(["script", "style", "noscript"]):
        t.extract()

    text = soup.get_text(separator=" ")
    words = [w for w in text.split() if w.isalpha() or any(c.isalnum() for c in w)]
    word_count = len(words)

    tel_links = soup.find_all("a", href=lambda h: h and h.lower().startswith("tel:"))
    mail_links = soup.find_all("a", href=lambda h: h and h.lower().startswith("mailto:"))
    contact_mentions = len(re.findall(r"\b(contact|quote|appointment|schedule|book|call now|request)\b", text, re.I))

    copyright_years = [int(y) for y in re.findall(r"(?:©|copyright)?\s*(20[0-2][0-9]|19[8-9][0-9])", html, re.I)]
    newest_copyright = max(copyright_years) if copyright_years else None

    if newest_copyright:
        result["freshness_signals"].append(f"Footer/copyright year detected: {newest_copyright}")
        if newest_copyright <= 2021:
            result["detected_issues"].append(f"Older copyright signal detected: {newest_copyright}")

    # Common SEO / website opportunity issues
    if not https_ok:
        result["detected_issues"].append("Website is not using HTTPS")

    if not title:
        result["detected_issues"].append("Missing title tag")

    if not description:
        result["detected_issues"].append("Missing meta description")

    if len(h1_tags) == 0:
        result["detected_issues"].append("No H1 heading found")
    elif len(h1_tags) > 1:
        result["detected_issues"].append(f"Multiple H1 headings found: {len(h1_tags)}")

    if not viewport:
        result["detected_issues"].append("Missing mobile viewport tag")

    if not canonical:
        result["detected_issues"].append("No canonical tag detected")

    if not schema_scripts:
        result["detected_issues"].append("No schema markup detected")

    if word_count < 300:
        result["detected_issues"].append(f"Thin page content detected: {word_count} words")

    if imgs_without_alt > 0:
        result["detected_issues"].append(f"{imgs_without_alt} image(s) missing ALT text")

    if not tel_links:
        result["detected_issues"].append("No clickable phone link found")

    if not mail_links:
        result["freshness_signals"].append("No mailto email link found")

    if contact_mentions < 2:
        result["detected_issues"].append("Weak or unclear call-to-action signals")

    # Check robots/sitemap
    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_ok = False
    sitemap_ok = False

    try:
        rr = requests.head(urljoin(base, "/robots.txt"), headers={"User-Agent": UA}, timeout=TIMEOUT, allow_redirects=True)
        robots_ok = rr.status_code == 200
    except Exception:
        pass

    try:
        sr = requests.head(urljoin(base, "/sitemap.xml"), headers={"User-Agent": UA}, timeout=TIMEOUT, allow_redirects=True)
        sitemap_ok = sr.status_code == 200
    except Exception:
        pass

    if not robots_ok:
        result["detected_issues"].append("robots.txt not found")

    if not sitemap_ok:
        result["detected_issues"].append("XML sitemap not found")

    # Contact name extraction
    contact = find_contact_name_from_site(soup)
    result["contact_name"] = contact["name"]
    result["contact_role"] = contact["role"]
    result["contact_confidence"] = contact["confidence"]

    # SEO-ish score for the website
    seo_score = 0
    if title:
        seo_score += 10
    if description:
        seo_score += 10
    if len(h1_tags) == 1:
        seo_score += 10
    elif len(h1_tags) > 1:
        seo_score += 4
    if https_ok:
        seo_score += 10
    if viewport:
        seo_score += 10
    if robots_ok:
        seo_score += 6
    if sitemap_ok:
        seo_score += 6
    if canonical:
        seo_score += 6
    if schema_scripts:
        seo_score += 6
    if word_count >= 800:
        seo_score += 12
    elif word_count >= 400:
        seo_score += 8
    elif word_count >= 250:
        seo_score += 4
    if len(imgs) > 0:
        alt_ratio = (len(imgs) - imgs_without_alt) / len(imgs)
        if alt_ratio >= 0.9:
            seo_score += 8
        elif alt_ratio >= 0.7:
            seo_score += 4
    if tel_links:
        seo_score += 4
    if contact_mentions >= 2:
        seo_score += 4

    seo_score = max(0, min(100, int(round(seo_score))))
    result["seo_score"] = seo_score

    # The lower the site score, the higher the opportunity score.
    issue_boost = min(len(result["detected_issues"]) * 4, 28)
    result["website_opportunity_score"] = max(15, min(100, int((100 - seo_score) + issue_boost)))

    return result


def business_quality_score(place, category, is_chain):
    rating = float(place.get("rating") or 0)
    reviews = int(place.get("user_ratings_total") or 0)
    phone = place.get("formatted_phone_number") or place.get("international_phone_number") or ""
    website = place.get("website") or ""
    category_lc = (category or "").lower()

    score = 0

    if rating >= 4.7:
        score += 25
    elif rating >= 4.4:
        score += 22
    elif rating >= 4.1:
        score += 16
    elif rating >= 3.8:
        score += 8

    if reviews >= 150:
        score += 25
    elif reviews >= 75:
        score += 21
    elif reviews >= 30:
        score += 16
    elif reviews >= 10:
        score += 9

    if phone:
        score += 15

    if website:
        score += 8

    if any(cat in category_lc for cat in HIGH_VALUE_CATEGORIES):
        score += 18
    else:
        score += 10

    if not is_chain:
        score += 12
    else:
        score -= 35

    return max(0, min(100, int(score)))


def lead_priority_label(priority, website_scan, is_chain):
    if is_chain:
        return "Possible Chain / Skip"

    if not website_scan.get("website_url"):
        return "No Website Found"

    if website_scan.get("is_directory_site"):
        return "Social / Directory Website Lead"

    if priority >= 82:
        return "Hot Refresh Lead"

    if priority >= 68:
        return "SEO Foundation Opportunity"

    if priority >= 52:
        return "Possible Website Refresh"

    return "Low Priority"


def recommended_offer_for_lead(website_scan):
    issues = " ".join(website_scan.get("detected_issues", [])).lower()

    if not website_scan.get("website_url"):
        return "Starter Website / New Website"

    if website_scan.get("is_directory_site"):
        return "Starter Website / Full Website"

    if "missing meta" in issues or "h1" in issues or "sitemap" in issues or "thin page" in issues:
        return "Website Refresh + SEO Foundation"

    if "clickable phone" in issues or "call-to-action" in issues:
        return "Conversion Cleanup + Website Refresh"

    if website_scan.get("seo_score", 0) >= 75:
        return "Maintenance + SEO Growth"

    return "Website Refresh Services"


def build_outreach_opener(place, category, market, website_scan, recommended_offer):
    name = place.get("name") or "your business"
    city = extract_city_from_address(place.get("formatted_address") or "") or market
    contact_name = website_scan.get("contact_name") or ""

    issue = "your website may not be matching the quality of your local reputation"

    detected = website_scan.get("detected_issues", [])
    if detected:
        issue = detected[0].lower()

    greeting = f"Hi {contact_name}," if contact_name else f"Hi {name} team,"

    return (
        f"{greeting} I came across {name} while looking at {category} businesses around {city}. "
        f"You already have local visibility, but I noticed {issue}. "
        f"Divi Dojo helps established small businesses refresh outdated websites, improve SEO structure, "
        f"and create clearer calls-to-action so more visitors turn into leads. "
        f"This looks like it could be a fit for {recommended_offer}."
    )


@app.route("/existing-business-leads", methods=["POST"])
def existing_business_leads():
    data = request.get_json(force=True)

    market = (data.get("market") or "St. Petersburg, FL").strip()
    category = (data.get("category") or "med spa").strip()
    radius_miles = float(data.get("radius_miles") or 15)
    min_reviews = int(data.get("min_reviews") or 20)
    min_rating = float(data.get("min_rating") or 4.0)
    exclude_chains = bool(data.get("exclude_chains", True))
    limit = int(data.get("limit") or 20)
    limit = max(1, min(limit, 20))

    if not category:
        return jsonify({"error": "Missing category"}), 400

    try:
        raw_places = places_nearby_search(market, category, radius_miles, limit=limit)
    except Exception as e:
        return jsonify({"error": f"Google Places search failed: {e}"}), 400

       leads = []
    debug = {
        "raw_places_returned": len(raw_places),
        "skipped_no_place_id": 0,
        "skipped_no_details": 0,
        "skipped_low_rating": 0,
        "skipped_low_reviews": 0,
        "skipped_chain": 0,
        "processed": 0
    }

        for item in raw_places:
        place_id = item.get("place_id")
        if not place_id:
            debug["skipped_no_place_id"] += 1
            continue

        details = place_details(place_id)
        if not details:
            debug["skipped_no_details"] += 1
            continue

        debug["processed"] += 1

        rating = float(details.get("rating") or 0)
        reviews = int(details.get("user_ratings_total") or 0)

        if rating < min_rating:
            debug["skipped_low_rating"] += 1
            continue

        if reviews < min_reviews:
            debug["skipped_low_reviews"] += 1
            continue
            
        website = details.get("website") or ""
        address = details.get("formatted_address") or ""
        name = details.get("name") or ""

        is_chain = likely_chain_business(name, website, address)

                if exclude_chains and is_chain:
            debug["skipped_chain"] += 1
            continue

        website_scan = scan_business_website(website)
        quality = business_quality_score(details, category, is_chain)
        opportunity = int(website_scan.get("website_opportunity_score") or 0)

        priority = int(round((quality * 0.52) + (opportunity * 0.48)))
        label = lead_priority_label(priority, website_scan, is_chain)
        offer = recommended_offer_for_lead(website_scan)
        opener = build_outreach_opener(details, category, market, website_scan, offer)

        lead = {
            "business_name": name,
            "category": category,
            "market": market,
            "city": extract_city_from_address(address),
            "address": address,
            "phone": details.get("formatted_phone_number") or details.get("international_phone_number") or "",
            "google_rating": rating,
            "review_count": reviews,
            "google_listing_url": details.get("url") or "",
            "website": website,
            "website_status": website_scan.get("website_status"),
            "website_loads": website_scan.get("website_loads"),
            "is_directory_site": website_scan.get("is_directory_site"),
            "small_business_confidence": "Low" if is_chain else "Medium",
            "possible_chain": is_chain,
            "contact_name": website_scan.get("contact_name"),
            "contact_role": website_scan.get("contact_role"),
            "contact_confidence": website_scan.get("contact_confidence"),
            "seo_score": website_scan.get("seo_score"),
            "business_quality_score": quality,
            "website_opportunity_score": opportunity,
            "lead_priority_score": priority,
            "priority_label": label,
            "detected_issues": website_scan.get("detected_issues", [])[:8],
            "freshness_signals": website_scan.get("freshness_signals", [])[:5],
            "recommended_offer": offer,
            "outreach_opener": opener
        }

        leads.append(lead)

        # Keep things polite and reduce API/site pressure.
        time.sleep(0.15)

    leads.sort(key=lambda x: x.get("lead_priority_score", 0), reverse=True)

        return jsonify({
        "market": market,
        "category": category,
        "radius_miles": radius_miles,
        "count": len(leads),
        "debug": debug,
        "leads": leads
    })
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
