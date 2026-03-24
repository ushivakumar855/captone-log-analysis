# run_unified_pipeline.py  —  Main SOC pipeline
# GNN filters → LLM copilot for anomalies. Clean, no hacks.

import json
import time
from config import DATASET_PATH if hasattr(__import__('config'), 'DATASET_PATH') else None
from config import ANOMALY_THRESHOLD, FINAL_DATASETS
from gnn.scorer import is_anomalous
from pipelines.ir_pipeline import run_ir
from utils.logger import get_logger
from utils.metrics import ConfusionMatrix

logger = get_logger(__name__)

DATASET_PATH = FINAL_DATASETS / "BETH_final_dataset" / "beth_testing.json"
SAMPLE_SIZE  = 500

def load_logs(path, limit):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    try:
        logs = json.loads(content)
    except Exception:
        import ast
        logs = ast.literal_eval(content)
    return logs[:limit] if isinstance(logs, list) else []

def run_soc_pipeline():
    logger.info("=== LogRESP SOC Pipeline Starting ===")
    logs = load_logs(DATASET_PATH, SAMPLE_SIZE)
    cm = ConfusionMatrix()
    start = time.time()

    for i, log in enumerate(logs, 1):
        pid = str(log.get("processId", log.get("process_id", "UNKNOWN")))
        actual_evil = int(log.get("is_evil", 0))

        anomalous, score = is_anomalous(log)
        logger.info("[%03d] PID=%-8s score=%.4f anomalous=%s", i, pid, score, anomalous)

        if anomalous:
            # High/Critical → human in loop; Low → auto-mitigate
            severity = "HIGH" if score > 0.95 else "MEDIUM"
            logger.info("  Anomaly detected (severity=%s) — running IR copilot", severity)
            result = run_ir(pid, score)
            logger.info("  Verified commands:\n%s", result["verified_commands"])

        cm.update(actual_evil, anomalous)

    elapsed = round(time.time() - start, 2)
    summary = cm.summary()
    logger.info("=== Pipeline Complete in %ss ===", elapsed)
    logger.info("Accuracy=%.2f%%  Precision=%.2f%%  Recall=%.2f%%  F1=%.2f%%",
                summary["accuracy"], summary["precision"],
                summary["recall"],   summary["f1"])

if __name__ == "__main__":
    run_soc_pipeline()
