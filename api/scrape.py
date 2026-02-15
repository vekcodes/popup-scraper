from http.server import BaseHTTPRequestHandler
import json
import urllib.request
import urllib.parse
import re
import ssl


# ---------------------------------------------------------------------------
# Klaviyo-specific detection patterns
# ---------------------------------------------------------------------------

KLAVIYO_SCRIPT_PATTERNS = [
    "klaviyo",
    "static.klaviyo.com",
    "klaviyo.js",
    "a.klaviyo.com",
    "fast.a.klaviyo.com",
]

KLAVIYO_HTML_PATTERNS = [
    "klaviyo-form",
    "klaviyo_modal",
    "klaviyo-popup",
    "kl-private-reset-css-Xuajs1",
    "kl-form",
    "kl_",
    "data-klaviyo",
    "klaviyo_subscribe",
    "klaviyo-bis",
    "__kla_id",
    "klOnsite",
    "KlaviyoSubscribe",
    "_klOnsite",
    "_learnq",
]


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_website(url):
    """Fetch website HTML content."""
    if not url.startswith("http"):
        url = "https://" + url

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
        return response.read().decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_klaviyo(html):
    """Detect Klaviyo presence in the page HTML."""
    html_lower = html.lower()
    matched = []

    for pattern in KLAVIYO_SCRIPT_PATTERNS:
        if pattern.lower() in html_lower:
            matched.append(f"script: {pattern}")

    for pattern in KLAVIYO_HTML_PATTERNS:
        if pattern.lower() in html_lower:
            matched.append(f"html: {pattern}")

    return matched


def detect_klaviyo_email_input(html):
    """Check if Klaviyo form blocks contain an email input field."""
    klaviyo_block_re = re.compile(
        r'<(?:div|form|section)\s[^>]*'
        r'(?:class|id|data-[\w-]+)=["\'][^"\']*'
        r'(?:klaviyo|kl-form|kl_)'
        r'[^"\']*["\']'
        r'[^>]*>'
        r'([\s\S]*?)'
        r'</(?:div|form|section)>',
        re.IGNORECASE,
    )

    email_re = re.compile(
        r'(?:type=["\']email["\']'
        r'|(?:name|id|placeholder)=["\'][^"\']*email[^"\']*["\'])',
        re.IGNORECASE,
    )

    matches = []
    for m in klaviyo_block_re.finditer(html):
        if email_re.search(m.group(0)):
            matches.append(m.group(0)[:300])
        if len(matches) >= 5:
            break
    return matches


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def detect(url):
    """Main detection — returns yes/no for Klaviyo email popup."""
    try:
        html = fetch_website(url)

        klaviyo_signals = detect_klaviyo(html)
        klaviyo_email_forms = detect_klaviyo_email_input(html)

        has_klaviyo = len(klaviyo_signals) > 0

        return {
            "success": True,
            "url": url,
            "result": "yes" if has_klaviyo else "no",
            "matched_signals": klaviyo_signals,
            "klaviyo_email_forms_found": len(klaviyo_email_forms),
            "klaviyo_email_forms": klaviyo_email_forms,
            "html_length": len(html),
        }

    except Exception as e:
        return {
            "success": False,
            "url": url,
            "result": "error",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Vercel handler
# ---------------------------------------------------------------------------

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        url = params.get("url", [None])[0]

        if not url:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Missing 'url' parameter",
                "usage": "?url=https://example.com",
            }).encode())
            return

        result = detect(url)

        self.send_response(200 if result["success"] else 500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(result, indent=2).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
