import os
import json
import re
import smtplib
import urllib.request
from email.message import EmailMessage


API_URL = "https://sbssugsp.ac.in/getNoticeList"
BASE_NOTICE_URL = "https://sbssugsp.ac.in/#/notice-board/"

STARTING_NOTICE_ID = 211

STATE_FILE = "state.json"


# ---------------------------------------------------------
# STATE
# ---------------------------------------------------------

def load_last_notice_id():
    """
    GitHub Actions does not preserve the filesystem between runs,
    so this file is only useful when running locally.

    In GitHub Actions, the previous ID is stored in the repository
    using GitHub Actions cache/artifact or, more simply, as a
    repository variable/state mechanism.

    For the first implementation, we use the GitHub cache.
    """

    if not os.path.exists(STATE_FILE):
        return STARTING_NOTICE_ID

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return int(data["last_notice_id"])

    except Exception:
        return STARTING_NOTICE_ID


def save_last_notice_id(notice_id):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"last_notice_id": notice_id},
            f,
            indent=2
        )


# ---------------------------------------------------------
# GET SBSSU DATA
# ---------------------------------------------------------

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
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")

    return json.loads(raw)


# ---------------------------------------------------------
# FIND NOTICE RECORDS
# ---------------------------------------------------------

def extract_notice_records(data):

    if isinstance(data, list):
        return data

    if isinstance(data, dict):

        # Common API structures
        for key in (
            "data",
            "result",
            "results",
            "noticeList",
            "notices",
            "records",
        ):
            value = data.get(key)

            if isinstance(value, list):
                return value

        # Search nested dictionaries
        for value in data.values():

            if isinstance(value, list):
                if any(isinstance(x, dict) for x in value):
                    return value

    return []


# ---------------------------------------------------------
# FIND NOTICE ID
# ---------------------------------------------------------

def get_notice_id(notice):

    for key in (
        "noticeid",
        "noticeId",
        "notice_id",
        "id",
    ):

        if key in notice:

            try:
                return int(notice[key])
            except:
                pass

    return None


# ---------------------------------------------------------
# GET TITLE
# ---------------------------------------------------------

def get_notice_title(notice):

    for key in (
        "title",
        "noticetitle",
        "noticeTitle",
        "name",
        "subject",
    ):

        value = notice.get(key)

        if value:
            return str(value)

    return "New SBSSU Notice"


# ---------------------------------------------------------
# EMAIL
# ---------------------------------------------------------

def send_email(notice):

    gmail_user = os.environ["GMAIL_USERNAME"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["EMAIL_TO"]

    notice_id = get_notice_id(notice)
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

Notice ID:
{notice_id}

Title:
{title}

Open the notice:
{notice_url}

SBSSU Notice Board:
https://www.sbssugsp.ac.in/#/notice-board/{notice_id}

This notification was generated automatically.
"""
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


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    print("Checking SBSSU Notice Board...")

    last_id = load_last_notice_id()

    print(f"Last known notice: {last_id}")

    data = get_notice_data()

    records = extract_notice_records(data)

    if not records:
        raise RuntimeError(
            "Could not find notice records in API response."
        )

    notices = []

    for notice in records:

        if not isinstance(notice, dict):
            continue

        notice_id = get_notice_id(notice)

        if notice_id is not None:
            notices.append(
                (notice_id, notice)
            )

    if not notices:
        raise RuntimeError(
            "No notice IDs found in API response."
        )

    notices.sort(
        key=lambda x: x[0]
    )

    latest_id = notices[-1][0]

    print(f"Latest SBSSU notice: {latest_id}")

    # -----------------------------------------------------
    # NO NEW NOTICE
    # -----------------------------------------------------

    if latest_id <= last_id:

        print("No new notice.")

        return

    # -----------------------------------------------------
    # NEW NOTICE(S)
    # -----------------------------------------------------

    new_notices = [
        notice
        for notice_id, notice in notices
        if notice_id > last_id
    ]

    print(
        f"Found {len(new_notices)} new notice(s)."
    )

    for notice in new_notices:

        notice_id = get_notice_id(notice)

        print(
            f"Sending notification for notice #{notice_id}"
        )

        send_email(notice)

    save_last_notice_id(latest_id)

    print(
        f"Monitoring position updated to {latest_id}."
    )


if __name__ == "__main__":
    main()