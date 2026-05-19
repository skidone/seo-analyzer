from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import os
import re
import time

app = Flask(__name__)

# Public launch protection:
# Only Divi Dojo should be allowed to call this API from browser-based frontend code.
CORS(app, resources={
    r"/*": {
        "origins": [
            "https://dividojo.com",
            "https://www.dividojo.com"
        ]
    }
})

# Basic fair-use protection.
# This helps prevent one person or bot from burning through PageSpeed quota.
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)
UA = "Mozilla/5.0 (compatible; DiviDojoSEO/1.0; +https://dividojo.com)"
TIMEOUT = 10
LAST_PLACES_DEBUG = {}


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

    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""

    md = soup.find("meta", attrs={"name": "description"})
    description = (md.get("content") or "").strip() if md else ""

    h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]

    for t in soup(["script", "style", "noscript"]):
        t.extract()

    text = soup.get_text(separator=" ")
    words = [w for w in text.split() if w.isalpha() or any(c.isalnum() for c in w)]
    word_count = len(words)

    imgs = soup.find_all("img")
    imgs_without_alt = sum(1 for im in imgs if not (im.get("alt") or "").strip())

    viewport = soup.find("meta", attrs={"name": "viewport"})
    viewport_ok = bool(viewport)

    https_ok = parsed.scheme.lower() == "https"

    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_ok = False
    sitemap_ok = False

    try:
        rr = requests.head(
            urljoin(base, "/robots.txt"),
            headers={"User-Agent": UA},
            timeout=TIMEOUT,
            allow_redirects=True
        )
        robots_ok = rr.status_code == 200
    except Exception:
        pass

    try:
        sr = requests.head(
            urljoin(base, "/sitemap.xml"),
            headers={"User-Agent": UA},
            timeout=TIMEOUT,
            allow_redirects=True
        )
        sitemap_ok = sr.status_code == 200
    except Exception:
        pass

    keyword_in_title = bool(keyword and title and keyword in title.lower())
    keyword_in_desc = bool(keyword and description and keyword in description.lower())
    keyword_in_h1 = bool(keyword and any(keyword in h1.lower() for h1 in h1_tags))
    keyword_in_body = bool(keyword and keyword in text.lower())

    keyword_found_in_list = []

    if keyword:
        if keyword_in_title:
            keyword_found_in_list.append("Title")
        if keyword_in_desc:
            keyword_found_in_list.append("Meta")
        if keyword_in_h1:
            keyword_found_in_list.append("H1")
        if keyword_in_body:
            keyword_found_in_list.append("Body")

    score = 0

    if title:
        score += 10
    if description:
        score += 10
    if h1_tags:
        score += 10

    if keyword_in_title:
        score += 12
    if keyword_in_desc:
        score += 6
    if keyword_in_h1:
        score += 6
    if keyword_in_body:
        score += 6

    if https_ok:
        score += 10
    if viewport_ok:
        score += 8
    if robots_ok:
        score += 6
    if sitemap_ok:
        score += 6

    if word_count >= 1200:
        score += 12
    elif word_count >= 600:
        score += 8
    elif word_count >= 300:
        score += 4

    total_imgs = len(imgs)

    if total_imgs > 0:
        covered = total_imgs - imgs_without_alt
        coverage_ratio = covered / total_imgs

        if coverage_ratio >= 0.9:
            score += 8
        elif coverage_ratio >= 0.7:
            score += 4
        elif coverage_ratio >= 0.5:
            score += 2

    seo_score = max(0, min(100, int(round(score))))

    verdict = (
        "Excellent ✅" if seo_score >= 85
        else "Good 👍" if seo_score >= 70
        else "Needs Improvement ⚠️"
    )

    def check_str(ok, yes="✅ Yes", no="❌ No"):
        return yes if ok else no

    title_field = f"✅ Present — {len(title)} chars" if title else "❌ Missing"
    desc_field = f"✅ Present — {len(description)} chars" if description else "❌ Missing"
    viewport_field = "✅ Present" if viewport_ok else "❌ Missing"
    https_field = check_str(https_ok)
    robots_field = check_str(robots_ok, yes="✅ Found", no="❌ Not Found")
    sitemap_field = check_str(sitemap_ok, yes="✅ Found", no="❌ Not Found")
    kw_where = ", ".join(keyword_found_in_list) if keyword_found_in_list else "Not Found"

    payload = {
        "URL": url,
        "SEO Score (0–100)": seo_score,
        "Verdict": verdict,
        "Estimated Monthly Visitors": "N/A",
        "Backlinks (Referring Domains)": "N/A",
        "Title": title_field,
        "Title Tag": title or "",
        "Meta Description": desc_field,
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
        raise RuntimeError(f"Could not geocode market. Status: {data.get('status')}")

    loc = data["results"][0]["geometry"]["location"]

    return loc["lat"], loc["lng"]


def places_nearby_search(market, category, radius_miles=15, limit=20):
    global LAST_PLACES_DEBUG

    key = google_api_key()

    if not key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not set")

    LAST_PLACES_DEBUG = {
        "query": f"{category} in {market}",
        "method_used": "",
        "new_location_count": 0,
        "new_no_location_count": 0,
        "legacy_count": 0,
        "legacy_status": "",
        "legacy_error_message": "",
        "last_error": ""
    }

    lat, lng = geocode_market(market)
    radius_meters = max(1000, min(int(float(radius_miles) * 1609.34), 50000))

    def convert_new_places(places):
        results = []

        for p in places:
            results.append({
                "place_id": p.get("id"),
                "_new_place_details": {
                    "name": (p.get("displayName") or {}).get("text", ""),
                    "formatted_address": p.get("formattedAddress", ""),
                    "formatted_phone_number": p.get("nationalPhoneNumber", ""),
                    "international_phone_number": p.get("internationalPhoneNumber", ""),
                    "website": p.get("websiteUri", ""),
                    "rating": p.get("rating", 0),
                    "user_ratings_total": p.get("userRatingCount", 0),
                    "types": p.get("types", []),
                    "url": p.get("googleMapsUri", ""),
                    "business_status": p.get("businessStatus", "")
                }
            })

        return results

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": (
            "places.id,"
            "places.displayName,"
            "places.formattedAddress,"
            "places.nationalPhoneNumber,"
            "places.internationalPhoneNumber,"
            "places.websiteUri,"
            "places.rating,"
            "places.userRatingCount,"
            "places.googleMapsUri,"
            "places.businessStatus,"
            "places.types"
        )
    }

    try:
        response = requests.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers=headers,
            json={
                "textQuery": f"{category} in {market}",
                "locationBias": {
                    "circle": {
                        "center": {
                            "latitude": lat,
                            "longitude": lng
                        },
                        "radius": float(radius_meters)
                    }
                },
                "maxResultCount": max(1, min(int(limit), 20))
            },
            timeout=TIMEOUT
        )

        response.raise_for_status()
        data = response.json()
        places = data.get("places", [])

        LAST_PLACES_DEBUG["new_location_count"] = len(places)

        if places:
            LAST_PLACES_DEBUG["method_used"] = "Places API New Text Search with location bias"
            return convert_new_places(places)

    except Exception as e:
        LAST_PLACES_DEBUG["last_error"] = "New location search failed: " + str(e)

    try:
        response = requests.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers=headers,
            json={
                "textQuery": f"{category} in {market}",
                "maxResultCount": max(1, min(int(limit), 20))
            },
            timeout=TIMEOUT
        )

        response.raise_for_status()
        data = response.json()
        places = data.get("places", [])

        LAST_PLACES_DEBUG["new_no_location_count"] = len(places)

        if places:
            LAST_PLACES_DEBUG["method_used"] = "Places API New Text Search without location bias"
            return convert_new_places(places)

    except Exception as e:
        LAST_PLACES_DEBUG["last_error"] = "New no-location search failed: " + str(e)

    try:
        data = google_get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            {"query": f"{category} in {market}"}
        )

        results = data.get("results", [])
        LAST_PLACES_DEBUG["legacy_count"] = len(results)
        LAST_PLACES_DEBUG["legacy_status"] = data.get("status", "")
        LAST_PLACES_DEBUG["legacy_error_message"] = data.get("error_message", "")

        if results:
            LAST_PLACES_DEBUG["method_used"] = "Legacy Text Search fallback"
            return results[:limit]

    except Exception as e:
        LAST_PLACES_DEBUG["last_error"] = "Legacy search failed: " + str(e)

    LAST_PLACES_DEBUG["method_used"] = "No method returned places"

    return []


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

    if host and any(hint.replace(" ", "") in host for hint in CHAIN_HINTS):
        return True

    return False


