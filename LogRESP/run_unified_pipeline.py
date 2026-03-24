# run_unified_pipeline.py  —  Main SOC pipeline
# GNN filters → LLM copilot for anomalies. Clean, no hacks.

import json
import time
from config import ANOMALY_THRESHOLD, FINAL_DATASETS
from gnn.scorer import is_anomalous
from pipelines.ir_pipeline import run_ir
from utils.logger import get_logger
from utils.metrics import ConfusionMatrix

logger = get_logger(__name__)

DATASET_PATH = FINAL_DATASETS / "BETH_final_dataset" / "beth_testing.json"
SAMPLE_SIZE  = 500

def load_logs(path, limit):
    logger.info("[Data Loader] Reading logs from %s (limit=%d)", path, limit)
    logs = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= limit:
                    logger.debug("[Data Loader] Reached limit of %d logs", limit)
                    break
                line = line.strip()
                if line:
                    try:
                        logs.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.debug("[Data Loader] Skipped malformed JSON on line %d: %s", i, e)
                        continue
        logger.info("[Data Loader] Loaded %d logs from %s", len(logs), path.name)
        return logs
    except Exception as e:
        logger.error("[Data Loader] Failed to load logs: %s", e, exc_info=True)
        raise

def run_soc_pipeline():
    logger.info("="*60)
    logger.info("=== LogRESP SOC Pipeline Starting ===")
    logger.info("Anomaly Threshold: %.3f  |  Sample Size: %d", ANOMALY_THRESHOLD, SAMPLE_SIZE)
    logger.info("="*60)
    
    try:
        # Load logs
        logs = load_logs(DATASET_PATH, SAMPLE_SIZE)
        if not logs:
            logger.error("[SOC] No logs loaded, aborting")
            return
        
        logger.info("[SOC] Dataset loaded: %d logs", len(logs))
        benign_count = sum(1 for log in logs if int(log.get("is_evil", 0)) == 0)
        evil_count = len(logs) - benign_count
        logger.info("[SOC] Ground truth: %d benign, %d malicious", benign_count, evil_count)
        
        cm = ConfusionMatrix()
        pipeline_start = time.time()
        anomalies_detected = 0
        high_severity_count = 0

        for i, log in enumerate(logs, 1):
            pid = str(log.get("processId", log.get("process_id", "UNKNOWN")))
            actual_evil = int(log.get("is_evil", 0))
            
            # GNN anomaly detection
            iterlog_start = time.time()
            anomalous, score = is_anomalous(log)
            gnn_time = time.time() - iterlog_start
            
            # Log GNN result
            logger.info("[SOC %03d] PID=%s | GNN_score=%.4f | Anomalous=%s | Time=%.3fs",i, pid, score, "YES" if anomalous else "NO", gnn_time)
            
            # Threshold decision
            if anomalous:
                anomalies_detected += 1
                severity = "CRITICAL" if score > 0.95 else "MEDIUM" if score > 0.85 else "LOW"
                logger.warning("[SOC %03d] *** ANOMALY DETECTED (severity=%s, score=%.4f) ***",i, severity, score)
                                # Print full JSON for detected malicious
                logger.warning("[SOC %03d] MALICIOUS DATA DETECTED ", i)
                logger.warning("[SOC %03d] Complete JSON: ", i)
                logger.warning(json.dumps(log, indent=2))
                if score > 0.95:
                    high_severity_count += 1
                    logger.warning("[SOC %03d] HIGH/CRITICAL — Human review required before IR", i)
                else:
                    logger.info("[SOC %03d] MEDIUM/LOW — Auto-mitigating", i)
                
                # IR response
                try:
                    ir_start = time.time()
                    logger.info("[SOC %03d] Invoking IR pipeline...", i)
                    result = run_ir(pid, score)
                    ir_time = time.time() - ir_start
                    
                    strategy = result.get("ir_strategy", "")
                    commands = result.get("verified_commands", "")
                    logger.info("[SOC %03d] IR complete in %.2fs | Strategy: %s", i, ir_time, strategy[:80])
                    logger.debug("[SOC %03d] Verified commands:\n%s", i, commands)
                    
                except Exception as e:
                    logger.error("[SOC %03d] IR pipeline failed: %s", i, e)

            # Update confusion matrix
            cm.update(actual_evil, anomalous)

        # Summary
        elapsed = round(time.time() - pipeline_start, 2)
        summary = cm.summary()
        
        logger.info("="*60)
        logger.info("=== Pipeline Complete ===")
        logger.info("Total Time: %ss  |  Anomalies Detected: %d/%d (%.1f%%)",
                   elapsed, anomalies_detected, len(logs), 
                   100*anomalies_detected/len(logs) if logs else 0)
        logger.info("High Severity Cases: %d (human review required)", high_severity_count)
        logger.info("="*60)
        logger.info("METRICS:")
        logger.info("  Accuracy:  %.2f%%", summary["accuracy"])
        logger.info("  Precision: %.2f%%", summary["precision"])
        logger.info("  Recall:    %.2f%%", summary["recall"])
        logger.info("  F1-Score:  %.2f%%", summary["f1"])
        logger.info("="*60)
        
    except Exception as e:
        logger.error("[SOC] Pipeline failed catastrophically: %s", e, exc_info=True)
        raise

if __name__ == "__main__":
    run_soc_pipeline()
