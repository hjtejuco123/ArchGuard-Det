"""Application configuration for the baseline e-commerce backend."""

import os


class AppConfig:
    """Centralized immutable configuration container."""

    DATABASE_PATH = os.environ.get("SAMPLE_ECOM_DB", "ecommerce_baseline.db")
    SECRET_KEY = os.environ.get("SAMPLE_ECOM_SECRET", "baseline-dev-key-not-for-prod")
    TOKEN_TTL_SECONDS = 3600
    MAX_PAGE_SIZE = 100
    DEBUG = False