def extract_city_from_address(address):
    if not address:
        return ""

    parts = [p.strip() for p in address.split(",")]

    if len(parts) >= 3:
        return parts[-3]

    if len(parts) >= 1:
        return parts[0]

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
            role_match = re.search(
                r"(Founder|Owner|President|Principal|CEO|Director|Practice Manager|Office Manager|General Manager|Dr\.)",
                match.group(0)
            )
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

    copyright_years = [
        int(y) for y in re.findall(r"(?:©|copyright)?\s*(20[0-2][0-9]|19[8-9][0-9])", html, re.I)
    ]

    newest_copyright = max(copyright_years) if copyright_years else None

    if newest_copyright:
        result["freshness_signals"].append(f"Footer/copyright year detected: {newest_copyright}")

        if newest_copyright <= 2021:
            result["detected_issues"].append(f"Older copyright signal detected: {newest_copyright}")

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

    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_ok = False
    sitemap_ok = False

    try:
        rr = requests.head(
            urljoin(base, "/robots.txt"),
            headers={"User-Agent": UA},
            timeout=TIMEOUT,
            allow_redirects=True
        )
        robots_ok = rr.status_code == 200
    except Exception:
        pass

    try:
        sr = requests.head(
            urljoin(base, "/sitemap.xml"),
            headers={"User-Agent": UA},
            timeout=TIMEOUT,
            allow_redirects=True
        )
        sitemap_ok = sr.status_code == 200
    except Exception:
        pass

    if not robots_ok:
        result["detected_issues"].append("robots.txt not found")

    if not sitemap_ok:
        result["detected_issues"].append("XML sitemap not found")

    contact = find_contact_name_from_site(soup)
    result["contact_name"] = contact["name"]
    result["contact_role"] = contact["role"]
    result["contact_confidence"] = contact["confidence"]

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

        details = item.get("_new_place_details") or place_details(place_id)

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
        time.sleep(0.15)

    leads.sort(key=lambda x: x.get("lead_priority_score", 0), reverse=True)

    return jsonify({
        "market": market,
        "category": category,
        "radius_miles": radius_miles,
        "count": len(leads),
        "debug": debug,
        "places_debug": LAST_PLACES_DEBUG,
        "leads": leads
    })


