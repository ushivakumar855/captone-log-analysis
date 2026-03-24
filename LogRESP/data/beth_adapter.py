# data/beth_adapter.py
# Converts BETH CSV splits into unified JSONL format.
# Reads paths from config.py — no hardcoded strings here.

import csv
import json
import time
from config import BETH_SPLITS, BETH_OUTPUT_DIR
from utils.logger import get_logger

logger = get_logger(__name__)


def _translate_row(row: dict) -> dict | None:
    """Map one BETH CSV row to the unified log schema."""
    try:
        log = {
            "timestamp":         float(row.get("timestamp", 0)),
            "event_type":        row.get("eventName", "UNKNOWN"),
            "thread_id":         row.get("threadId"),
            "process_id":        row.get("processId"),
            "parent_process_id": row.get("parentProcessId"),
            "cmdLine":           row.get("processName"),   # unified field name
            "user_id":           row.get("userId"),
            "return_value":      row.get("returnValue"),
            "is_suspicious":     int(row.get("sus",  0)),
            "is_evil":           int(row.get("evil", 0)),
        }
        # Drop null / empty fields to save LLM context space
        result = {k: v for k, v in log.items() if v not in (None, "", " ")}
        logger.debug("[BETH] Row translated: %d fields mapped, %d fields dropped",
                    len(result), len(log) - len(result))
        return result
    except Exception as exc:
        logger.warning("[BETH] Skipping malformed row: %s", exc)
        return None


def convert_split(split_name: str):
    input_path  = BETH_SPLITS[split_name]
    output_path = BETH_OUTPUT_DIR / f"beth_{split_name}.json"

    if not input_path.exists():
        logger.error("[BETH] Missing input file: %s", input_path)
        return

    logger.info("[BETH] Converting %s → %s", input_path.name, output_path.name)
    start = time.time()
    count = 0
    evil_count = 0
    benign_count = 0
    skip_count = 0
    null_defaults = 0

    try:
        with open(input_path, encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            with open(output_path, "w", encoding="utf-8") as out:
                for row in reader:
                    entry = _translate_row(row)
                    if entry:
                        out.write(json.dumps(entry) + "\n")
                        count += 1
                        
                        # Track ground truth label
                        if entry.get("is_evil") == 1:
                            evil_count += 1
                        else:
                            benign_count += 1
                        
                        # Track nulls replaced with defaults
                        if row.get("timestamp") is None or row.get("timestamp") == "":
                            null_defaults += 1
                    else:
                        skip_count += 1
        
        elapsed = time.time() - start
        logger.info("[BETH] %s complete", split_name)
        logger.info("  - Logs processed: %d", count)
        logger.info("  - Malicious (is_evil=1): %d (%.1f%%)", evil_count, 100*evil_count/count if count > 0 else 0)
        logger.info("  - Benign (is_evil=0): %d (%.1f%%)", benign_count, 100*benign_count/count if count > 0 else 0)
        logger.info("  - Skipped (malformed): %d", skip_count)
        logger.info("  - Null fields replaced: %d", null_defaults)
        logger.info("  - Time: %.2fs", elapsed)
        
        # Verify output file
        try:
            output_size = output_path.stat().st_size / 1024 / 1024
            logger.info("  - Output file size: %.2f MB", output_size)
        except Exception as e:
            logger.warning("  - Could not verify output file size: %s", e)
            
    except Exception as e:
        logger.error("[BETH] Conversion failed for %s: %s", split_name, e, exc_info=True)


def run_all():
    logger.info("="*70)
    logger.info("=== BETH Data Adapter ===")
    logger.info("="*70)
    
    BETH_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("[BETH] Output directory created/verified: %s", BETH_OUTPUT_DIR)
    
    total_start = time.time()
    total_logs = 0
    
    for split in ("training", "validation", "testing"):
        logger.info("")
        logger.info("[BETH] Processing split: %s", split.upper())
        convert_split(split)
        # Note: Would need to add counter return from convert_split to track total
    
    total_elapsed = time.time() - total_start
    logger.info("")
    logger.info("="*70)
    logger.info("=== BETH Adapter Complete ===")
    logger.info("Output directory: %s", BETH_OUTPUT_DIR)
    logger.info("Total time: %.2fs", total_elapsed)
    logger.info("="*70)


if __name__ == "__main__":
    run_all()
