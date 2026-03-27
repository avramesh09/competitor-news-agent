import os
import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
BRIEF_PATH = BASE_DIR / "output" / "latest_brief.md"


def load_brief_text():
    if not BRIEF_PATH.exists():
        print("Missing output/latest_brief.md. Run python3 src/generate_brief.py first.")
        sys.exit(1)

    return BRIEF_PATH.read_text(encoding="utf-8")


def get_required_env(name):
    value = os.getenv(name, "").strip()
    if not value:
        print(f"Missing {name} in .env")
        sys.exit(1)
    return value


def build_message(brief_text, smtp_username, email_to):
    today = datetime.now().strftime("%Y-%m-%d")

    message = EmailMessage()
    message["Subject"] = f"Competitor Morning Brief - {today}"
    message["From"] = smtp_username
    message["To"] = email_to

    message.set_content(
        "Your competitor morning brief is below.\n\n"
        f"{brief_text}"
    )

    return message


def send_email(message, smtp_host, smtp_port, smtp_username, smtp_password):
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(message)


def main():
    load_dotenv()

    brief_text = load_brief_text()
    smtp_host = get_required_env("SMTP_HOST")
    smtp_port = get_required_env("SMTP_PORT")
    smtp_username = get_required_env("SMTP_USERNAME")
    smtp_password = get_required_env("SMTP_PASSWORD")
    email_to = get_required_env("EMAIL_TO")

    try:
        smtp_port = int(smtp_port)
    except ValueError:
        print("SMTP_PORT must be a number")
        sys.exit(1)

    message = build_message(brief_text, smtp_username, email_to)
    send_email(message, smtp_host, smtp_port, smtp_username, smtp_password)

    print(f"Loaded brief from {BRIEF_PATH}")
    print(f"Sent email to {email_to}")


if __name__ == "__main__":
    main()
