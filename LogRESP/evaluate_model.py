# evaluate_model.py
# Evaluates the DEFAULT model on the BETH test set.
# Run from project root: python evaluate_model.py

import sys
import json
import os
import random
import time
import ast
from pathlib import Path

# Add parent directory to sys.path so relative imports work
sys.path.insert(0, str(Path(__file__).parent))

from config import FINAL_DATASETS, EVAL_SAMPLE_PER_CLASS
from pipelines.logresp_pipeline import logresp_app
from utils.logger import get_logger
from utils.metrics import ConfusionMatrix

logger = get_logger(__name__)

DATASET_PATH = FINAL_DATASETS / "BETH_final_dataset" / "beth_testing.json"


def _load_balanced(filepath, per_class: int) -> list[dict]:
    logger.info("[Evaluate] Loading balanced test set from %s", filepath)
    logger.debug("[Evaluate] Target: %d samples per class", per_class)
    
    if not os.path.exists(filepath):
        logger.error("[Evaluate] File not found: %s", filepath)
        return []

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        logger.debug("[Evaluate] File read: %d bytes", len(content))

        logs = []
        try:
            logs = json.loads(content)
            logger.debug("[Evaluate] Parsed as single JSON")
        except json.JSONDecodeError:
            try:
                dec, pos = json.JSONDecoder(), 0
                content  = content.lstrip()
                while pos < len(content):
                    obj, pos = dec.raw_decode(content, pos)
                    logs.append(obj)
                    while pos < len(content) and content[pos].isspace():
                        pos += 1
                logger.debug("[Evaluate] Parsed as streaming JSON: %d objects", len(logs))
            except Exception:
                try:
                    logs = ast.literal_eval(content)
                    logger.debug("[Evaluate] Parsed as literal eval")
                except Exception as exc:
                    logger.error("[Evaluate] Cannot parse file: %s", exc, exc_info=True)
                    return []

        benign    = [l for l in logs if isinstance(l, dict) and int(l.get("is_evil", 0)) == 0]
        malicious = [l for l in logs if isinstance(l, dict) and int(l.get("is_evil", 0)) == 1]
        logger.info("[Evaluate] Dataset composition: %d benign, %d malicious, %d unknown",
                   len(benign), len(malicious), len(logs) - len(benign) - len(malicious))

        sampled_benign = random.sample(benign,    min(per_class, len(benign)))
        sampled_malicious = random.sample(malicious, min(per_class, len(malicious)))
        sampled = sampled_benign + sampled_malicious
        random.shuffle(sampled)
        
        logger.info("[Evaluate] Balanced sample: %d benign + %d malicious = %d total",
                   len(sampled_benign), len(sampled_malicious), len(sampled))
        return sampled
        
    except Exception as e:
        logger.error("[Evaluate] Failed to load balanced dataset: %s", e, exc_info=True)
        return []


def _predict_evil(analysis: str) -> bool:
    txt = analysis.lower()
    is_malicious = "malicious" in txt and "benign" not in txt
    logger.debug("[Evaluate] Classification extracted: %s (from len=%d response)",
                 "MALICIOUS" if is_malicious else "BENIGN", len(txt))
    return is_malicious


def evaluate():
    logger.info("="*70)
    logger.info("=== LogRESP Model Evaluation ===")
    logger.info("Dataset: BETH Test Set  |  Sample size per class: %d", EVAL_SAMPLE_PER_CLASS)
    logger.info("="*70)
    
    test_logs = _load_balanced(DATASET_PATH, EVAL_SAMPLE_PER_CLASS)
    if not test_logs:
        logger.error("[Evaluate] No logs loaded — aborting.")
        return

    logger.info("[Evaluate] Starting evaluation on %d logs", len(test_logs))
    cm    = ConfusionMatrix()
    start = time.time()
    
    tp_count = tn_count = fp_count = fn_count = 0

    for i, log in enumerate(test_logs, 1):
        actual_evil = int(log.get("is_evil", 0))
        pid   = str(log.get("process_id", log.get("processId", "UNKNOWN")))
        label = "MALICIOUS" if actual_evil else "BENIGN"
        
        logger.info("[Evaluate %d/%d] PID=%s  Ground Truth=%s", i, len(test_logs), pid, label)

        # Build state for pipeline
        state = {
            "raw_log": log, "process_id": pid,
            "anomaly_score": 0.0, "neo4j_context": "",
            "ttp_analysis": "", "ir_strategy": "",
            "raw_commands": "", "verified_commands": "",
            "final_analysis": "",
        }
        
        try:
            logger.debug("[Evaluate %d] Invoking detection pipeline", i)
            invoke_start = time.time()
            result    = logresp_app.invoke(state)
            invoke_time = time.time() - invoke_start
            
            analysis = result["final_analysis"]
            logger.debug("[Evaluate %d] Pipeline response in %.2fs (len=%d)", i, invoke_time, len(analysis))
            
            predicted = _predict_evil(analysis)
            
        except Exception as exc:
            logger.warning("[Evaluate %d] Pipeline error: %s | Defaulting to BENIGN", i, exc)
            predicted = False

        cm.update(actual_evil, predicted)
        
        # Classification result mapping
        result_map = {
            (1, True):  "TP ✓ (Correctly identified as malicious)",
            (1, False): "FN ✗ (Missed malicious log)",
            (0, True):  "FP ✗ (False alarm - benign flagged)",
            (0, False): "TN ✓ (Correctly identified as benign)",
        }
        result_tag = result_map[(actual_evil, predicted)]
        logger.info("[Evaluate %d] Prediction: %s  %s",
                   i, "MALICIOUS" if predicted else "BENIGN", result_tag)
        
        # Print full JSON if malicious is detected
        if predicted:
            logger.warning("[Evaluate %d] *** MALICIOUS DATA DETECTED ***", i)
            logger.warning("[Evaluate %d] Complete JSON:", i)
            logger.warning(json.dumps(log, indent=2))
        
        # Track counts
        if actual_evil == 1 and predicted == True:
            tp_count += 1
        elif actual_evil == 0 and predicted == False:
            tn_count += 1
        elif actual_evil == 0 and predicted == True:
            fp_count += 1
        elif actual_evil == 1 and predicted == False:
            fn_count += 1

    elapsed = round(time.time() - start, 2)
    summary = cm.summary()

    # Log results
    logger.info("="*70)
    logger.info("=== Evaluation Complete ===")
    logger.info("Total Time: %ds  |  Logs Evaluated: %d", elapsed, len(test_logs))
    logger.info("="*70)
    logger.info("Confusion Matrix:")
    logger.info("  TP (True Positive):  %d", cm.TP)
    logger.info("  TN (True Negative):  %d", cm.TN)
    logger.info("  FP (False Positive): %d", cm.FP)
    logger.info("  FN (False Negative): %d", cm.FN)
    logger.info("-"*70)
    logger.info("Performance Metrics:")
    logger.info("  Accuracy:  %.2f%%", summary["accuracy"])
    logger.info("  Precision: %.2f%%", summary["precision"])
    logger.info("  Recall:    %.2f%%", summary["recall"])
    logger.info("  F1-Score:  %.2f%%", summary["f1"])
    logger.info("="*70)


if __name__ == "__main__":
    evaluate()