# ---------- Lead capture ----------

@app.route("/lead", methods=["POST"])
def lead():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    message = (data.get("message") or "").strip()

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
                print("Brevo error:", resp.status_code, resp.text)

        except Exception as e:
            print("Brevo send exception:", e)

    return jsonify({"ok": True})


# ---------- Website Speed Checker ----------

def pagespeed_api_key():
    return os.environ.get("PAGESPEED_API_KEY", "").strip()


def normalize_speed_url(url):
    value = (url or "").strip()

    if not value:
        return ""

    if not value.startswith(("http://", "https://")):
        value = "https://" + value

    return value


def safe_score(category):
    try:
        score = category.get("score")
        if score is None:
            return None
        return int(round(float(score) * 100))
    except Exception:
        return None


def format_ms(value):
    try:
        n = float(value)
        if n >= 1000:
            return f"{n / 1000:.1f}s"
        return f"{int(round(n))}ms"
    except Exception:
        return "N/A"


def format_bytes(value):
    try:
        n = float(value)

        if n >= 1024 * 1024:
            return f"{n / (1024 * 1024):.1f} MB"

        if n >= 1024:
            return f"{n / 1024:.0f} KB"

        return f"{int(round(n))} B"
    except Exception:
        return ""


def format_wasted_ms(value):
    try:
        n = float(value)
        if n <= 0:
            return ""
        return format_ms(n)
    except Exception:
        return ""


