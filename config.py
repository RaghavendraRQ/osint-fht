import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RESULTS_DIR = DATA_DIR / "results"
MODELS_DIR = DATA_DIR / "models"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# --- API Keys ---
NUMVERIFY_API_KEY = os.getenv("NUMVERIFY_API_KEY", "")
TRUECALLER_API_KEY = os.getenv("TRUECALLER_API_KEY", "")
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")
SPIDERFOOT_API_URL = os.getenv("SPIDERFOOT_API_URL", "http://127.0.0.1:5001")
SPIDERFOOT_API_KEY = os.getenv("SPIDERFOOT_API_KEY", "")

# --- Neo4j ---
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# --- Tor ---
TOR_PROXY_HOST = os.getenv("TOR_PROXY_HOST", "localhost")
TOR_PROXY_PORT = int(os.getenv("TOR_PROXY_PORT", "9050"))
TOR_SOCKS_URL = f"socks5://{TOR_PROXY_HOST}:{TOR_PROXY_PORT}"

# --- HTTP Client ---
RATE_LIMIT_DELAY = int(os.getenv("RATE_LIMIT_DELAY", "2"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
REQUEST_TIMEOUT = int(os.getenv("TIMEOUT", "10"))

# --- Scheduler ---
SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "false").lower() == "true"
SCHEDULER_INTERVAL_HOURS = int(os.getenv("SCHEDULER_INTERVAL_HOURS", "6"))

# --- GNN Model ---
GNN_ENABLED = os.getenv("GNN_ENABLED", "true").lower() == "true"
GNN_MODEL_PATH = MODELS_DIR / "graphsage_risk.pt"
GNN_HIDDEN_DIM = int(os.getenv("GNN_HIDDEN_DIM", "64"))
GNN_NUM_FEATURES = 7  # see ml/graph_features.py
GNN_LEARNING_RATE = float(os.getenv("GNN_LEARNING_RATE", "0.01"))
GNN_EPOCHS = int(os.getenv("GNN_EPOCHS", "100"))

# --- Dark Web Risk Weights ---
RISK_WEIGHTS = {
    "darkweb_mentions": 0.30,
    "cross_entity": 0.25,
    "keyword_severity": 0.30,
    "high_risk_density": 0.15,
}

KEYWORD_TIERS = {
    "critical": {
        "weight": 1.0,
        "terms": [
            "trafficking", "underage", "child exploitation", "forced labor",
            "sex trafficking", "minor", "child abuse", "sexual exploitation",
        ],
    },
    "high": {
        "weight": 0.7,
        "terms": [
            "smuggling", "slave", "passport confiscation", "visa fraud",
            "organ trade", "bonded labor", "debt bondage", "forced marriage",
        ],
    },
    "medium": {
        "weight": 0.4,
        "terms": [
            "escort", "brothel", "recruitment agency", "red light",
            "massage parlor", "nightclub", "adult services",
        ],
    },
    "low": {
        "weight": 0.2,
        "terms": [
            "massage", "services", "agency", "travel", "placement",
        ],
    },
    "india_specific": {
        "weight": 0.55,
        "terms": [
            "devadasi", "jogini", "kamathipura", "sonagachi", "gb road",
            "manpower agency", "placement agency", "red light area",
        ],
    },
}

RISK_LEVELS = [
    (0.1, "MINIMAL"),
    (0.3, "LOW"),
    (0.5, "MEDIUM"),
    (0.7, "HIGH"),
    (1.0, "CRITICAL"),
]


def get_risk_level(score: float) -> str:
    for threshold, level in RISK_LEVELS:
        if score < threshold:
            return level
    return "CRITICAL"
