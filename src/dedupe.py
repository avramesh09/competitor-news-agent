import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "output" / "latest_articles.json"
OUTPUT_PATH = BASE_DIR / "output" / "fresh_articles.json"
DATABASE_PATH = BASE_DIR / "data" / "seen_articles.db"


def normalize_title(title):
    cleaned = title.lower().strip()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def ensure_database():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            normalized_title TEXT NOT NULL,
            competitor TEXT,
            title TEXT,
            first_seen_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_seen_articles_title ON seen_articles (normalized_title)"
    )

    connection.commit()
    return connection


def load_articles():
    if not INPUT_PATH.exists():
        print("Missing output/latest_articles.json. Run python3 src/fetch_news.py first.")
        sys.exit(1)

    with INPUT_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def article_exists(cursor, url, normalized_title):
    cursor.execute(
        """
        SELECT 1
        FROM seen_articles
        WHERE url = ?
           OR normalized_title = ?
        LIMIT 1
        """,
        (url, normalized_title),
    )
    return cursor.fetchone() is not None


def filter_fresh_articles(articles, cursor):
    fresh_articles = []
    skipped_seen = 0
    skipped_duplicates = 0
    run_urls = set()
    run_titles = set()

    for article in articles:
        url = article.get("url", "").strip()
        title = article.get("title", "").strip()
        normalized_title = normalize_title(title)

        if not url or not normalized_title:
            skipped_duplicates += 1
            continue

        if url in run_urls or normalized_title in run_titles:
            skipped_duplicates += 1
            continue

        if article_exists(cursor, url, normalized_title):
            skipped_seen += 1
            continue

        run_urls.add(url)
        run_titles.add(normalized_title)
        fresh_articles.append(article)

    return fresh_articles, skipped_seen, skipped_duplicates


def save_seen_articles(connection, articles):
    cursor = connection.cursor()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for article in articles:
        cursor.execute(
            """
            INSERT OR IGNORE INTO seen_articles (
                url,
                normalized_title,
                competitor,
                title,
                first_seen_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                article.get("url", "").strip(),
                normalize_title(article.get("title", "")),
                article.get("competitor", ""),
                article.get("title", ""),
                now,
            ),
        )

    connection.commit()


def save_fresh_articles(articles):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(articles, file, indent=2)


def main():
    articles = load_articles()
    connection = ensure_database()
    cursor = connection.cursor()

    fresh_articles, skipped_seen, skipped_duplicates = filter_fresh_articles(
        articles,
        cursor,
    )

    save_seen_articles(connection, fresh_articles)
    save_fresh_articles(fresh_articles)
    connection.close()

    print(f"Loaded {len(articles)} articles")
    print(f"Removed {skipped_duplicates} duplicates from this run")
    print(f"Skipped {skipped_seen} previously seen articles")
    print(f"Kept {len(fresh_articles)} fresh articles")
    print(f"Saved fresh articles to {OUTPUT_PATH}")
    print(f"Saved seen links to {DATABASE_PATH}")


if __name__ == "__main__":
    main()