def speed_grade(score):
    try:
        n = int(score)
    except Exception:
        return "N/A"

    if n >= 90:
        return "A"
    if n >= 75:
        return "B"
    if n >= 50:
        return "C"
    if n >= 30:
        return "D"
    return "F"


def speed_grade_label(score):
    try:
        n = int(score)
    except Exception:
        return "Not available"

    if n >= 90:
        return "Fast"
    if n >= 75:
        return "Good, with room for polish"
    if n >= 50:
        return "Needs speed cleanup"
    if n >= 30:
        return "Slow"
    return "Serious performance issue"


def get_metric_numeric(audits, key):
    audit = audits.get(key, {})
    value = audit.get("numericValue")

    try:
        return float(value)
    except Exception:
        return None


def client_load_time_from_audits(audits):
    lcp = get_metric_numeric(audits, "largest-contentful-paint")

    if lcp is None:
        return "N/A"

    return format_ms(lcp)


def plain_language_speed_summary(score, load_time, strategy):
    grade = speed_grade(score)
    device = "desktop" if strategy == "desktop" else "mobile"

    if grade == "A":
        return f"Your {device} page feels fast. The main content appears quickly, and the site has a strong performance foundation."

    if grade == "B":
        return f"Your {device} page is in good shape, but there may still be small speed wins that make the site feel lighter and more polished."

    if grade == "C":
        return f"Your {device} page loads, but it may feel slower than visitors expect. A focused cleanup can help reduce delays from scripts, CSS, images, plugins, or layout weight."

    if grade == "D":
        return f"Your {device} page is likely slow enough for visitors to notice. This may affect trust, bounce rate, and lead flow."

    if grade == "F":
        return f"Your {device} page has serious performance issues. Visitors may leave before the page fully loads or becomes easy to use."

    return f"Your {device} speed result needs review."


def format_metric_value(audit):
    if not audit:
        return "N/A"

    if audit.get("displayValue"):
        return audit.get("displayValue")

    numeric = audit.get("numericValue")

    if numeric is None:
        return "N/A"

    return format_ms(numeric)


def metric_score_status(metric_key, numeric_value):
    try:
        n = float(numeric_value)
    except Exception:
        return "neutral"

    if metric_key == "largest-contentful-paint":
        if n <= 2500:
            return "good"
        if n <= 4000:
            return "needs-work"
        return "poor"

    if metric_key == "cumulative-layout-shift":
        if n <= 0.1:
            return "good"
        if n <= 0.25:
            return "needs-work"
        return "poor"

    if metric_key == "total-blocking-time":
        if n <= 200:
            return "good"
        if n <= 600:
            return "needs-work"
        return "poor"

    if metric_key == "first-contentful-paint":
        if n <= 1800:
            return "good"
        if n <= 3000:
            return "needs-work"
        return "poor"

    if metric_key == "speed-index":
        if n <= 3400:
            return "good"
        if n <= 5800:
            return "needs-work"
        return "poor"

    return "neutral"


def audit_savings_text(audit):
    details = audit.get("details") or {}
    overall_savings_ms = details.get("overallSavingsMs")
    overall_savings_bytes = details.get("overallSavingsBytes")

    parts = []

    if overall_savings_ms:
        ms = format_wasted_ms(overall_savings_ms)
        if ms:
            parts.append(f"Potential time savings: {ms}")

    if overall_savings_bytes:
        size = format_bytes(overall_savings_bytes)
        if size:
            parts.append(f"Potential transfer savings: {size}")

    display_value = audit.get("displayValue") or ""

    if display_value and display_value not in parts:
        parts.append(display_value)

    return " · ".join(parts)


def classify_finding_severity(audit, key):
    score = audit.get("score")

    try:
        score_float = float(score)
    except Exception:
        score_float = 1

    details = audit.get("details") or {}
    savings_ms = float(details.get("overallSavingsMs") or 0)
    savings_bytes = float(details.get("overallSavingsBytes") or 0)

    high_keys = [
        "render-blocking-resources",
        "unused-javascript",
        "unused-css-rules",
        "total-blocking-time",
        "largest-contentful-paint",
        "server-response-time"
    ]

    if key in high_keys and (score_float < 0.5 or savings_ms >= 600 or savings_bytes >= 250000):
        return "high"

    if score_float < 0.5 or savings_ms >= 400 or savings_bytes >= 150000:
        return "high"

    if score_float < 0.9 or savings_ms >= 150 or savings_bytes >= 50000:
        return "medium"

    return "low"


