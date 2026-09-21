import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "eams-default-secret-key-change-in-production")
    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1", "yes")
    
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
