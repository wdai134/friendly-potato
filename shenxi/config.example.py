"""Configuration template. Copy to config.py and fill in your values."""
import os
import base64

def decode_key(encoded: str) -> str:
    """Decode base64-encoded API key. Obscures keys from casual inspection only."""
    return base64.b64decode(encoded).decode("utf-8")

# API Keys — copy from .env or set directly
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "your-api-key-here")
BOCHA_API_KEY = os.getenv("BOCHA_API_KEY", "")

# SearXNG (local search engine)
SEARXNG_URL = "http://localhost:8888"

# FRP / Server
FRP_SERVER = os.getenv("FRP_SERVER", "your-server-ip")
FRP_PORT = 7000

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
