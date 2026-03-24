# data/trace_extractor.py
# Extracts high-value events from DARPA Theia .gz Avro files into JSONL.
# Multi-process, one core per file. Reads all paths from config.py.

import concurrent.futures
import fastavro
import gzip
import json
import os
import time
from config import THEIA_SPLITS_DIR, THEIA_OUTPUT_DIR
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_CORES = max(1, os.cpu_count() - 2)

HIGH_VALUE_EVENTS = {
    "EVENT_EXECUTE", "EVENT_FORK", "EVENT_CLONE",
    "EVENT_CONNECT", "EVENT_ACCEPT", "EVENT_SENDTO", "EVENT_RECVFROM",
    "EVENT_OPEN", "EVENT_WRITE", "EVENT_MODIFY_FILE_ATTRIBUTES",
}


def _bytes_to_str(value):
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    return value


def _extract_record(record: dict) -> dict | None:
    if record.get("type") != "RECORD_EVENT":
        return None
    datum = record.get("datum", {})
    event_type = datum.get("type", "")
    if event_type not in HIGH_VALUE_EVENTS:
        return None
    props = datum.get("properties", {})
    log = {
        "timestamp_ns": datum.get("timestampNanos", 0),
        "event_type":   event_type,
        "thread_id":    datum.get("threadId", "UNKNOWN"),
        "cmdLine":      props.get("cmdLine"),
        "file_path":    datum.get("predicateObjectPath"),
        "remote_ip":    props.get("remoteAddress"),
        "remote_port":  props.get("remotePort"),
    }
    return {k: _bytes_to_str(v) for k, v in log.items() if v is not None}


def _process_file(filepath: str) -> tuple[str, list[str], str | None]:
    name = os.path.basename(filepath)
    logs = []
    try:
        with gzip.open(filepath, "rb") as fh:
            for record in fastavro.reader(fh):
                entry = _extract_record(record)
                if entry:
                    logs.append(json.dumps(entry))
        return name, logs, None
    except Exception as exc:
        return name, [], str(exc)


def process_split(split_name: str):
    folder = THEIA_SPLITS_DIR / split_name
    output = THEIA_OUTPUT_DIR / f"theia_{split_name.lower()}.json"

    if not folder.exists():
        logger.error("Folder not found: %s", folder)
        return

    gz_files = sorted(str(p) for p in folder.iterdir() if p.suffix == ".gz")
    if not gz_files:
        logger.warning("No .gz files in %s", folder)
        return

    logger.info("[Theia] %s: %d files, %d cores", split_name, len(gz_files), MAX_CORES)
    start = time.time()
    total = 0

    with open(output, "w", encoding="utf-8") as out:
        with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_CORES) as pool:
            for name, logs, error in pool.map(_process_file, gz_files):
                if error:
                    logger.error("  Error in %s: %s", name, error)
                else:
                    for line in logs:
                        out.write(line + "\n")
                    total += len(logs)
                    logger.info("  %s → %d logs", name, len(logs))

    logger.info("[Theia] %s complete: %d logs in %.2fs", split_name, total, time.time() - start)


def run_all():
    THEIA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("=== Theia Extractor Starting ===")
    for split in ("Training", "Validation", "Testing"):
        process_split(split)
    logger.info("=== Theia Extractor Complete — output: %s ===", THEIA_OUTPUT_DIR)


if __name__ == "__main__":
    run_all()
