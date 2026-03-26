# config.py  —  single source of truth for the entire project
# All other files import from here. No hardcoded paths anywhere else.

import sys
from pathlib import Path
import os

# Add parent directory to sys.path so relative imports work
sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import get_logger

logger = get_logger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────
# Override any of these with environment variables for portability across machines
BASE_DATA_DIR   = Path(os.getenv("LOGRESP_DATA",   r"C:\Users\Student\Downloads"))
FINAL_DATASETS  = BASE_DATA_DIR / "FINAL_DATASETS"
BETH_DATASET    = BASE_DATA_DIR / "BETH dataset"
THEIA_DATASET   = BASE_DATA_DIR / "Theia Complete" / "theia"
MODEL_DIR       = BASE_DATA_DIR

logger.debug("[Config] BASE_DATA_DIR=%s (source: %s)", BASE_DATA_DIR,
            "env var" if "LOGRESP_DATA" in os.environ else "default")

# Dataset splits
BETH_SPLITS = {
    "training":   BETH_DATASET / "labelled_training_data.csv",
    "validation": BETH_DATASET / "labelled_validation_data.csv",
    "testing":    BETH_DATASET / "labelled_testing_data.csv",
}
BETH_OUTPUT_DIR   = BASE_DATA_DIR / "LogMEND_BETH_Splits"
THEIA_OUTPUT_DIR  = BASE_DATA_DIR / "LogMEND_Theia_Splits"
THEIA_SPLITS_DIR  = BASE_DATA_DIR / "Theia_E5_Prototype_Files"

# GNN model artifact
GNN_MODEL_PATH   = MODEL_DIR / "ocr_apt_model.pth"
BENIGN_GRAPH_PT  = MODEL_DIR / "benign_graph.pt"

# ── Neo4j ─────────────────────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI",  "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASS", "test2-beth123")
BETH_JSON_DIR  = Path(os.getenv("BETH_JSON_DIR", r"C:\Users\Student\Downloads\test1\dataset\preprocessed\test"))
BETH_JSON_TEST_DIR = Path(os.getenv("BETH_JSON_TEST_DIR", r"C:\Users\Student\Downloads\test1\dataset\preprocessed\test"))

logger.debug("[Config] Neo4j URI: %s (source: %s)", NEO4J_URI,
            "env var" if "NEO4J_URI" in os.environ else "default")
logger.debug("[Config] Neo4j User: %s (password provided: %s)", NEO4J_USER, "YES" if NEO4J_PASSWORD else "NO")

# ── LLM ──────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL       = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL         = os.getenv("LOGRESP_MODEL", "llama3.1:8b")
LLM_TEMPERATURE       = 0.0

logger.info("[Config] LLM Configuration:")
logger.info("  - Ollama Base URL: %s (source: %s)", OLLAMA_BASE_URL,
           "env var" if "OLLAMA_URL" in os.environ else "default")
logger.info("  - Default Model: %s (source: %s)", DEFAULT_MODEL,
           "env var" if "LOGRESP_MODEL" in os.environ else "default")
logger.info("  - Temperature: %.1f", LLM_TEMPERATURE)

BENCHMARK_MODELS = [
    "phi4-mini",
    "qwen2.5-coder:7b",
    "llama3.1:8b",
    "deepseek-r1:14b",
]

# ── GNN ───────────────────────────────────────────────────────────────────────
GNN_INPUT_DIM         = 16
GNN_HIDDEN_DIM        = 32
ANOMALY_THRESHOLD     = 0.85    # configurable — no magic numbers inside agent code
GNN_TRAIN_EPOCHS      = 50

logger.info("[Config] GNN Configuration:")
logger.info("  - Input Dimension: %d", GNN_INPUT_DIM)
logger.info("  - Hidden Dimension: %d", GNN_HIDDEN_DIM)
logger.info("  - Anomaly Threshold: %.2f", ANOMALY_THRESHOLD)
logger.info("  - Training Epochs: %d", GNN_TRAIN_EPOCHS)

# ── Evaluation ────────────────────────────────────────────────────────────────
EVAL_SAMPLE_PER_CLASS = 20
BENCHMARK_CSV_OUT     = Path("benchmark_results.csv")

# ── API ───────────────────────────────────────────────────────────────────────
API_HOST  = "0.0.0.0"
API_PORT  = 8000
API_TOKEN = os.getenv("LOGRESP_API_TOKEN", "changeme")   # set in env for prod
