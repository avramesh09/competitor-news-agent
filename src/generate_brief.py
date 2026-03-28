import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "output" / "filtered_articles.json"
FRESH_INPUT_PATH = BASE_DIR / "output" / "fresh_articles.json"
LATEST_INPUT_PATH = BASE_DIR / "output" / "latest_articles.json"
OUTPUT_PATH = BASE_DIR / "output" / "latest_brief.md"
STATUS_PATH = BASE_DIR / "output" / "filter_status.json"
MAX_BULLETS = 8


def load_articles():
    if not INPUT_PATH.exists():
        print("Missing output/filtered_articles.json. Run python3 src/filter_with_openai.py first.")
        sys.exit(1)

    with INPUT_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_fresh_articles():
    if not FRESH_INPUT_PATH.exists():
        return []

    with FRESH_INPUT_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_latest_articles():
    if not LATEST_INPUT_PATH.exists():
        return []

    with LATEST_INPUT_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_filter_status():
    if not STATUS_PATH.exists():
        return {
            "openai_quota_exhausted": False,
            "fallback_used": False,
            "used_raw_articles_fallback": False,
            "fallback_competitors": [],
            "message": "",
        }

    with STATUS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def sort_articles(articles):
    return sorted(
        articles,
        key=lambda item: (
            -int(item.get("importance", 1)),
            item.get("date", ""),
            item.get("competitor", ""),
        ),
        reverse=False,
    )


def select_top_articles(articles):
    sorted_articles = sort_articles(articles)
    return sorted_articles[:MAX_BULLETS]


def group_by_competitor(articles):
    grouped = defaultdict(list)
    for article in articles:
        grouped[article.get("competitor", "Unknown competitor")].append(article)
    return dict(grouped)


def format_article_line(article):
    title = article.get("title", "Untitled article")
    summary = article.get("summary", "").strip()
    url = article.get("url", "").strip()
    importance = article.get("importance", 1)

    line = f"- {title} (importance: {importance})"

    if summary:
        line += f": {summary}"

    if url:
        line += f" [{url}]"

    return line


def normalize_fresh_articles(fresh_articles):
    normalized = []

    for article in fresh_articles:
        source_type = article.get("source_type", "")
        category = "official_update" if source_type == "official" else "other"
        importance = 3 if source_type == "official" else 2
        source = article.get("source", "").strip()
        title = article.get("title", "").strip()

        summary = "Fallback summary from fetched article"
        if source:
            summary += f" via {source}"
        if title:
            summary += f". Headline: {title}"

        normalized.append(
            {
                "competitor": article.get("competitor", ""),
                "title": title,
                "url": article.get("url", ""),
                "date": article.get("date", ""),
                "category": category,
                "summary": summary,
                "importance": importance,
            }
        )

    return normalized


def build_why_this_matters(articles):
    if not articles:
        return "No important competitor updates were found in the last 24 hours."

    top_competitors = []
    for article in articles:
        name = article.get("competitor", "Unknown competitor")
        if name not in top_competitors:
            top_competitors.append(name)

    names_text = ", ".join(top_competitors[:3])

    return (
        "These updates highlight where competitors are launching products, making partnerships, "
        f"or changing strategy. Today, the biggest signals came from {names_text}."
    )


def build_quota_warning(status):
    if (
        not status.get("openai_quota_exhausted")
        and not status.get("fallback_used")
        and not status.get("used_raw_articles_fallback")
    ):
        return []

    competitors = status.get("fallback_competitors", [])
    competitor_text = ", ".join(competitors) if competitors else "Unknown competitors"
    message = status.get("message", "").strip()
    if not message and status.get("used_raw_articles_fallback"):
        message = (
            "Filtered articles were empty, so this brief was built directly from fetched articles."
        )

    return [
        "## Quota Warning",
        message or "Fallback content was used for this brief.",
        f"Affected competitors: {competitor_text}",
        "",
    ]


def build_brief(articles, status):
    today = datetime.now().strftime("%Y-%m-%d")
    top_articles = select_top_articles(articles)
    grouped_articles = group_by_competitor(top_articles)

    lines = [
        f"# Competitor Morning Brief - {today}",
        "",
    ]

    lines.extend(build_quota_warning(status))

    if not top_articles:
        lines.append("No relevant competitor updates found in the last 24 hours.")
        lines.append("")
        lines.append("## Why this matters")
        lines.append("No meaningful competitor news was found today.")
        return "\n".join(lines) + "\n"

    for competitor in sorted(grouped_articles.keys()):
        lines.append(f"## {competitor}")
        for article in grouped_articles[competitor]:
            lines.append(format_article_line(article))
        lines.append("")

    lines.append("## Why this matters")
    lines.append(build_why_this_matters(top_articles))
    lines.append("")

    return "\n".join(lines)


def save_brief(brief_text):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        file.write(brief_text)


def main():
    articles = load_articles()
    status = load_filter_status()
    fresh_articles = load_fresh_articles()
    latest_articles = load_latest_articles()

    if not articles and fresh_articles:
        articles = normalize_fresh_articles(fresh_articles)
        status["used_raw_articles_fallback"] = True
        if not status.get("message"):
            status["message"] = (
                "Filtered articles were empty, so this brief was built directly from fetched articles."
            )
        if not status.get("fallback_competitors"):
            status["fallback_competitors"] = sorted(
                {
                    article.get("competitor", "Unknown competitor")
                    for article in fresh_articles
                    if article.get("competitor")
                }
            )

    if not articles and latest_articles:
        articles = normalize_fresh_articles(latest_articles)
        status["used_raw_articles_fallback"] = True
        if not status.get("message"):
            status["message"] = (
                "Fresh articles were empty, so this brief was built from the latest fetched articles, including previously seen items."
            )
        if not status.get("fallback_competitors"):
            status["fallback_competitors"] = sorted(
                {
                    article.get("competitor", "Unknown competitor")
                    for article in latest_articles
                    if article.get("competitor")
                }
            )

    brief_text = build_brief(articles, status)
    save_brief(brief_text)

    selected_count = min(len(articles), MAX_BULLETS)
    print(f"Loaded {len(articles)} filtered articles")
    print(f"Selected up to {selected_count} items for the brief")
    print(f"Saved brief to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
