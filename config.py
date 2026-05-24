"""Central configuration — loads API keys and settings."""

import os
import httpx
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# DeepSeek API
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# SSL — set CTFAGENT_SSL_VERIFY=false in .env to disable (Windows proxy/AV workaround)
SSL_VERIFY = os.getenv("CTFAGENT_SSL_VERIFY", "true").lower() not in ("false", "0", "no")

# Data
DATA_DIR = os.getenv("CTFAGENT_DATA_DIR", "data")

# Limits
MAX_ROUNDS_DEFAULT = int(os.getenv("CTFAGENT_MAX_ROUNDS", "10"))


def validate_config():
    """Validate required configuration. Raises ValueError on misconfiguration."""
    if not DEEPSEEK_API_KEY:
        raise ValueError(
            "DEEPSEEK_API_KEY is not set. "
            "Add it to your .env file: DEEPSEEK_API_KEY=sk-..."
        )
    if not DEEPSEEK_BASE_URL:
        raise ValueError(
            "DEEPSEEK_BASE_URL is not set. "
            "Set it to https://api.deepseek.com"
        )


def create_client(model: str | None = None) -> OpenAI:
    """Create an OpenAI-compatible client for DeepSeek with SSL config."""
    http_client = httpx.Client(verify=SSL_VERIFY)
    return OpenAI(
        base_url=DEEPSEEK_BASE_URL,
        api_key=DEEPSEEK_API_KEY,
        http_client=http_client,
    )
