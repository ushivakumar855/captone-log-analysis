# evaluate_model.py
# Evaluates the DEFAULT model on the BETH test set.
# Run from project root: python evaluate_model.py

import json
import os
import random
import time
import ast
from config import FINAL_DATASETS, EVAL_SAMPLE_PER_CLASS
from pipelines.logresp_pipeline import logresp_app
from utils.logger import get_logger
from utils.metrics import ConfusionMatrix

logger = get_logger(__name__)

DATASET_PATH = FINAL_DATASETS / "BETH_final_dataset" / "beth_testing.json"


def _load_balanced(filepath, per_class: int) -> list[dict]:
    logger.info("[Evaluate] Loading %s", filepath)
    if not os.path.exists(filepath):
        logger.error("File not found: %s", filepath)
        return []

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    logs = []
    try:
        logs = json.loads(content)
    except json.JSONDecodeError:
        try:
            dec, pos = json.JSONDecoder(), 0
            content  = content.lstrip()
            while pos < len(content):
                obj, pos = dec.raw_decode(content, pos)
                logs.append(obj)
                while pos < len(content) and content[pos].isspace():
                    pos += 1
        except Exception:
            try:
                logs = ast.literal_eval(content)
            except Exception as exc:
                logger.error("Cannot parse file: %s", exc)
                return []

    benign    = [l for l in logs if isinstance(l, dict) and int(l.get("is_evil", 0)) == 0]
    malicious = [l for l in logs if isinstance(l, dict) and int(l.get("is_evil", 0)) == 1]
    logger.info("  Benign=%d  Malicious=%d", len(benign), len(malicious))

    sampled = (
        random.sample(benign,    min(per_class, len(benign)))
        + random.sample(malicious, min(per_class, len(malicious)))
    )
    random.shuffle(sampled)
    return sampled


def _predict_evil(analysis: str) -> bool:
    txt = analysis.lower()
    return "malicious" in txt and "benign" not in txt


def evaluate():
    test_logs = _load_balanced(DATASET_PATH, EVAL_SAMPLE_PER_CLASS)
    if not test_logs:
        logger.error("No logs loaded — aborting.")
        return

    logger.info("[Evaluate] Running on %d logs...", len(test_logs))
    cm    = ConfusionMatrix()
    start = time.time()

    for i, log in enumerate(test_logs, 1):
        actual_evil = int(log.get("is_evil", 0))
        pid   = str(log.get("process_id", log.get("processId", "UNKNOWN")))
        label = "Malicious" if actual_evil else "Benign"
        logger.info("[%d/%d] PID=%-8s  truth=%s", i, len(test_logs), pid, label)

        state = {
            "raw_log": log, "process_id": pid,
            "anomaly_score": 0.0, "neo4j_context": "",
            "ttp_analysis": "", "ir_strategy": "",
            "raw_commands": "", "verified_commands": "",
            "final_analysis": "",
        }
        try:
            result    = logresp_app.invoke(state)
            predicted = _predict_evil(result["final_analysis"])
        except Exception as exc:
            logger.warning("  Error: %s", exc)
            predicted = False

        cm.update(actual_evil, predicted)
        tag = {
            (1, True):  "TRUE POSITIVE  ✓",
            (1, False): "FALSE NEGATIVE ✗",
            (0, True):  "FALSE POSITIVE ✗",
            (0, False): "TRUE NEGATIVE  ✓",
        }[(actual_evil, predicted)]
        logger.info("  → %s", tag)

    elapsed = round(time.time() - start, 2)
    summary = cm.summary()

    print("\n" + "="*50)
    print("  LogRESP Evaluation Results")
    print("="*50)
    print(f"  Logs tested : {len(test_logs)}")
    print(f"  Time taken  : {elapsed}s")
    print(f"  TP={cm.TP}  TN={cm.TN}  FP={cm.FP}  FN={cm.FN}")
    print("-"*50)
    print(f"  Accuracy  : {summary['accuracy']:.2f}%")
    print(f"  Precision : {summary['precision']:.2f}%")
    print(f"  Recall    : {summary['recall']:.2f}%")
    print(f"  F1 Score  : {summary['f1']:.2f}%")
    print("="*50)


if __name__ == "__main__":
    evaluate()
