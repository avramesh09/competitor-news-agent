import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "output" / "fresh_articles.json"
OUTPUT_PATH = BASE_DIR / "output" / "filtered_articles.json"
STATUS_PATH = BASE_DIR / "output" / "filter_status.json"


class OpenAIQuotaExceeded(Exception):
    pass

CATEGORIES = [
    "product_launch",
    "feature_update",
    "partnership",
    "acquisition",
    "executive_change",
    "customer_win",
    "security_event",
    "pricing",
    "funding",
    "official_update",
    "other",
]


def load_articles():
    if not INPUT_PATH.exists():
        print("Missing output/fresh_articles.json. Run python3 src/dedupe.py first.")
        sys.exit(1)

    with INPUT_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_status(status):
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATUS_PATH.open("w", encoding="utf-8") as file:
        json.dump(status, file, indent=2)


def split_into_batches(items, batch_size):
    batches = []
    for start in range(0, len(items), batch_size):
        batches.append(items[start : start + batch_size])
    return batches


def build_prompt(batch):
    prompt_articles = []

    for index, article in enumerate(batch, start=1):
        prompt_articles.append(
            {
                "id": str(index),
                "competitor": article.get("competitor", ""),
                "title": article.get("title", ""),
                "url": article.get("url", ""),
                "date": article.get("date", ""),
                "source": article.get("source", ""),
                "source_type": article.get("source_type", ""),
            }
        )

    prompt = {
        "task": (
            "Review these articles and keep only items that are clearly relevant "
            "competitor news or official company updates."
        ),
        "rules": [
            "Keep only articles that are truly about the tracked competitor.",
            "Drop generic industry news, passing mentions, opinion pieces, job posts, and stock-only updates.",
            "If you are unsure, drop the article.",
            "Use only these categories: " + ", ".join(CATEGORIES),
            "Summary must be plain English and no more than 2 short sentences.",
            "Importance must be an integer from 1 to 5.",
            "Return valid JSON.",
        ],
        "articles": prompt_articles,
        "required_output": {
            "kept_articles": [
                {
                    "id": "string",
                    "category": "string",
                    "summary": "string",
                    "importance": 1,
                }
            ]
        },
    }

    return json.dumps(prompt, indent=2)


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key":
        print("Missing OPENAI_API_KEY. Add your real OpenAI key to .env.")
        sys.exit(1)

    return OpenAI(api_key=api_key)


def get_model_name():
    model_name = os.getenv("OPENAI_MODEL", "").strip()
    if model_name:
        return model_name
    return "gpt-5-mini"


def is_quota_error(error):
    error_text = str(error).lower()
    error_repr = repr(error).lower()
    status_code = str(getattr(error, "status_code", "")).lower()
    return (
        "insufficient_quota" in error_text
        or "insufficient_quota" in error_repr
        or "exceeded your current quota" in error_text
        or "exceeded your current quota" in error_repr
        or "rate limit" in error_text
        or "rate limit" in error_repr
        or "error code: 429" in error_text
        or "error code: 429" in error_repr
        or status_code == "429"
    )


def call_openai(client, model, batch):
    try:
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful competitor news analyst. "
                        "You must respond with JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": build_prompt(batch),
                },
            ],
            text={"format": {"type": "json_object"}},
        )
    except Exception as error:
        if is_quota_error(error):
            raise OpenAIQuotaExceeded(str(error))
        print(f"OpenAI request failed: {error}")
        sys.exit(1)

    output_text = (response.output_text or "").strip()
    if not output_text:
        print("OpenAI returned an empty response.")
        sys.exit(1)

    try:
        return json.loads(output_text)
    except json.JSONDecodeError:
        print("OpenAI returned invalid JSON.")
        print(output_text[:1000])
        sys.exit(1)


def normalize_kept_articles(batch, response_data):
    kept_articles = response_data.get("kept_articles", [])
    batch_map = {str(index): article for index, article in enumerate(batch, start=1)}
    normalized = []

    for item in kept_articles:
        article_id = str(item.get("id", "")).strip()
        original = batch_map.get(article_id)

        if not original:
            continue

        category = item.get("category", "other")
        if category not in CATEGORIES:
            category = "other"

        try:
            importance = int(item.get("importance", 1))
        except (TypeError, ValueError):
            importance = 1

        importance = max(1, min(5, importance))

        normalized.append(
            {
                "competitor": original.get("competitor", ""),
                "title": original.get("title", ""),
                "url": original.get("url", ""),
                "date": original.get("date", ""),
                "category": category,
                "summary": str(item.get("summary", "")).strip(),
                "importance": importance,
            }
        )

    return normalized


def build_fallback_summary(article):
    title = article.get("title", "").strip()
    competitor = article.get("competitor", "This competitor")

    if title:
        return f"Fallback summary because OpenAI quota was exhausted. Headline: {title}"

    return f"Fallback summary because OpenAI quota was exhausted for {competitor}."


def fallback_filter_batch(batch):
    fallback_articles = []

    for article in batch:
        source_type = article.get("source_type", "")
        category = "official_update" if source_type == "official" else "other"
        importance = 3 if source_type == "official" else 2

        fallback_articles.append(
            {
                "competitor": article.get("competitor", ""),
                "title": article.get("title", ""),
                "url": article.get("url", ""),
                "date": article.get("date", ""),
                "category": category,
                "summary": build_fallback_summary(article),
                "importance": importance,
            }
        )

    return fallback_articles


def save_articles(articles):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(articles, file, indent=2)


def main():
    load_dotenv()
    articles = load_articles()

    if not articles:
        save_articles([])
        save_status(
            {
                "openai_quota_exhausted": False,
                "fallback_competitors": [],
                "message": "",
            }
        )
        print("Loaded 0 fresh articles")
        print(f"Saved 0 filtered articles to {OUTPUT_PATH}")
        return

    client = get_openai_client()
    model = get_model_name()
    batches = split_into_batches(articles, batch_size=8)

    filtered_articles = []
    quota_exhausted = False
    fallback_competitors = set()

    for index, batch in enumerate(batches, start=1):
        print(f"Filtering batch {index} of {len(batches)}")
        if quota_exhausted:
            filtered_articles.extend(fallback_filter_batch(batch))
            fallback_competitors.update(
                article.get("competitor", "Unknown competitor") for article in batch
            )
            continue

        try:
            response_data = call_openai(client, model, batch)
            filtered_articles.extend(normalize_kept_articles(batch, response_data))
        except OpenAIQuotaExceeded:
            quota_exhausted = True
            fallback_competitors.update(
                article.get("competitor", "Unknown competitor") for article in batch
            )
            filtered_articles.extend(fallback_filter_batch(batch))
            print("OpenAI quota was exhausted. Continuing with fallback summaries.")

    save_articles(filtered_articles)
    save_status(
        {
            "openai_quota_exhausted": quota_exhausted,
            "fallback_competitors": sorted(name for name in fallback_competitors if name),
            "message": (
                "OpenAI quota was exhausted during this run. "
                "The brief below includes fallback headline-based summaries for the affected competitors."
                if quota_exhausted
                else ""
            ),
        }
    )
    print(f"Loaded {len(articles)} fresh articles")
    print(f"Kept {len(filtered_articles)} relevant articles")
    print(f"Saved filtered articles to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
