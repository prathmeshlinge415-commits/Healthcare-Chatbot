"""Central configuration. Every secret/credential comes from environment variables (.env)."""
import os
import secrets
from dotenv import load_dotenv

load_dotenv()


def _bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    # --- Security ---
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)  # random per start if unset (dev only)
    SECRET_KEY_FROM_ENV = bool(os.environ.get("SECRET_KEY"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)  # set True when served over HTTPS
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("SESSION_HOURS", "8")) * 3600
    MAX_CONTENT_LENGTH = 64 * 1024
    DEBUG = _bool("FLASK_DEBUG", False)

    # --- Database ---
    DB_BACKEND = os.environ.get("DB_BACKEND", "mysql").lower()  # "mysql" (default) or "sqlite" (tests/demo)
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "Healthcare_chat_bot")
    SQLITE_PATH = os.environ.get("SQLITE_PATH", "healthcare_demo.db")

    # --- AI (any OpenAI-compatible chat-completions API) ---
    AI_API_KEY = os.environ.get("AI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    AI_MODEL = os.environ.get("AI_MODEL", "gpt-4o-mini")
    AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT", "20"))

    # --- Local emergency / support information (set for your region) ---
    EMERGENCY_NUMBER = os.environ.get("EMERGENCY_NUMBER", "112")
    AMBULANCE_NUMBER = os.environ.get("AMBULANCE_NUMBER", "108")
    EXTRA_EMERGENCY_CONTACTS = os.environ.get("EXTRA_EMERGENCY_CONTACTS", "")  # "Label:number;Label:number"
    SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "")
    SUPPORT_PHONE = os.environ.get("SUPPORT_PHONE", "")
    SUPPORT_ADDRESS = os.environ.get("SUPPORT_ADDRESS", "")
    SUPPORT_HOURS = os.environ.get("SUPPORT_HOURS", "")

    # --- App behaviour ---
    ADMIN_EMAILS = [e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]
    SLOT_CAPACITY = int(os.environ.get("SLOT_CAPACITY", "3"))  # max bookings per specialty per time slot
    MAX_BOOKING_DAYS_AHEAD = int(os.environ.get("MAX_BOOKING_DAYS_AHEAD", "90"))
    CLINIC_START = os.environ.get("CLINIC_START", "09:00")
    CLINIC_END = os.environ.get("CLINIC_END", "17:30")
    SLOT_MINUTES = int(os.environ.get("SLOT_MINUTES", "30"))
