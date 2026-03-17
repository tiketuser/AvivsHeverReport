import os
import json
import urllib.request
import urllib.parse
import traceback
from datetime import datetime
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

HVR_ID = os.environ["HVR_ID"]
HVR_PASSWORD = os.environ["HVR_PASSWORD"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")


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
                deals.append({"label": "🔔 " + text, "subtitle": None})

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

        if label and len(label) > 2:
            deals.append({"label": "🛒 " + label, "subtitle": subtitle, "url": href})

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

            if name:
                companies.append({
                    "name": name,
                    "category": category,
                    "online": online,
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

            addr_span = card.query_selector("div.col-8.col-lg-3 span")
            address = addr_span.inner_text().strip() if addr_span else ""

            phone_el = card.query_selector("a[href^='tel:']")
            phone = phone_el.inner_text().strip() if phone_el else ""

            hours_el = card.query_selector("div.d-none.d-lg-inline.col-lg-2 span")
            hours = hours_el.inner_text().strip() if hours_el else ""

            if name:
                restaurants.append({
                    "name": name,
                    "type": restaurant_type,
                    "address": address,
                    "phone": phone,
                    "hours": hours,
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

    # Save last_updated.json
    today_str = datetime.now().strftime("%d/%m/%Y")
    last_updated_path = os.path.join(DOCS_DIR, "last_updated.json")
    save_json(last_updated_path, {"date": today_str, "restaurant_count": len(restaurants), "company_count": len(companies)})
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
