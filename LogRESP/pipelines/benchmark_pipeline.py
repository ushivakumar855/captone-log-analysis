# pipelines/benchmark_pipeline.py
# Runs every model in BENCHMARK_MODELS against the BETH test set.
# Prints a comparison table to terminal AND saves a CSV.

import csv
import json
import os
import random
import time
import ast
from config import (
    FINAL_DATASETS, BENCHMARK_MODELS,
    EVAL_SAMPLE_PER_CLASS, BENCHMARK_CSV_OUT,
)
from pipelines.logresp_pipeline import build_logresp_pipeline
from utils.logger import get_logger
from utils.metrics import ConfusionMatrix

logger = get_logger(__name__)

DATASET_PATH = FINAL_DATASETS / "BETH_final_dataset" / "beth_testing.json"


def _load_balanced(filepath, per_class: int) -> list[dict]:
    logger.info("[Benchmark] Loading dataset from %s", filepath)
    if not os.path.exists(filepath):
        logger.error("Dataset not found: %s", filepath)
        return []

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    logs = []
    try:
        logs = json.loads(content)
    except json.JSONDecodeError:
        try:
            dec, pos = json.JSONDecoder(), 0
            content = content.lstrip()
            while pos < len(content):
                obj, pos = dec.raw_decode(content, pos)
                logs.append(obj)
                while pos < len(content) and content[pos].isspace():
                    pos += 1
        except Exception:
            try:
                logs = ast.literal_eval(content)
            except Exception as exc:
                logger.error("Cannot parse dataset: %s", exc)
                return []

    benign     = [l for l in logs if isinstance(l, dict) and int(l.get("is_evil", 0)) == 0]
    malicious  = [l for l in logs if isinstance(l, dict) and int(l.get("is_evil", 0)) == 1]
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


def run_benchmark():
    test_logs = _load_balanced(DATASET_PATH, EVAL_SAMPLE_PER_CLASS)
    if not test_logs:
        logger.error("No logs loaded — aborting benchmark.")
        return

    results: dict[str, dict] = {}

    for model in BENCHMARK_MODELS:
        logger.info("\n%s\nModel: %s\n%s", "="*60, model.upper(), "="*60)
        pipeline = build_logresp_pipeline(model_name=model)
        cm       = ConfusionMatrix()
        start    = time.time()

        for i, log in enumerate(test_logs, 1):
            actual_evil = int(log.get("is_evil", 0))
            pid = str(log.get("process_id", log.get("processId", "UNKNOWN")))
            label = "Malicious" if actual_evil else "Benign"
            logger.info("[%d/%d] model=%-22s PID=%-8s truth=%s",
                        i, len(test_logs), model, pid, label)

            state = {
                "raw_log": log, "process_id": pid,
                "anomaly_score": 0.0, "neo4j_context": "",
                "ttp_analysis": "", "ir_strategy": "",
                "raw_commands": "", "verified_commands": "",
                "final_analysis": "",
            }
            try:
                result = pipeline.invoke(state)
                predicted = _predict_evil(result["final_analysis"])
            except Exception as exc:
                logger.warning("  Error: %s", exc)
                predicted = False

            cm.update(actual_evil, predicted)
            tag = {
                (1, True):  "TRUE POSITIVE",
                (1, False): "FALSE NEGATIVE",
                (0, True):  "FALSE POSITIVE",
                (0, False): "TRUE NEGATIVE",
            }[(actual_evil, predicted)]
            logger.info("  → %s", tag)

        elapsed  = round(time.time() - start, 2)
        summary  = cm.summary()
        summary["time_s"] = elapsed
        results[model] = summary

        logger.info("\n--- %s Results ---", model)
        logger.info("Accuracy=%.2f%%  Precision=%.2f%%  Recall=%.2f%%  F1=%.2f%%  Time=%ss",
                    summary["accuracy"], summary["precision"],
                    summary["recall"], summary["f1"], elapsed)

    # ── Terminal comparison table ─────────────────────────────────────────────
    print("\n" + "="*90)
    print(f"{'Model':<22} | {'Accuracy':>9} | {'Precision':>10} | {'Recall':>7} | {'F1':>7} | {'Time(s)':>8}")
    print("-"*90)
    for model, m in results.items():
        print(f"{model:<22} | {m['accuracy']:>8.2f}% | {m['precision']:>9.2f}% | "
              f"{m['recall']:>6.2f}% | {m['f1']:>6.2f}% | {m['time_s']:>8}")
    print("="*90)

    # ── CSV export ────────────────────────────────────────────────────────────
    try:
        with open(BENCHMARK_CSV_OUT, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "model", "accuracy", "precision", "recall", "f1",
                "TP", "TN", "FP", "FN", "time_s"
            ])
            writer.writeheader()
            for model, m in results.items():
                writer.writerow({"model": model, **m})
        logger.info("Results saved → %s", BENCHMARK_CSV_OUT.resolve())
    except Exception as exc:
        logger.error("CSV save failed: %s", exc)


if __name__ == "__main__":
    run_benchmark()
