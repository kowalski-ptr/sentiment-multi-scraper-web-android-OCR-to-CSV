"""Shared email notification module for sentiment collection system."""

import smtplib
import logging
import sys
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import EMAIL_SENDER, EMAIL_APP_PASSWORD, EMAIL_RECIPIENT


class EmailNotifier:
    def __init__(self, sender_email=None, sender_password=None, recipient_email=None):
        self.sender_email = sender_email or EMAIL_SENDER
        self.sender_password = sender_password or EMAIL_APP_PASSWORD
        self.recipient_email = recipient_email or EMAIL_RECIPIENT

    def send_email(self, subject, body):
        if not all([self.sender_email, self.sender_password, self.recipient_email]):
            logging.warning("Email credentials not configured. Skipping notification.")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.send_message(msg)
            server.quit()
            logging.info(f"Email sent successfully to {self.recipient_email}")
            return True
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
            return False