def finding_priority_label(severity):
    if severity == "high":
        return "Fix First"

    if severity == "medium":
        return "Good Improvement"

    return "Review"


def clean_pagespeed_description(description):
    text = str(description or "")
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text[:420]


def extract_audit_examples(audit, key, max_items=5):
    details = audit.get("details") or {}
    items = details.get("items") or []

    examples = []

    for item in items[:25]:
        url = (
            item.get("url")
            or item.get("source")
            or item.get("scriptUrl")
            or item.get("node", {}).get("snippet")
            or item.get("request", {}).get("url")
            or ""
        )

        if isinstance(url, dict):
            url = url.get("url") or url.get("text") or ""

        label = "Resource"

        if "image" in key or key in ["modern-image-formats", "offscreen-images", "uses-responsive-images", "uses-webp-images"]:
            label = "Image"
        elif "css" in key or key == "render-blocking-resources":
            label = "CSS / Render-blocking resource"
        elif "javascript" in key or "bootup" in key or "mainthread" in key or "third-party" in key:
            label = "Script"
        elif "cache" in key:
            label = "Cache resource"
        elif "server-response" in key:
            label = "Server response"
        elif "dom" in key:
            label = "DOM / Page structure"

        wasted_bytes = (
            item.get("wastedBytes")
            or item.get("totalBytes")
            or item.get("transferSize")
            or item.get("resourceSize")
            or 0
        )

        wasted_ms = (
            item.get("wastedMs")
            or item.get("blockingTime")
            or item.get("duration")
            or 0
        )

        size_text = format_bytes(wasted_bytes) if wasted_bytes else ""
        time_text = format_wasted_ms(wasted_ms) if wasted_ms else ""

        extra = ""

        if item.get("cacheLifetimeMs"):
            try:
                days = round(float(item.get("cacheLifetimeMs")) / 1000 / 60 / 60 / 24, 1)
                extra = f"Cache lifetime: {days} day(s)"
            except Exception:
                pass

        if item.get("numElements"):
            extra = f"Elements: {item.get('numElements')}"

        if item.get("node") and isinstance(item.get("node"), dict):
            snippet = item.get("node", {}).get("snippet") or ""
            if snippet and not url:
                url = snippet[:180]

        if not url and item.get("group"):
            url = str(item.get("group"))

        if not url and item.get("entity"):
            entity = item.get("entity")
            if isinstance(entity, dict):
                url = entity.get("text") or entity.get("url") or ""
            else:
                url = str(entity)

        if not url:
            continue

        examples.append({
            "label": label,
            "url": str(url)[:260],
            "size": size_text,
            "time": time_text,
            "extra": extra
        })

        if len(examples) >= max_items:
            break

    return examples


