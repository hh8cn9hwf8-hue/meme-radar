import os
import re
import time
import html
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher


BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

CHECK_INTERVAL = 60
NEWS_MAX_AGE_MINUTES = 15
STARTUP_MAX_AGE_MINUTES = 3

MAX_ALERTS_PER_SCAN = 5
SIMILARITY_THRESHOLD = 0.74

FIRST_SCAN = True
SEEN_KEYS = set()
RECENT_TITLES = []


SEARCHES = [
    (
        "🚨 ELON",
        '"Elon Musk" (announces OR launches OR dies OR arrested OR resigns OR viral OR meme)'
    ),
    (
        "🚨 TRUMP",
        '"Donald Trump" (announces OR launches OR arrested OR resigns OR crypto OR viral OR meme)'
    ),
    (
        "🔥 CRYPTO",
        '(Bitcoin OR Solana OR Ethereum OR crypto) '
        '(breaking OR approved OR banned OR hack OR hacked OR exploit OR listing OR listed OR launch)'
    ),
    (
        "🔥 EXCHANGE",
        '(Binance OR Coinbase OR Kraken OR Bybit) '
        '(listing OR listed OR hack OR hacked OR exploit OR launch OR announces)'
    ),
    (
        "🔥 SOLANA",
        '(Solana OR pump.fun OR PumpSwap) '
        '(meme OR memecoin OR viral OR launch OR launches OR breaking)'
    ),
    (
        "⭐ CELEBRITY",
        '(celebrity OR actor OR actress OR singer OR rapper OR athlete OR billionaire) '
        '(dies OR dead OR death OR killed OR arrested OR resigns OR hospitalized)'
    ),
    (
        "⭐ CELEBRITY",
        '"breaking news" (actor OR actress OR singer OR rapper OR celebrity)'
    ),
    (
        "🔥 VIRAL MEME",
        '"viral meme" OR "new meme" OR "internet meme" OR "going viral"'
    ),
    (
        "🔥 VIRAL",
        '(TikTok OR Reddit OR Instagram) '
        '("going viral" OR "viral meme" OR "viral character" OR "viral animal")'
    ),
    (
        "🔥 MEMECOIN",
        '"new memecoin" OR "new meme coin" OR "viral memecoin" OR "pump.fun"'
    ),
]


def utc_now():
    return datetime.now(timezone.utc)


