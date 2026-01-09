#
# Copyright (c) 2025 MongoDB Inc.
# Author: Benjamin Lorenz <benjamin.lorenz@mongodb.com>
#

import datetime, pymongo, smtplib, markdown
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import keyparams

client = pymongo.MongoClient(keyparams.MONGO_URI)
news_collection = client[keyparams.MONGO_DB_NAME]["news"]
daily_collection = client[keyparams.MONGO_DB_NAME]["daily"]
print(f"Using database: {keyparams.MONGO_DB_NAME}")

formatted_date = datetime.datetime.now(datetime.UTC).strftime("%d %B %Y")

try:
    doc = daily_collection.find_one({"day": formatted_date})
    summary = doc['summary'] if doc else "No summary found."
    summary_html = markdown.markdown(summary)

    SMTP_SERVER = "localhost"
    SMTP_PORT = 587

    sender_email = "noreply@leafy.media"
    receiver_email = "istdaily"
    subject = f"leafy.media - {formatted_date}"

    msg = MIMEMultipart("alternative")
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = subject

    with open("daily-mail.html", "r", encoding="utf-8") as file:
        html_template = file.read()
    html_content = html_template.replace("{{formatted_date}}", formatted_date)
    html_content = html_content.replace("{{summary_html}}", summary_html)
    msg.attach(MIMEText(html_content, "html"))    

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.sendmail(sender_email, receiver_email, msg.as_string())

except Exception as e:
    print(f"Error: {e}")
