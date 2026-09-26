"""
Configuration loader.
Reads settings from environment variables (via a .env file in development).
"""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DB_PATH", "meds.db").strip()

# How often (seconds) the scheduler checks for reminders that are due.
REMINDER_CHECK_INTERVAL_SECONDS = int(os.getenv("REMINDER_CHECK_INTERVAL_SECONDS", "60"))

# Minutes after a reminder is sent before we send one gentle follow-up nudge.
FOLLOWUP_NUDGE_MINUTES = int(os.getenv("FOLLOWUP_NUDGE_MINUTES", "15"))

# Minutes after a reminder is sent, with no response, before we mark it
# "missed" and notify the linked caregiver(s).
ESCALATION_WINDOW_MINUTES = int(os.getenv("ESCALATION_WINDOW_MINUTES", "45"))

# How long (minutes) a caregiver link code stays valid.
LINK_CODE_TTL_MINUTES = int(os.getenv("LINK_CODE_TTL_MINUTES", "30"))

# --- Status / uptime notifications ---
# Telegram user ID (yours) that gets pinged when the bot starts/stops.
# Get your own ID by messaging @userinfobot on Telegram. Leave blank to disable.
_admin_id_raw = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
ADMIN_TELEGRAM_ID = int(_admin_id_raw) if _admin_id_raw.isdigit() else None

# --- "Ask a Question" (Gemini) feature ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6IYWdWx5s6cDtw5DFXCSNWbF9R8IuuSyTlgbX8mkOiheg").strip()
# gemini-3.5-flash is Google's current stable, production-recommended model
# for the generateContent endpoint as of mid-2026.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()

# Shown whenever the bot detects possible emergency/crisis language, and
# whenever it answers a question. These default to Singapore numbers —
# CHANGE THEM in .env if your users are elsewhere, or the bot will point
# someone in a real emergency to the wrong number.
EMERGENCY_NUMBER = os.getenv("EMERGENCY_NUMBER", "995 (ambulance) or 999 (police)").strip()
CRISIS_HOTLINE_NAME = os.getenv("CRISIS_HOTLINE_NAME", "Samaritans of Singapore (SOS)").strip()
CRISIS_HOTLINE_NUMBER = os.getenv("CRISIS_HOTLINE_NUMBER", "1767").strip()

# Minimum seconds between two questions from the same user, so an
# accidental double-tap or spam doesn't run up your Gemini API bill.
ASK_COOLDOWN_SECONDS = int(os.getenv("ASK_COOLDOWN_SECONDS", "20"))

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. Copy .env.example to .env and fill in your bot token "
        "(get it from @BotFather on Telegram)."
    )
