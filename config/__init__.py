"""
Centralized configuration module.
Single source of truth for all environment variables.
"""
from pathlib import Path
from dotenv import load_dotenv
import os

# Load .env from project root
_project_root = Path(__file__).resolve().parents[1]
load_dotenv(_project_root / ".env")

# API Keys
ZYTE_API_KEY = os.getenv("ZYTE_API_KEY")

# Git Publishing
PUBLIC_REPO_URL = os.getenv(
    "PUBLIC_REPO_URL",
    "git@github.com:your_username/sentiment_data_collection.git"
)

# Email Notifications
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT")

# Data Source
USE_ANDROID_APP = os.getenv("USE_ANDROID_APP", "true").lower() == "true"

# Scheduling
SCHEDULE_RUN_SCRAPER = os.getenv("SCHEDULE_RUN_SCRAPER", "false").lower() == "true"
