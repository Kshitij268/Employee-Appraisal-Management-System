import os

# `python-dotenv` is convenient during local development, but the application
# must still start when environment variables are supplied by the operating
# system (or when the optional package has not yet been installed).
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(dotenv_path=None, override=False, *_args, **_kwargs):
        """Small dependency-free .env reader used when python-dotenv is absent."""
        path = dotenv_path or os.path.join(os.path.dirname(__file__), ".env")
        if not os.path.isfile(path):
            return False
        with open(path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and (override or key not in os.environ):
                    os.environ[key] = value
        return True

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "eams-default-secret-key-change-in-production")
    # Never expose Flask's interactive traceback unless it is explicitly enabled
    # for local development.
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")
    
    # MySQL settings
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "employee_appraisal")

    # Uploads settings
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "documents")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))  # 16 MB
    ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "png", "jpg", "jpeg"}

    # Rating boundaries
    MIN_RATING = 1.00
    MAX_RATING = 5.00

    # Promotion and performance settings
    PROMOTION_ELIGIBILITY_THRESHOLD = 4.60  # Strictly > 4.60 required
    OTP_EXPIRY_SECONDS = 120  # 2 minutes

    # SMTP Mail settings
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", os.getenv("SMTP_USERNAME", "no-reply@eams.local"))
    OTP_BYPASS_DEBUG = os.getenv("OTP_BYPASS_DEBUG", "True").lower() in ("true", "1", "yes")
