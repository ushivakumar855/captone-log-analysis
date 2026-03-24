# config.py  —  single source of truth for the entire project
# All other files import from here. No hardcoded paths anywhere else.

from pathlib import Path
import os

# ── Paths ────────────────────────────────────────────────────────────────────
# Override any of these with environment variables for portability across machines
BASE_DATA_DIR   = Path(os.getenv("LOGRESP_DATA",   r"C:\Users\Student\Downloads"))
FINAL_DATASETS  = BASE_DATA_DIR / "FINAL_DATASETS"
BETH_DATASET    = BASE_DATA_DIR / "BETH dataset"
THEIA_DATASET   = BASE_DATA_DIR / "Theia Complete" / "theia"
MODEL_DIR       = BASE_DATA_DIR

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
NEO4J_PASSWORD = os.getenv("NEO4J_PASS", "capstone123")

# ── LLM ──────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL       = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL         = os.getenv("LOGRESP_MODEL", "qwen2.5-coder:7b")
LLM_TEMPERATURE       = 0.0

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

# ── Evaluation ────────────────────────────────────────────────────────────────
EVAL_SAMPLE_PER_CLASS = 20
BENCHMARK_CSV_OUT     = Path("benchmark_results.csv")

# ── API ───────────────────────────────────────────────────────────────────────
API_HOST  = "0.0.0.0"
API_PORT  = 8000
API_TOKEN = os.getenv("LOGRESP_API_TOKEN", "changeme")   # set in env for prod

# ── n8n ───────────────────────────────────────────────────────────────────────
N8N_ALERT_WEBHOOK  = os.getenv("N8N_ALERT_WEBHOOK",  "http://localhost:5678/webhook/alert")
N8N_APPROVE_WEBHOOK = os.getenv("N8N_APPROVE_WEBHOOK","http://localhost:5678/webhook/approve")