def make_actual_finding(key, audit):
    title = audit.get("title") or "Performance issue found"
    description = clean_pagespeed_description(audit.get("description") or "")
    savings = audit_savings_text(audit)
    severity = classify_finding_severity(audit, key)
    priority = finding_priority_label(severity)
    examples = extract_audit_examples(audit, key)

    finding = {
        "key": key,
        "type": "general",
        "severity": severity,
        "priority": priority,
        "title": title,
        "evidence": savings,
        "plain_english": "Google found a performance item worth reviewing on this page.",
        "divi_fix": "Review the Divi page structure, modules, global sections, theme options, and any effects or embeds used on this page.",
        "wordpress_fix": "Review plugins, caching, image optimization, hosting, scripts, and whether any assets are loading on pages where they are not needed.",
        "developer_note": description,
        "displayValue": audit.get("displayValue") or "",
        "score": audit.get("score"),
        "examples": examples
    }

    image_keys = [
        "uses-optimized-images",
        "uses-webp-images",
        "uses-responsive-images",
        "modern-image-formats",
        "offscreen-images",
        "efficient-animated-content",
        "unsized-images"
    ]

    css_keys = [
        "render-blocking-resources",
        "unused-css-rules",
        "unminified-css"
    ]

    js_keys = [
        "unused-javascript",
        "unminified-javascript",
        "legacy-javascript",
        "bootup-time",
        "mainthread-work-breakdown",
        "third-party-summary",
        "total-blocking-time"
    ]

    server_keys = [
        "server-response-time",
        "uses-text-compression",
        "uses-long-cache-ttl",
        "redirects"
    ]

    layout_keys = [
        "dom-size",
        "cumulative-layout-shift",
        "layout-shift-elements",
        "largest-contentful-paint-element"
    ]

    if key in image_keys:
        finding.update({
            "type": "images",
            "plain_english": "This page has image-related speed opportunities. PageSpeed may have found oversized images, images that are not compressed enough, images not using modern formats, or images loading before they are needed.",
            "divi_fix": "Check Divi hero images, background images, gallery modules, image modules, and mobile image sizing. Large Divi background images are one of the most common speed drags.",
            "wordpress_fix": "Compress images, resize oversized uploads, use WebP/AVIF where possible, and confirm lazy loading is working for below-the-fold media.",
            "developer_note": description or "Image audit returned by PageSpeed/Lighthouse."
        })

    elif key in css_keys:
        finding.update({
            "type": "css",
            "plain_english": "CSS may be delaying how quickly the page becomes visible, or the page may be loading style files that are not needed immediately.",
            "divi_fix": "Review Divi Theme Options > Performance, especially dynamic CSS, critical CSS, and whether heavy modules/global sections are adding extra styles.",
            "wordpress_fix": "Check whether theme, builder, or plugin CSS is loading sitewide. A caching/performance plugin may help remove unused CSS or delay non-critical CSS.",
            "developer_note": description or "CSS/render-blocking audit returned by PageSpeed/Lighthouse."
        })

    elif key in js_keys:
        finding.update({
            "type": "javascript",
            "plain_english": "JavaScript may be adding delay before the page feels fully usable. This often comes from plugins, tracking scripts, animations, forms, maps, popups, sliders, or third-party widgets.",
            "divi_fix": "Audit Divi add-ons, sliders, animations, forms, popups, and any modules that load extra scripts. Delay scripts that are not needed immediately.",
            "wordpress_fix": "Review plugins loading scripts sitewide. Common culprits include forms, popups, maps, chat widgets, analytics, reviews, booking tools, and social embeds.",
            "developer_note": description or "JavaScript/main-thread audit returned by PageSpeed/Lighthouse."
        })

    elif key in server_keys:
        finding.update({
            "type": "server-cache",
            "plain_english": "The technical delivery layer may need improvement. Hosting response, compression, redirects, or browser caching can affect speed even when the page design looks fine.",
            "divi_fix": "After Divi layout cleanup, confirm the site is running with proper cache settings and that Divi static assets are being served efficiently.",
            "wordpress_fix": "Review page caching, browser caching, compression, CDN setup, redirects, hosting quality, and whether static assets have long cache lifetimes.",
            "developer_note": description or "Server/cache audit returned by PageSpeed/Lighthouse."
        })

    elif key in layout_keys:
        finding.update({
            "type": "layout",
            "plain_english": "The page structure may be creating extra browser work or visual movement. Large layouts, too many sections/modules, or unstable elements can make a page feel less smooth.",
            "divi_fix": "Simplify Divi sections/modules where possible, avoid unnecessary nested rows, reduce heavy animations, and check above-the-fold layout stability.",
            "wordpress_fix": "Review page builder output, embeds, widgets, plugin blocks, ad/tracking placements, and any elements that load late or shift the layout.",
            "developer_note": description or "Layout/DOM audit returned by PageSpeed/Lighthouse."
        })

    return finding


