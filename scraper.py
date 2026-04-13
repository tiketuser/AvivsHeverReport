import os
import sys
import json
import urllib.request
import urllib.parse
import traceback
from datetime import datetime
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

HVR_ID = os.environ["HVR_ID"]
HVR_PASSWORD = os.environ["HVR_PASSWORD"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
LOGOS_DIR = os.path.join(DOCS_DIR, "logos")


def download_logo(url):
    """Download a logo from url into docs/logos/, return relative path or empty string."""
    if not url:
        return ""
    try:
        filename = os.path.basename(urllib.parse.urlparse(url).path)
        if not filename:
            return ""
        os.makedirs(LOGOS_DIR, exist_ok=True)
        dest = os.path.join(LOGOS_DIR, filename)
        if not os.path.exists(dest):
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                with open(dest, "wb") as f:
                    f.write(resp.read())
        return f"logos/{filename}"
    except Exception:
        return url  # fall back to external URL if download fails


def send_telegram(text):
    """Send a text message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req)


def scrape_deals(page):
    """Scrape current weekly deals from the homepage."""
    page.goto("https://www.hvr.co.il/site/pg/hvr_home", wait_until="domcontentloaded")
    page.wait_for_selector("#carouselMainIndicators", timeout=20000)

    deals = []

    # 1. Carousel highlights (top banners)
    carousel_items = page.query_selector_all("#carouselMainIndicators .carousel-item")
    for item in carousel_items:
        caption = item.query_selector(".carousel-caption span")
        if caption:
            text = caption.inner_text().strip()
            if text:
                # Try to extract the carousel banner image
                img_el = item.query_selector("img")
                img_src = img_el.get_attribute("src") if img_el else None
                if img_src and img_src.startswith("/"):
                    img_src = "https://www.hvr.co.il" + img_src
                deals.append({"label": "🔔 " + text, "subtitle": None, "image": img_src})

    # 2. Weekly deals grid cards
    deal_cards = page.query_selector_all("div.col-xl-2.col-md-3.col-6")
    for card in deal_cards:
        title_el = card.query_selector(".card-box-footer-title")
        text_el = card.query_selector(".card-box-footer-text")
        title = title_el.inner_text().strip() if title_el else ""
        text = text_el.inner_text().strip() if text_el else ""
        label = title if title else text
        subtitle = text if (title and text and title != text) else None

        # Try to find a link on the card (anchor wrapping or inside)
        link_el = card.query_selector("a[href]")
        href = link_el.get_attribute("href") if link_el else None
        # Only keep external or meaningful links (skip javascript: and empty)
        if href and (href.startswith("http") or href.startswith("/")):
            if href.startswith("/"):
                href = "https://www.hvr.co.il" + href
        else:
            href = None

        # Extract deal card image
        img_el = card.query_selector("img.box-img")
        img_src = img_el.get_attribute("src") if img_el else None
        if img_src and img_src.startswith("/"):
            img_src = "https://www.hvr.co.il" + img_src

        if label and len(label) > 2:
            deals.append({"label": "🛒 " + label, "subtitle": subtitle, "url": href, "image": img_src})

    return deals


def scrape_giftcard_companies(page):
    """Scrape gift card (yellow card) supported companies."""
    page.goto("https://www.hvr.co.il/site/pg/gift_card_company", wait_until="domcontentloaded")
    page.wait_for_selector("#company-list", timeout=15000)

    companies = []
    cards = page.query_selector_all("#company-list .rounded-lg")

    for card in cards:
        try:
            name_el = card.query_selector("p.h6")
            name = name_el.inner_text().strip() if name_el else ""

            # Use mobile category text (d-xl-none) — single line with | separators
            cat_el = card.query_selector("p.d-xl-none")
            category = cat_el.inner_text().strip() if cat_el else ""

            badge_el = card.query_selector("span.online-badge")
            online = badge_el is not None and "hide" not in (badge_el.get_attribute("class") or "")

            logo_el = card.query_selector("img")
            logo_src = logo_el.get_attribute("src") if logo_el else ""
            if logo_src and logo_src.startswith("/"):
                logo_src = "https://www.hvr.co.il" + logo_src
            logo_src = download_logo(logo_src)

            if name:
                companies.append({
                    "name": name,
                    "category": category,
                    "online": online,
                    "logo": logo_src,
                })
        except Exception:
            continue

    return companies


def scrape_restaurants(page):
    """Scrape restaurant list from חבר טעמים page — click 'הצג עוד' until all loaded."""
    page.goto("https://www.hvr.co.il/site/pg/teamim_card_store", wait_until="domcontentloaded")
    page.wait_for_selector("div.col-12.bg-light.px-0.py-3.my-1", timeout=15000)

    # Click "הצג עוד" repeatedly until it's gone
    while True:
        btn = page.query_selector("button#lazy-load-btn")
        if not btn or not btn.is_visible():
            break
        btn.scroll_into_view_if_needed()
        btn.click()
        page.wait_for_timeout(1200)

    restaurants = []
    cards = page.query_selector_all("div.col-12.bg-light.px-0.py-3.my-1")

    for card in cards:
        try:
            name_el = card.query_selector("a.h5")
            name = name_el.inner_text().strip() if name_el else ""

            spans = card.query_selector_all("div.col-8.col-lg-2 span")
            restaurant_type = spans[0].inner_text().strip() if spans else ""

            # הערות (notes): text content of the notes column — all <p class="mb-2"> inside it
            # The notes column has class "col-12 col-lg-2 font-size-14" and contains free-text notes
            notes_col = card.query_selector("div.col-12.col-lg-2.font-size-14")
            if notes_col:
                p_tags = notes_col.query_selector_all("p.mb-2")
                notes_parts = [p.inner_text().strip() for p in p_tags if p.inner_text().strip()]
                notes = " | ".join(notes_parts)
            else:
                notes = ""

            # פרטים נוספים (services/delivery icons): check which icons are visible
            # Each icon is an <a> with data-original-title describing the service
            service_icons = card.query_selector_all("a[data-original-title]")
            services_parts = []
            for icon in service_icons:
                title = icon.get_attribute("data-original-title") or ""
                cls = icon.get_attribute("class") or ""
                if title and "hide" not in cls:
                    services_parts.append(title)
            services = " | ".join(services_parts)

            addr_span = card.query_selector("div.col-8.col-lg-3 span")
            address = addr_span.inner_text().strip() if addr_span else ""

            phone_el = card.query_selector("a[href^='tel:']")
            phone = phone_el.inner_text().strip() if phone_el else ""

            hours_el = card.query_selector("div.d-none.d-lg-inline.col-lg-2 span")
            hours = hours_el.inner_text().strip() if hours_el else ""

            logo_el = card.query_selector("div.col-4.col-lg-1 img")
            logo_src = logo_el.get_attribute("src") if logo_el else ""
            if logo_src and logo_src.startswith("/"):
                logo_src = "https://www.hvr.co.il" + logo_src
            logo_src = download_logo(logo_src)

            if name:
                restaurants.append({
                    "name": name,
                    "type": restaurant_type,
                    "services": services,
                    "notes": notes,
                    "address": address,
                    "phone": phone,
                    "hours": hours,
                    "logo": logo_src,
                })
        except Exception:
            continue

    return restaurants


def build_deals_message(deals):
    today = datetime.now().strftime("%d/%m/%Y")
    lines = [
        f"🛍️ *דוח שבועי - כרטיס חבר*",
        f"📅 {today}",
        "",
        "📦 *מבצעי השבוע:*",
    ]
    if deals:
        for deal in deals:
            line = f"• {deal['label']}"
            if deal.get("subtitle"):
                line += f" — {deal['subtitle']}"
            lines.append(line)
    else:
        lines.append("לא נמצאו מבצעים")
    lines.append("")
    lines.append("🌐 רשימת מסעדות מעודכנת:")
    lines.append("https://tiketuser.github.io/AvivsHeverReport")
    return "\n".join(lines)


def fetch_map_markers(page):
    """Fetch all map markers from the Hever markers API (includes lat/lng and card type)."""
    markers_data = []

    def handle_response(response):
        if "markers_hvr" in response.url:
            try:
                raw = response.text()
                parsed = json.loads(raw)
                # API returns double-encoded JSON (a JSON string containing a JSON array)
                if isinstance(parsed, str):
                    parsed = json.loads(parsed)
                if isinstance(parsed, list):
                    markers_data.extend(parsed)
            except Exception:
                pass

    page.on("response", handle_response)
    page.goto("https://www.hvr.co.il/site/pg/maps_hvr", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    page.remove_listener("response", handle_response)
    return markers_data


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    print("Starting Hever scraper...")

    os.makedirs(DOCS_DIR, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="he-IL",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("Logging in...")
        page.goto("https://www.hvr.co.il/", wait_until="domcontentloaded")
        # Save a screenshot immediately after page load for debugging
        page.screenshot(path=os.path.join(DOCS_DIR, "debug_login.png"), full_page=True)
        # Also dump the HTML so we can inspect the actual login form selectors
        html_dump = page.content()
        with open(os.path.join(DOCS_DIR, "debug_login.html"), "w", encoding="utf-8") as f:
            f.write(html_dump)
        print(f"Login page URL: {page.url}")
        print(f"Login page title: {page.title()}")
        # Log all input elements found on the page for debugging
        inputs = page.query_selector_all("input")
        print(f"Inputs found on page: {[{'name': el.get_attribute('name'), 'type': el.get_attribute('type'), 'id': el.get_attribute('id')} for el in inputs]}")
        page.wait_for_selector('input[name="tz"]', timeout=30000)
        page.fill('input[name="tz"]', HVR_ID)
        page.fill('input[name="password"]', HVR_PASSWORD)
        page.click('button.btn-hvr')
        page.wait_for_load_state("networkidle")
        print(f"After login: {page.url}")

        print("Scraping deals...")
        deals = scrape_deals(page)
        print(f"Found {len(deals)} deals")

        print("Scraping restaurants (clicking הצג עוד until all loaded)...")
        restaurants = scrape_restaurants(page)
        print(f"Found {len(restaurants)} restaurants")

        print("Scraping gift card companies...")
        companies = scrape_giftcard_companies(page)
        print(f"Found {len(companies)} gift card companies")

        print("Fetching map markers...")
        markers = fetch_map_markers(page)
        print(f"Found {len(markers)} map markers")

        browser.close()

    # Save deals to docs/deals.json
    deals_path = os.path.join(DOCS_DIR, "deals.json")
    save_json(deals_path, deals)
    print(f"Saved {len(deals)} deals to {deals_path}")

    # Save restaurants to docs/restaurants.json
    restaurants_path = os.path.join(DOCS_DIR, "restaurants.json")
    save_json(restaurants_path, restaurants)
    print(f"Saved {len(restaurants)} restaurants to {restaurants_path}")

    # Save gift card companies to docs/giftcard.json
    giftcard_path = os.path.join(DOCS_DIR, "giftcard.json")
    save_json(giftcard_path, companies)
    print(f"Saved {len(companies)} companies to {giftcard_path}")

    # Save map markers to docs/markers.json
    markers_path = os.path.join(DOCS_DIR, "markers.json")
    save_json(markers_path, markers)
    print(f"Saved {len(markers)} markers to {markers_path}")

    # Save last_updated.json
    now = datetime.now()
    today_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%H:%M")
    last_updated_path = os.path.join(DOCS_DIR, "last_updated.json")
    save_json(last_updated_path, {"date": today_str, "time": time_str, "restaurant_count": len(restaurants), "company_count": len(companies)})
    print(f"Saved last_updated.json: {today_str}, {len(restaurants)} restaurants")

    # Send weekly Telegram message with deals + website link
    deals_msg = build_deals_message(deals)
    print("Sending deals message...")
    send_telegram(deals_msg)

    print("Done!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_msg = f"❌ *שגיאה בסקריפט חבר*\n\n`{traceback.format_exc()}`"
        try:
            send_telegram(error_msg[:4096])
        except Exception:
            pass
        raise
