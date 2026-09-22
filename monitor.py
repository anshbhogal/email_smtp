import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage


# =========================================================
# CONFIGURATION
# =========================================================

API_URL = "https://sbssugsp.ac.in/getNoticeList"

BASE_NOTICE_URL = "https://sbssugsp.ac.in/#/notice-board/"

STARTING_NOTICE_ID = 211

STATE_FILE = "state.json"


# =========================================================
# STATE
# =========================================================

def load_last_notice_id():
    """
    Read the last notice ID that has already been processed.
    """

    if not os.path.exists(STATE_FILE):
        print(
            f"{STATE_FILE} not found. "
            f"Starting from notice #{STARTING_NOTICE_ID}."
        )

        return STARTING_NOTICE_ID

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        last_id = int(data["last_notice_id"])

        return last_id

    except Exception as error:
        raise RuntimeError(
            f"Could not read {STATE_FILE}: {error}"
        )


def save_last_notice_id(notice_id):
    """
    Save the latest processed notice ID.
    GitHub Actions workflow commits this file back to GitHub.
    """

    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(
            {
                "last_notice_id": notice_id
            },
            file,
            indent=2
        )

        file.write("\n")


# =========================================================
# GET SBSSU NOTICE DATA
# =========================================================

def get_notice_data():

    request = urllib.request.Request(
        API_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/153.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        },
        method="GET",
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:

            raw = response.read().decode("utf-8")

    except Exception as error:

        raise RuntimeError(
            f"Could not contact SBSSU API: {error}"
        )

    try:

        return json.loads(raw)

    except json.JSONDecodeError as error:

        raise RuntimeError(
            f"SBSSU API did not return valid JSON: {error}"
        )


# =========================================================
# NOTICE ID
# =========================================================

def get_notice_id(notice):

    possible_keys = (
        "noticeid",
        "noticeId",
        "noticeID",
        "notice_id",
        "id",
    )

    for key in possible_keys:

        if key not in notice:
            continue

        value = notice[key]

        try:

            return int(value)

        except (ValueError, TypeError):

            continue

    return None


# =========================================================
# NOTICE TITLE
# =========================================================

def get_notice_title(notice):

    possible_keys = (
        "title",
        "noticetitle",
        "noticeTitle",
        "notice_title",
        "name",
        "subject",
    )

    for key in possible_keys:

        value = notice.get(key)

        if value is not None:

            value = str(value).strip()

            if value:
                return value

    return "New SBSSU Notice"


# =========================================================
# RECURSIVELY FIND NOTICE RECORDS
# =========================================================

def find_notice_records(data):
    """
    Recursively searches the API response for dictionaries
    containing a notice ID.

    This allows the script to handle different JSON structures.
    """

    records = []

    def walk(value):

        if isinstance(value, dict):

            notice_id = get_notice_id(value)

            if notice_id is not None:
                records.append(value)

            for child in value.values():
                walk(child)

        elif isinstance(value, list):

            for child in value:
                walk(child)

    walk(data)

    # Remove duplicate records while preserving order.
    unique_records = []
    seen_ids = set()

    for record in records:

        notice_id = get_notice_id(record)

        if notice_id is None:
            continue

        if notice_id in seen_ids:
            continue

        seen_ids.add(notice_id)
        unique_records.append(record)

    return unique_records


# =========================================================
# SEND EMAIL
# =========================================================

def send_email(notice):

    gmail_user = os.environ.get("GMAIL_USERNAME")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("EMAIL_TO")

    if not gmail_user:
        raise RuntimeError(
            "GMAIL_USERNAME secret is missing."
        )

    if not gmail_password:
        raise RuntimeError(
            "GMAIL_APP_PASSWORD secret is missing."
        )

    if not recipient:
        raise RuntimeError(
            "EMAIL_TO secret is missing."
        )

    notice_id = get_notice_id(notice)

    if notice_id is None:
        raise RuntimeError(
            "Cannot send email because notice ID is missing."
        )

    title = get_notice_title(notice)

    notice_url = BASE_NOTICE_URL + str(notice_id)

    message = EmailMessage()

    message["Subject"] = (
        f"🔔 New SBSSU Notice #{notice_id}"
    )

    message["From"] = gmail_user
    message["To"] = recipient

    message.set_content(
        f"""
A new notice has been uploaded on SBSSU.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SBSSU NOTICE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Notice ID:
#{notice_id}

Title:
{title}

Open the notice:
{notice_url}

SBSSU Notice Board:
https://www.sbssugsp.ac.in/#/notice-board/{notice_id}

This notification was generated automatically by
the SBSSU Notice Monitor.
"""
    )

    print(
        f"Connecting to Gmail SMTP..."
    )

    with smtplib.SMTP(
        "smtp.gmail.com",
        587,
        timeout=30
    ) as smtp:

        smtp.ehlo()

        smtp.starttls()

        smtp.ehlo()

        smtp.login(
            gmail_user,
            gmail_password
        )

        smtp.send_message(message)

    print(
        f"Email successfully sent for notice #{notice_id}"
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 60)
    print("SBSSU NOTICE MONITOR")
    print("=" * 60)

    # -----------------------------------------------------
    # Load previous state
    # -----------------------------------------------------

    last_id = load_last_notice_id()

    print(
        f"Last processed notice: #{last_id}"
    )

    # -----------------------------------------------------
    # Get current SBSSU data
    # -----------------------------------------------------

    print(
        "Checking SBSSU API..."
    )

    data = get_notice_data()

    # -----------------------------------------------------
    # Extract notices
    # -----------------------------------------------------

    records = find_notice_records(data)

    if not records:

        raise RuntimeError(
            "No notice records were found in the SBSSU API response."
        )

    # -----------------------------------------------------
    # Sort notices by ID
    # -----------------------------------------------------

    notices = []

    for notice in records:

        notice_id = get_notice_id(notice)

        if notice_id is not None:

            notices.append(
                (notice_id, notice)
            )

    notices.sort(
        key=lambda item: item[0]
    )

    latest_id = notices[-1][0]

    print(
        f"Latest SBSSU notice found: #{latest_id}"
    )

    # -----------------------------------------------------
    # No new notice
    # -----------------------------------------------------

    if latest_id <= last_id:

        print(
            "No new notice."
        )

        print("=" * 60)

        return

    # -----------------------------------------------------
    # Find all unseen notices
    # -----------------------------------------------------

    new_notices = [
        notice
        for notice_id, notice in notices
        if notice_id > last_id
    ]

    print(
        f"Found {len(new_notices)} new notice(s)."
    )

    # -----------------------------------------------------
    # Send notifications
    # -----------------------------------------------------

    for notice in new_notices:

        notice_id = get_notice_id(notice)

        title = get_notice_title(notice)

        print()
        print(
            f"New notice detected:"
        )
        print(
            f"ID: #{notice_id}"
        )
        print(
            f"Title: {title}"
        )

        send_email(notice)

    # -----------------------------------------------------
    # Update state ONLY after all emails succeed
    # -----------------------------------------------------

    save_last_notice_id(latest_id)

    print()
    print(
        f"State updated to notice #{latest_id}."
    )

    print("=" * 60)


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()