def extract_actual_findings(audits):
    finding_keys = [
        "render-blocking-resources",
        "unused-css-rules",
        "unused-javascript",
        "uses-optimized-images",
        "uses-webp-images",
        "uses-responsive-images",
        "efficient-animated-content",
        "modern-image-formats",
        "offscreen-images",
        "unminified-css",
        "unminified-javascript",
        "server-response-time",
        "uses-text-compression",
        "uses-long-cache-ttl",
        "third-party-summary",
        "dom-size",
        "legacy-javascript",
        "bootup-time",
        "mainthread-work-breakdown",
        "redirects",
        "unsized-images",
        "largest-contentful-paint-element",
        "layout-shift-elements"
    ]

    findings = []

    for key in finding_keys:
        audit = audits.get(key)

        if not audit:
            continue

        score = audit.get("score")

        if score is None:
            details = audit.get("details") or {}
            has_items = bool(details.get("items"))
            if not has_items:
                continue
        else:
            try:
                score_float = float(score)
            except Exception:
                score_float = 1

            if score_float >= 0.9:
                continue

        findings.append(make_actual_finding(key, audit))

    severity_order = {
        "high": 0,
        "medium": 1,
        "low": 2
    }

    findings.sort(key=lambda f: severity_order.get(f.get("severity"), 9))

    return findings[:12]


def build_speed_recommendation(mobile_score, desktop_score, findings):
    issue_blob = " ".join([
        (f.get("type", "") + " " + f.get("title", "") + " " + f.get("plain_english", ""))
        for f in findings
    ]).lower()

    low_mobile = mobile_score is not None and mobile_score < 70
    low_desktop = desktop_score is not None and desktop_score < 75

    if "images" in issue_blob:
        return {
            "title": "Divi Image Optimization + Speed Cleanup",
            "text": "The scan found image-related performance opportunities. Divi Dojo would start with hero/background images, gallery and module images, WebP conversion, compression, lazy loading, and mobile image sizing.",
            "pills": ["Image optimization", "WebP review", "Lazy loading", "Divi media cleanup"]
        }

    if "javascript" in issue_blob or "css" in issue_blob:
        return {
            "title": "Divi Asset Cleanup + Plugin Review",
            "text": "The scan found CSS or JavaScript cleanup opportunities. On Divi and WordPress sites, this usually means reviewing Divi performance settings, plugin load, render-blocking files, script delay, and unnecessary front-end weight.",
            "pills": ["Divi assets", "Plugin audit", "Script delay", "Caching setup"]
        }

    if "server-cache" in issue_blob:
        return {
            "title": "Hosting, Cache + Performance Setup",
            "text": "The scan found delivery-layer opportunities, such as cache, compression, server response, or asset lifetime. Divi Dojo would review the technical foundation before making page-level improvements.",
            "pills": ["Hosting review", "Caching", "Compression", "CDN setup"]
        }

    if low_mobile or low_desktop:
        return {
            "title": "Full Divi Performance Cleanup",
            "text": "Your site may benefit from a focused performance cleanup. Divi Dojo would review hosting, plugins, Divi assets, caching, images, scripts, layout structure, and mobile/desktop user experience.",
            "pills": ["Divi cleanup", "Plugin review", "Core Web Vitals", "Speed cleanup"]
        }

    if mobile_score is not None and mobile_score >= 85 and desktop_score is not None and desktop_score >= 85:
        return {
            "title": "Maintenance + Speed Monitoring",
            "text": "Your speed foundation looks strong. The best next step may be ongoing maintenance, performance monitoring, updates, and SEO/content growth so your site stays fast and polished.",
            "pills": ["Maintenance", "Monitoring", "Updates", "SEO growth"]
        }

    return {
        "title": "Divi Website Performance Refresh",
        "text": "Your website has room for performance polish. Divi Dojo would look at performance basics, Divi settings, plugin weight, SEO signals, mobile experience, and conversion paths together.",
        "pills": ["Divi optimization", "Mobile polish", "SEO structure", "Conversion cleanup"]
    }


