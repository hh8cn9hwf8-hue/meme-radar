import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

CHECK_INTERVAL = 60
SEARCHES = [
    "Elon Musk",
    "Donald Trump",
    "Trump crypto",
    "Elon Musk crypto",
    "Bitcoin crypto breaking",
    "Solana crypto breaking",
    "celebrity death breaking",
    "actor death breaking",
    "singer death breaking",
    "crypto breaking news",
]
SEEN = set()

def google_news_url(query):
    encoded = urllib.parse.quote(query)
    return (
        "https://news.google.com/rss/search?q="
        + encoded
        + "&hl=en-US&gl=US&ceid=US:en"
    )
  def fetch_news(query):
    url = google_news_url(query)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        data = response.read()

    root = ET.fromstring(data)
    return root.findall(".//item")
    def get_text(item, tag):
    element = item.find(tag)
    if element is None or element.text is None:
        return ""
    return element.text.strip()
    def article_data(item):
    return {
        "title": get_text(item, "title"),
        "link": get_text(item, "link"),
        "pubDate": get_text(item, "pubDate"),
    }
    def telegram_send(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram non configuré")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": "true",
    }).encode()

    urllib.request.urlopen(url, data=data, timeout=15).read()
def make_key(article):
    return article["title"] + "|" + article["link"]


def scan_once():
    alerts = []

    for query in SEARCHES:
        try:
            items = fetch_news(query)

            for item in items[:10]:
                article = article_data(item)
                key = make_key(article)

                if key in SEEN:
                    continue

                SEEN.add(key)

                if article["title"]:
                    alerts.append(article)

        except Exception as exc:
            print(f"Erreur pour {query}: {exc}")

    return alerts
def format_message(article):
    return (
        "🚨 MEME RADAR\n\n"
        f"{article['title']}\n\n"
        f"Publié : {article['pubDate']}\n"
        f"Source : {article['link']}"
    )


def main():
    print("Meme Radar démarré")

    while True:
        alerts = scan_once()

        for article in alerts:
            telegram_send(format_message(article))

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
