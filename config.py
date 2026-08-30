"""
Configuration management.
Loads secrets from Streamlit secrets (production) or environment variables (local dev).
"""

import os


def get_config() -> dict:
    """Load configuration from Streamlit secrets or environment variables."""
    config = {}

    # Try Streamlit secrets first (used in Streamlit Cloud deployment)
    try:
        import streamlit as st

        config["MONDAY_API_TOKEN"] = st.secrets.get("MONDAY_API_TOKEN", "")
        config["GEMINI_API_KEY"] = st.secrets.get("GEMINI_API_KEY", "")
        config["WORK_ORDERS_BOARD_ID"] = str(st.secrets.get("WORK_ORDERS_BOARD_ID", ""))
        config["DEALS_BOARD_ID"] = str(st.secrets.get("DEALS_BOARD_ID", ""))
    except Exception:
        pass

    # Fall back to environment variables (used for local dev / standalone scripts)
    for key in ["MONDAY_API_TOKEN", "GEMINI_API_KEY", "WORK_ORDERS_BOARD_ID", "DEALS_BOARD_ID"]:
        if key not in config or not config[key]:
            config[key] = os.environ.get(key, "")

    # Also try .env file for local development
    try:
        from dotenv import load_dotenv

        load_dotenv()
        for key in ["MONDAY_API_TOKEN", "GEMINI_API_KEY", "WORK_ORDERS_BOARD_ID", "DEALS_BOARD_ID"]:
            if not config.get(key):
                config[key] = os.environ.get(key, "")
    except ImportError:
        pass

    return config


# Module-level constants for convenience
MONDAY_API_URL = "https://api.monday.com/v2"