def parse_pagespeed_result(data, strategy):
    lighthouse = data.get("lighthouseResult", {})
    categories = lighthouse.get("categories", {})
    audits = lighthouse.get("audits", {})

    performance = safe_score(categories.get("performance", {}))
    accessibility = safe_score(categories.get("accessibility", {}))
    best_practices = safe_score(categories.get("best-practices", {}))
    seo = safe_score(categories.get("seo", {}))

    load_time = client_load_time_from_audits(audits)
    grade = speed_grade(performance)
    grade_label = speed_grade_label(performance)
    plain_summary = plain_language_speed_summary(performance, load_time, strategy)

    metric_keys = [
        ("first-contentful-paint", "First Contentful Paint"),
        ("largest-contentful-paint", "Estimated Load Time"),
        ("total-blocking-time", "Total Blocking Time"),
        ("cumulative-layout-shift", "Layout Shift"),
        ("speed-index", "Speed Index")
    ]

    metrics = []

    for key, label in metric_keys:
        audit = audits.get(key, {})
        metrics.append({
            "key": key,
            "label": label,
            "value": format_metric_value(audit),
            "numericValue": audit.get("numericValue"),
            "status": metric_score_status(key, audit.get("numericValue"))
        })

    actual_findings = extract_actual_findings(audits)

    opportunities = []

    for finding in actual_findings:
        opportunities.append({
            "key": finding.get("key"),
            "title": finding.get("title"),
            "displayValue": finding.get("evidence"),
            "description": finding.get("plain_english"),
            "type": finding.get("type"),
            "severity": finding.get("severity"),
            "priority": finding.get("priority"),
            "examples": finding.get("examples", []),
            "divi_fix": finding.get("divi_fix", ""),
            "wordpress_fix": finding.get("wordpress_fix", ""),
            "developer_note": finding.get("developer_note", "")
        })

    return {
        "strategy": strategy,
        "performance": performance,
        "grade": grade,
        "grade_label": grade_label,
        "estimated_load_time": load_time,
        "plain_summary": plain_summary,
        "accessibility": accessibility,
        "best_practices": best_practices,
        "seo": seo,
        "metrics": metrics,
        "opportunities": opportunities[:10],
        "actual_findings": actual_findings
    }


def run_pagespeed(url, strategy):
    key = pagespeed_api_key()

    params = {
        "url": url,
        "strategy": strategy,
        "category": ["performance", "accessibility", "best-practices", "seo"]
    }

    if key:
        params["key"] = key

    response = requests.get(
        "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
        params=params,
        timeout=75
    )

    response.raise_for_status()

    return response.json()

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        "error": "Daily fair-use limit reached.",
        "message": "Divi Dojo Speed Analyzer is free to use, but daily limits help keep the tool available for everyone. Please try again later, or contact Divi Dojo if you need help reviewing your website speed."
    }), 429
    
@app.route("/speed-check", methods=["POST"])
@limiter.limit("20 per day; 5 per hour")
def speed_check():
    data = request.get_json(force=True)
    url = normalize_speed_url(data.get("url"))

    if not url:
        return jsonify({"error": "Missing URL"}), 400

    results = {}
    errors = {}

    for strategy in ["desktop", "mobile"]:
        try:
            raw = run_pagespeed(url, strategy)
            results[strategy] = parse_pagespeed_result(raw, strategy)

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "unknown"
            response_text = e.response.text[:1200] if e.response is not None else ""
            errors[strategy] = f"HTTP {status_code}: {response_text}"
            print(f"PageSpeed {strategy} error:", errors[strategy], flush=True)

        except Exception as e:
            errors[strategy] = str(e)
            print(f"PageSpeed {strategy} error:", errors[strategy], flush=True)

    if not results:
        return jsonify({
            "error": "Speed check failed for desktop and mobile.",
            "details": errors,
            "hint": "Check whether PageSpeed Insights API is enabled and whether PAGESPEED_API_KEY is valid/restricted correctly."
        }), 400

    mobile_score = results.get("mobile", {}).get("performance")
    desktop_score = results.get("desktop", {}).get("performance")

    all_findings = []

    for strategy in ["desktop", "mobile"]:
        all_findings.extend(results.get(strategy, {}).get("actual_findings", []))

    recommendation = build_speed_recommendation(mobile_score, desktop_score, all_findings)

    return jsonify({
        "url": url,
        "desktop": results.get("desktop"),
        "mobile": results.get("mobile"),
        "errors": errors,
        "recommendation": recommendation
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
