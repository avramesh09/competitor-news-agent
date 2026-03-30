# Competitor News Agent

A small Python project that collects competitor news from the last 24 hours, filters it with OpenAI, removes duplicates, and sends a short daily email brief.

## Planned pieces

- `config/`: competitor list
- `data/`: SQLite database for previously seen articles
- `output/`: saved copy of the latest brief
- `src/`: Python scripts for fetch, filter, dedupe, brief generation, email sending, and the daily runner

## Setup

1. Create a virtual environment.
2. Install the dependencies from `requirements.txt`.
3. Copy `.env.example` to `.env` and fill in your keys later.

We will do the actual setup and coding in small steps.

## Competitor config

The file `config/competitors.json` stores the competitors we want to track.

Each competitor has:

- `name`: the company name
- `keywords`: extra search words that help find relevant news

## First fetch test

When `src/fetch_news.py` is ready, it will:

- load the competitor config
- fetch recent articles from the last 24 hours
- save the raw results to `output/latest_articles.json`

If you use the free NewsAPI plan, keep `NEWS_API_DELAY_HOURS=24` in `.env`.
That tells the script to fetch the most recent 24-hour window that NewsAPI can actually return.

To avoid burning through the free NewsAPI quota, set `NEWS_API_DAILY_REQUEST_BUDGET=25`.
The script will stop early once it reaches that limit and still save the articles it already found.

The fetch step now also has a Google News RSS fallback for every competitor.
That means if NewsAPI returns nothing or hits quota, the script will try Google News RSS for that competitor.

## Freshness step

The script `src/dedupe.py` will:

- read `output/latest_articles.json`
- remove duplicate or previously seen articles
- store seen links in `data/seen_articles.db`
- save fresh articles to `output/fresh_articles.json`

## OpenAI filter step

The script `src/filter_with_openai.py` will:

- read `output/fresh_articles.json`
- ask OpenAI which articles are truly relevant
- add `category`, `summary`, and `importance`
- save the cleaned result to `output/filtered_articles.json`

To control OpenAI usage, the filter step also supports:

- `OPENAI_MAX_ARTICLES=40`
- `OPENAI_MAX_ARTICLES_PER_COMPETITOR=2`

That keeps very large fetches from sending too many articles to OpenAI in a single run.

## Brief step

The script `src/generate_brief.py` will:

- read `output/filtered_articles.json`
- keep the most important items
- group them by competitor
- write the final brief to `output/latest_brief.md`

## Email step

The script `src/send_email.py` will:

- read `output/latest_brief.md`
- send it using SMTP
- deliver the daily brief to `EMAIL_TO`

## Daily runner

The script `src/run_daily.py` will run the whole flow in this order:

1. fetch news
2. remove duplicates and old links
3. filter with OpenAI
4. generate the brief
5. send the email

## Local scheduling

Use `run_daily.sh` for local scheduling with `cron`.

It will:

- move into the project folder
- use `.venv/bin/python` if that virtual environment exists
- run the full daily flow
- append output to `output/daily_run.log`

Example cron entry for 8:00 AM every day:

`0 8 * * * /Users/avramesh/Documents/AI Agents/Competitor-Research/run_daily.sh`

## GitHub Actions scheduling

The workflow file is `.github/workflows/daily_brief.yml`.

What it does:

- runs once a day on GitHub
- can also be run manually from the GitHub Actions page
- runs the same `src/run_daily.py` flow
- saves `data/seen_articles.db` back to the repo so seen links stay fresh across days

Important timezone note:

- GitHub Actions schedules use UTC, not your local timezone
- the workflow is currently set to `0 15 * * *`
- on March 29, 2026 in Los Angeles, that means 8:00 AM PDT
- after the fall time change, the same schedule will run at 7:00 AM PST

GitHub Secrets you need to add:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `NEWS_API_KEY`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `EMAIL_TO`
