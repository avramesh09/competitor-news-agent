import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus
from xml.etree import ElementTree

import requests
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "competitors.json"
OUTPUT_PATH = BASE_DIR / "output" / "latest_articles.json"
LAST_SUCCESSFUL_PATH = BASE_DIR / "data" / "last_successful_articles.json"
NEWS_API_URL = "https://newsapi.org/v2/everything"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"


class NewsApiQuotaReached(Exception):
    pass


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_tracking_settings(config):
    tracking = config.get("tracking", {})
    lookback_hours = tracking.get("lookback_hours", 24)
    max_articles = tracking.get("max_articles_per_competitor", 10)
    return lookback_hours, max_articles


def get_news_api_delay_hours():
    raw_value = os.getenv("NEWS_API_DELAY_HOURS", "24").strip()

    try:
        return max(0, int(raw_value))
    except ValueError:
        print("NEWS_API_DELAY_HOURS must be a whole number")
        sys.exit(1)


def get_daily_request_budget():
    raw_value = os.getenv("NEWS_API_DAILY_REQUEST_BUDGET", "25").strip()

    try:
        return max(1, int(raw_value))
    except ValueError:
        print("NEWS_API_DAILY_REQUEST_BUDGET must be a whole number")
        sys.exit(1)


def extract_competitors(config):
    competitors = config.get("competitors", [])

    if isinstance(competitors, list):
        return competitors

    if isinstance(competitors, dict):
        all_competitors = []
        for group_name in ["tier_1_direct", "tier_2_adjacent"]:
            all_competitors.extend(competitors.get(group_name, []))
        return all_competitors

    return []


def build_search_terms(competitor):
    terms = []

    if competitor.get("name"):
        terms.append(competitor["name"])

    for key in ["keywords", "aliases"]:
        for value in competitor.get(key, []):
            if value not in terms:
                terms.append(value)

    return terms[:5]


def build_query(competitor):
    search_terms = build_search_terms(competitor)
    return " OR ".join(f'"{term}"' for term in search_terms)


def build_time_window(lookback_hours, delay_hours):
    now = datetime.now(timezone.utc)
    newest_allowed = now - timedelta(hours=delay_hours)
    oldest_allowed = newest_allowed - timedelta(hours=lookback_hours)

    return (
        oldest_allowed.isoformat(timespec="seconds"),
        newest_allowed.isoformat(timespec="seconds"),
    )


def fetch_news(query, api_key, from_time, to_time, max_articles):
    params = {
        "q": query,
        "from": from_time,
        "to": to_time,
        "sortBy": "publishedAt",
        "language": "en",
        "searchIn": "title,description",
        "pageSize": min(max_articles, 100),
        "apiKey": api_key,
    }

    for attempt in range(1, 4):
        response = requests.get(NEWS_API_URL, params=params, timeout=30)

        if response.status_code != 429:
            response.raise_for_status()
            payload = response.json()
            return payload.get("articles", [])

        if attempt == 3:
            raise NewsApiQuotaReached("NewsAPI quota or rate limit was reached.")

        retry_after = response.headers.get("Retry-After")
        wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else 5 * attempt
        print(f"NewsAPI rate limit hit. Waiting {wait_seconds} seconds before retrying...")
        time.sleep(wait_seconds)

    return []


def build_google_news_rss_url(query):
    encoded_query = quote_plus(query)
    return (
        f"{GOOGLE_NEWS_RSS_URL}?q={encoded_query}"
        "&hl=en-US&gl=US&ceid=US:en"
    )


def fetch_google_news_rss(query, max_articles):
    response = requests.get(build_google_news_rss_url(query), timeout=30)
    response.raise_for_status()

    root = ElementTree.fromstring(response.text)
    channel = root.find("channel")
    if channel is None:
        return []

    articles = []
    for item in channel.findall("item")[:max_articles]:
        source_node = item.find("source")
        articles.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "url": (item.findtext("link") or "").strip(),
                "publishedAt": (item.findtext("pubDate") or "").strip(),
                "source": {
                    "name": (source_node.text or "Google News RSS").strip()
                    if source_node is not None
                    else "Google News RSS"
                },
            }
        )

    return articles


def format_article(article, competitor_name, source_type):
    return {
        "competitor": competitor_name,
        "title": article.get("title", "").strip(),
        "url": article.get("url", "").strip(),
        "date": article.get("publishedAt", ""),
        "source": article.get("source", {}).get("name", ""),
        "source_type": source_type,
    }


def add_articles(results, seen_urls, articles, competitor_name):
    for article in articles:
        formatted = format_article(article, competitor_name, "news")
        if formatted["url"] and formatted["url"] not in seen_urls:
            seen_urls.add(formatted["url"])
            results.append(formatted)


def fetch_articles_for_competitor(
    competitor,
    api_key,
    from_time,
    to_time,
    max_articles,
    allow_rss_fallback=True,
):
    competitor_name = competitor.get("name", "Unknown competitor")
    query = build_query(competitor)
    if not query:
        return []

    seen_urls = set()
    results = []

    try:
        general_articles = fetch_news(query, api_key, from_time, to_time, max_articles)
        add_articles(results, seen_urls, general_articles, competitor_name)
    except NewsApiQuotaReached:
        if not allow_rss_fallback:
            raise
        print(f"NewsAPI was unavailable for {competitor_name}. Trying Google News RSS fallback.")

    if not results and allow_rss_fallback:
        rss_articles = fetch_google_news_rss(query, max_articles)
        add_articles(results, seen_urls, rss_articles, competitor_name)
        if results:
            print(f"Used Google News RSS fallback for: {competitor_name}")

    return results


def save_results(articles):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(articles, file, indent=2)


def save_last_successful_results(articles):
    if not articles:
        return

    LAST_SUCCESSFUL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LAST_SUCCESSFUL_PATH.open("w", encoding="utf-8") as file:
        json.dump(articles, file, indent=2)


def main():
    load_dotenv()
    api_key = os.getenv("NEWS_API_KEY")

    if not api_key or api_key == "your_news_api_key":
        print("Missing NEWS_API_KEY. Create a .env file and add your real News API key.")
        sys.exit(1)

    config = load_config()
    lookback_hours, max_articles = get_tracking_settings(config)
    delay_hours = get_news_api_delay_hours()
    request_budget = get_daily_request_budget()
    competitors = extract_competitors(config)

    if not competitors:
        print("No competitors found in config/competitors.json")
        sys.exit(1)

    from_time, to_time = build_time_window(lookback_hours, delay_hours)

    all_articles = []
    print(f"Using fetch window: {from_time} to {to_time}")
    print(f"Using NewsAPI delay setting: {delay_hours} hours")
    print(f"Using daily request budget: {request_budget}")

    requests_used = 0

    for competitor in competitors:
        if requests_used >= request_budget:
            print("Stopped early because the NewsAPI daily request budget was reached.")
            break

        competitor_name = competitor.get("name", "Unknown competitor")
        print(f"Fetching articles for: {competitor_name}")
        try:
            articles = fetch_articles_for_competitor(
                competitor,
                api_key,
                from_time,
                to_time,
                max_articles,
                allow_rss_fallback=True,
            )
        except NewsApiQuotaReached:
            print("Stopped early because NewsAPI reported that the quota or rate limit was reached.")
            break

        requests_used += 1
        print(f"Found {len(articles)} articles")
        all_articles.extend(articles)

    save_results(all_articles)
    save_last_successful_results(all_articles)
    print(f"Used {requests_used} NewsAPI requests")
    print(f"Saved {len(all_articles)} total articles to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
