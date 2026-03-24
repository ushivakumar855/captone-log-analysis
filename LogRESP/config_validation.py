# Config validation module - included at end of config.py
# This file contains the validation logic executed when config.py is imported

from pathlib import Path
import logging

def validate_config(GNN_MODEL_PATH, BENIGN_GRAPH_PT, BETH_SPLITS, ANOMALY_THRESHOLD, logger):
    """Validate critical config values at import time."""
    issues = []
    
    if not GNN_MODEL_PATH.exists():
        issues.append(f"GNN model not found: {GNN_MODEL_PATH}")
    if not BENIGN_GRAPH_PT.exists():
        issues.append(f"Benign graph not found: {BENIGN_GRAPH_PT}")
    
    for split_name, split_path in BETH_SPLITS.items():
        if not split_path.exists():
            issues.append(f"BETH {split_name} not found: {split_path}")
    
    if not (0.0 <= ANOMALY_THRESHOLD <= 1.0):
        issues.append(f"Invalid threshold: {ANOMALY_THRESHOLD}")
    
    if issues:
        logger.warning("[Config] Validation issues:")
        for issue in issues:
            logger.warning("  - %s", issue)
    else:
        logger.info("[Config] All paths and thresholds verified")
