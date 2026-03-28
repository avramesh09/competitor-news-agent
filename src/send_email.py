import os
import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from html import escape
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
BRIEF_PATH = BASE_DIR / "output" / "latest_brief.md"


def load_brief_text():
    if not BRIEF_PATH.exists():
        print("Missing output/latest_brief.md. Run python3 src/generate_brief.py first.")
        sys.exit(1)

    return BRIEF_PATH.read_text(encoding="utf-8")


def markdown_to_html(markdown_text):
    html_parts = []
    table_lines = []

    def flush_table():
        nonlocal table_lines
        if not table_lines:
            return

        rows = []
        for line in table_lines:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows.append(cells)

        if len(rows) >= 2:
            html_parts.append("<table border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse;width:100%;'>")
            html_parts.append("<thead><tr>")
            for cell in rows[0]:
                html_parts.append(f"<th align='left'>{escape(cell)}</th>")
            html_parts.append("</tr></thead><tbody>")

            for row in rows[2:]:
                html_parts.append("<tr>")
                for index, cell in enumerate(row):
                    if index == 3 and cell.startswith("http"):
                        html_parts.append(f"<td><a href='{escape(cell)}'>Link</a></td>")
                    else:
                        html_parts.append(f"<td>{escape(cell)}</td>")
                html_parts.append("</tr>")

            html_parts.append("</tbody></table>")

        table_lines = []

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()

        if line.startswith("|") and line.endswith("|"):
            table_lines.append(line)
            continue

        flush_table()

        if not line:
            continue
        if line.startswith("# "):
            html_parts.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("## "):
            html_parts.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("- "):
            html_parts.append(f"<p>{escape(line[2:])}</p>")
        else:
            html_parts.append(f"<p>{escape(line)}</p>")

    flush_table()
    return "".join(html_parts)


def get_required_env(name):
    value = os.getenv(name, "").strip()
    if not value:
        print(f"Missing {name} in .env")
        sys.exit(1)
    return value


def build_message(brief_text, smtp_username, email_to):
    today = datetime.now().strftime("%Y-%m-%d")

    message = EmailMessage()
    message["Subject"] = f"Competitor Brief for Today - {today}"
    message["From"] = smtp_username
    message["To"] = email_to

    message.set_content(
        "Your competitor morning brief is below.\n\n"
        f"{brief_text}"
    )
    message.add_alternative(markdown_to_html(brief_text), subtype="html")

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
