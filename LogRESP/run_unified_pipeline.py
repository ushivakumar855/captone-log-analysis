# run_unified_pipeline.py  —  Main SOC pipeline
# GNN filters → LLM copilot for anomalies. Clean, no hacks.

import sys
import json
import time
from pathlib import Path

# Add parent directory to sys.path so relative imports work
sys.path.insert(0, str(Path(__file__).parent))

from config import ANOMALY_THRESHOLD, BETH_JSON_TEST_DIR
from db.neo4j_pool import neo4j_session
from gnn.scorer import is_anomalous
from pipelines.ir_pipeline import run_ir
from utils.logger import get_logger
from utils.metrics import ConfusionMatrix

logger = get_logger(__name__)

DATASET_PATH = BETH_JSON_TEST_DIR
SAMPLE_SIZE  = 9999

# ══════════════════════════════════════════════════════════════
#  CONFIGURATION  — Toggle between file and Neo4j data source
# ══════════════════════════════════════════════════════════════
LOAD_FROM_NEO4J = True   # Set to False to use the old file-based loader
# ══════════════════════════════════════════════════════════════

def load_logs_from_file(path, limit):
    logger.info("[Data Loader] Reading logs from %s (limit=%d)", path, limit)
    logs = []
    
    # Find all part_*.json files in the directory
    json_files = sorted(path.glob("part_*.json"))
    if not json_files:
        logger.error("[Data Loader] No part_*.json files found in %s", path)
        return logs

    total_loaded = 0
    try:
        for file_path in json_files:
            if total_loaded >= limit:
                break
            logger.debug("[Data Loader] Reading file: %s", file_path.name)
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                try:
                    # Each file is a single JSON array of records
                    data = json.load(f)
                    
                    # Extend logs, respecting the limit
                    num_to_add = min(len(data), limit - total_loaded)
                    logs.extend(data[:num_to_add])
                    total_loaded += num_to_add
                    
                except json.JSONDecodeError as e:
                    logger.warning("[Data Loader] Skipped malformed JSON file %s: %s", file_path.name, e)
                    continue
        logger.info("[Data Loader] Loaded %d logs from %d files in %s", len(logs), len(json_files), path)
        return logs
    except Exception as e:
        logger.error("[Data Loader] Failed to load logs: %s", e, exc_info=True)
        raise

def load_logs_from_neo4j(limit):
    """
    Load log data from Neo4j with minimal relationships.
    Absolutely minimal query to avoid memory issues.
    """
    logger.info("[Data Loader] Reading logs from Neo4j (limit=%d)", limit)
    
    # Absolute minimum query - just events, processes, hosts, users. Parent relationship only.
    query = """
    MATCH (e:SyscallEvent)<-[:EMITS]-(p:Process)-[:RUNS_ON]->(h:Host)
    MATCH (p)-[:RUNS_AS]->(u:User)
    OPTIONAL MATCH (parent:Process)-[:SPAWNED]->(p)
    RETURN
        e.eventName, e.timestamp, e.returnValue, e.sus, e.evil, e.event_category,
        e.is_delete_op, e.is_exec_op, e.is_network_op, e.is_failed_syscall,
        p.processId, p.processName,
        parent.processId AS parent_pid, parent.processName AS parent_name,
        h.hostName,
        u.userId, u.is_root, u.is_real_user
    SKIP $skip LIMIT $batch_size
    """
    
    logs = []
    batch_size = 5  # Extremely small batch to avoid memory issues
    skip = 0
    total_fetched = 0
    
    try:
        while total_fetched < limit:
            logger.debug("[Data Loader] Fetching batch (skip=%d, batch_size=%d)", skip, batch_size)
            
            with neo4j_session() as session:
                result = session.run(query, skip=skip, batch_size=batch_size)
                batch_count = 0
                
                for record in result:
                    if total_fetched >= limit:
                        break
                    
                    log_entry = {
                        "event": {
                            "eventName": record["e.eventName"],
                            "timestamp": record["e.timestamp"],
                            "returnValue": record["e.returnValue"],
                            "sus": record["e.sus"],
                            "evil": record["e.evil"],
                            "event_category": record["e.event_category"],
                            "is_delete_op": record["e.is_delete_op"],
                            "is_exec_op": record["e.is_exec_op"],
                            "is_network_op": record["e.is_network_op"],
                            "is_failed_syscall": record["e.is_failed_syscall"]
                        },
                        "process": {
                            "processId": record["p.processId"],
                            "processName": record["p.processName"]
                        },
                        "host": {"hostName": record["h.hostName"]},
                        "user": {
                            "userId": record["u.userId"],
                            "is_root": record["u.is_root"],
                            "is_real_user": record["u.is_real_user"]
                        }
                    }
                    
                    # Add parent process relationship if exists
                    if record["parent_pid"]:
                        log_entry["parent_process"] = {
                            "processId": record["parent_pid"],
                            "processName": record["parent_name"]
                        }
                    
                    logs.append({k: v for k, v in log_entry.items() if v is not None})
                    batch_count += 1
                    total_fetched += 1
            
            # If we got fewer records than batch_size, we've reached the end of data
            if batch_count < batch_size:
                logger.debug("[Data Loader] End of data reached (batch had %d records)", batch_count)
                break
            
            skip += batch_size
        
        logger.info("[Data Loader] Loaded %d logs from Neo4j", len(logs))
        return logs
        
    except Exception as e:
        logger.error("[Data Loader] Failed to load logs from Neo4j: %s", e, exc_info=True)
        if "memory" in str(e).lower():
            logger.error("[Data Loader] HINT: Neo4j memory is severely limited. Consider restarting Neo4j or using file-based loader")
        elif "Connection refused" in str(e):
            logger.error("[Data Loader] HINT: Is the Neo4j database running and accessible?")
        raise

def run_soc_pipeline():
    logger.info("="*60)
    logger.info("=== LogRESP SOC Pipeline Starting ===")
    logger.info("Anomaly Threshold: %.3f  |  Sample Size: %d", ANOMALY_THRESHOLD, SAMPLE_SIZE)
    logger.info("Data Source: %s", "Neo4j" if LOAD_FROM_NEO4J else "JSON Files")
    logger.info("="*60)
    
    try:
        # Load logs from the selected source
        if LOAD_FROM_NEO4J:
            logs = load_logs_from_neo4j(SAMPLE_SIZE)
        else:
            logs = load_logs_from_file(DATASET_PATH, SAMPLE_SIZE)
        
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
            # The log from the JSON file is a nested dictionary.
            # The GNN scorer and IR pipeline expect a flattened structure.
            flat_log = {
                **log.get("event", {}),
                **log.get("process", {}),
                **log.get("host", {}),
                **log.get("user", {}),
            }
            
            pid = str(flat_log.get("processId", "UNKNOWN"))
            actual_evil = int(flat_log.get("evil", 0))
            
            # GNN anomaly detection
            iterlog_start = time.time()
            anomalous, score = is_anomalous(flat_log)
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
                    # Pass the original nested log to the IR pipeline, as it contains all context
                    result = run_ir(pid, score, log)
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