def parse_rss_date(value):
    try:
        dt = parsedate_to_datetime(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception:
        return None


def age_minutes(dt):
    if dt is None:
        return 999999

    seconds = (utc_now() - dt).total_seconds()

    return max(0, int(seconds / 60))


def clean_title(title):
    title = html.unescape(title or "")
    title = re.sub(r"\s+", " ", title).strip()

    title = re.sub(
        r"\s+-\s+[^-]{1,80}$",
        "",
        title,
    ).strip()

    return title


def normalize_text(text):
    text = clean_title(text).lower()

    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^a-z0-9à-ÿ ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def stable_key(title):
    normalized = normalize_text(title)
    words = normalized.split()

    return " ".join(words[:18])


def is_duplicate_event(title):
    normalized = normalize_text(title)

    if not normalized:
        return True

    if len(RECENT_TITLES) > 250:
        del RECENT_TITLES[:100]

    for previous in RECENT_TITLES:

        ratio = SequenceMatcher(
            None,
            normalized,
            previous,
        ).ratio()

        if ratio >= SIMILARITY_THRESHOLD:
            return True

    RECENT_TITLES.append(normalized)

    return False


def event_score(title, category):
    text = normalize_text(title)
    score = 0

    strong = [
        "dies",
        "dead",
        "death",
        "killed",
        "arrested",
        "resigns",
        "resigned",
        "approved",
        "banned",
        "hack",
        "hacked",
        "exploit",
        "launches",
        "launched",
        "listing",
        "listed",
        "unexpected",
        "emergency",
    ]

    medium = [
        "announces",
        "announced",
        "breaking",
        "viral",
        "meme",
        "memecoin",
        "surges",
        "soars",
    ]

    for word in strong:
        if word in text:
            score += 3

    for word in medium:
        if word in text:
            score += 2

    if "ELON" in category or "TRUMP" in category:
        score += 2

    if "VIRAL" in category or "MEME" in category:
        score += 2

    if "CELEBRITY" in category:
        score += 2

    return score


def alert_level(score):
    if score >= 8:
        return "🚨 CRITICAL"

    if score >= 5:
        return "🔥 HOT"

    return "👀 EARLY"


def google_news_url(query):
    encoded = urllib.parse.quote(query)

    return (
        "https://news.google.com/rss/search"
        "?q="
        + encoded
        + "%20when:1h"
        + "&hl=en-US"
        + "&gl=US"
        + "&ceid=US:en"
    )


def fetch_news(query):
    request = urllib.request.Request(
        google_news_url(query),
        headers={
            "User-Agent": "Mozilla/5.0 MemeRadar/1.0"
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=15,
    ) as response:
        data = response.read()

    root = ET.fromstring(data)

    return root.findall(".//item")


def rss_text(item, tag):
    element = item.find(tag)

    if element is None or element.text is None:
        return ""

    return element.text.strip()


def telegram_send(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram non configuré")
        return

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    data = urllib.parse.urlencode(
        {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode()

    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=15,
    ) as response:
        response.read()


def format_message(
    category,
    title,
    link,
    age,
    score,
):
    safe_title = html.escape(title)

    safe_link = html.escape(
        link,
        quote=True,
    )

    return (
        f"{alert_level(score)}  "
        f"<b>{html.escape(category)}</b>\n\n"
        f"<b>{safe_title}</b>\n\n"
        f"⚡ Publié il y a ~{age} min\n"
        f"🎯 Score signal : {score}/10+\n"
        f'<a href="{safe_link}">'
        f"🔗 Lire la source</a>"
    )


def scan_once():
    global FIRST_SCAN

    candidates = []

    for category, query in SEARCHES:

        try:
            items = fetch_news(query)

            for item in items[:15]:

                title = clean_title(
                    rss_text(
                        item,
                        "title",
                    )
                )

                link = rss_text(
                    item,
                    "link",
                )

                published = parse_rss_date(
                    rss_text(
                        item,
                        "pubDate",
                    )
                )

                if not title or not link or published is None:
                    continue

                age = age_minutes(
                    published
                )

                if FIRST_SCAN:
                    max_age = STARTUP_MAX_AGE_MINUTES

                else:
                    max_age = NEWS_MAX_AGE_MINUTES

                if age > max_age:
                    continue

                key = stable_key(
                    title
                )

                if not key:
                    continue

                if key in SEEN_KEYS:
                    continue

                SEEN_KEYS.add(key)

                score = event_score(
                    title,
                    category,
                )

                if score < 4:
                    continue

                candidates.append(
                    {
                        "category": category,
                        "title": title,
                        "link": link,
                        "age": age,
                        "score": score,
                    }
                )

        except Exception as exc:
            print(
                f"Erreur source {category}: {exc}"
            )

    candidates.sort(
        key=lambda item: (
            -item["score"],
            item["age"],
        )
    )

    sent = 0

    for item in candidates:

        if sent >= MAX_ALERTS_PER_SCAN:
            break

        if is_duplicate_event(
            item["title"]
        ):
            continue

        try:
            telegram_send(
                format_message(
                    item["category"],
                    item["title"],
                    item["link"],
                    item["age"],
                    item["score"],
                )
            )

            print(
                "ALERTE:",
                item["title"],
            )

            sent += 1

        except Exception as exc:
            print(
                "Erreur Telegram:",
                exc,
            )

    FIRST_SCAN = False


def main():
    print(
        "🚀 Meme Radar Ultra Fresh démarré"
    )

    while True:

        try:
            scan_once()

        except Exception as exc:
            print(
                "Erreur générale:",
                exc,
            )

        time.sleep(
            CHECK_INTERVAL
        )


if __name__ == "__main__":
    main()
