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
        return {k: v for k, v in log.items() if v not in (None, "", " ")}
    except Exception as exc:
        logger.warning("Skipping malformed row: %s", exc)
        return None


def convert_split(split_name: str):
    input_path  = BETH_SPLITS[split_name]
    output_path = BETH_OUTPUT_DIR / f"beth_{split_name}.json"

    if not input_path.exists():
        logger.error("Missing input file: %s", input_path)
        return

    logger.info("[BETH] Converting %s → %s", input_path.name, output_path.name)
    start = time.time()
    count = 0

    with open(input_path, encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        with open(output_path, "w", encoding="utf-8") as out:
            for row in reader:
                entry = _translate_row(row)
                if entry:
                    out.write(json.dumps(entry) + "\n")
                    count += 1

    logger.info("[BETH] %s done — %d logs in %.2fs", split_name, count, time.time() - start)


def run_all():
    BETH_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("=== BETH Adapter Starting ===")
    for split in ("training", "validation", "testing"):
        convert_split(split)
    logger.info("=== BETH Adapter Complete — output: %s ===", BETH_OUTPUT_DIR)


if __name__ == "__main__":
    run_all()
