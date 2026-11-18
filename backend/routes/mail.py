import os
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template

SENDER = os.getenv("SMTP_SENDER", "")
PASSWORD = os.getenv("SMTP_PASSWORD", "")


def send_email(receiver, subject, template_name, **context):
    if not SENDER or not PASSWORD:
        raise ValueError("Set SMTP_SENDER and SMTP_PASSWORD in the Celery worker terminal.")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mail_app = Flask(__name__, template_folder=os.path.join(base_dir, "templates"))
    with mail_app.app_context():
        html = render_template(template_name, **context)

    message = MIMEText(html, "html")
    message["Subject"] = subject
    message["From"] = SENDER
    message["To"] = receiver

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
        server.starttls()
        server.login(SENDER, PASSWORD)
        server.sendmail(SENDER, receiver, message.as_string())
