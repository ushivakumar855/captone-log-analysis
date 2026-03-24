"""
BETH Dataset Pre-processor → Neo4j-ready JSON
===============================================
Reads chunked CSV files from train_chunks/, val_chunks/, test_chunks/
and outputs pre-processed JSON files ready for Neo4j ingest.

Directory structure expected:
  C:\\Users\\shiva\\OneDrive\\Desktop\\capstone\\dataset\\
    ├── train_chunks/  (part_1.csv, part_2.csv, ...)
    ├── val_chunks/    (part_1.csv, part_2.csv, ...)
    └── test_chunks/   (part_1.csv, part_2.csv, ...)

Output:
  C:\\Users\\shiva\\OneDrive\\Desktop\\capstone\\dataset\\preprocessed\\
    ├── train/  (part_1.json, part_2.json, ...)
    ├── val/    (part_1.json, part_2.json, ...)
    └── test/   (part_1.json, part_2.json, ...)

Usage:
  python beth_preprocess.py
"""

import os
import sys
import ast
import json
import time
import pandas as pd
from pathlib import Path

# Configure UTF-8 encoding for console output (fixes Unicode characters on Windows)
sys.stdout.reconfigure(encoding='utf-8')

# ═══════════════════════════════════════════════════════════
# CONFIGURATION — change this path if your dataset is elsewhere
# ═══════════════════════════════════════════════════════════
BASE_DIR = Path(r"C:\Users\shiva\OneDrive\Desktop\capstone\dataset")

INPUT_FOLDERS = {
    "train": BASE_DIR / "train_chunks",
    "val":   BASE_DIR / "val_chunks",
    "test":  BASE_DIR / "test_chunks",
}

OUTPUT_DIR = BASE_DIR / "preprocessed"

# Columns to drop (redundant / low-value)
DROP_COLUMNS = ["threadId", "eventId", "argsNum", "stackAddresses", "mountNamespace"]

# eventId → eventName is 1-to-1, so we keep only eventName
# threadId ≈ processId 99.4% of the time
# argsNum == len(args) always
# stackAddresses: 57% empty, raw memory pointers
# mountNamespace: only 4-5 values, 97% share default

# Event categories for grouping syscalls
EVENT_CATEGORIES = {
    # File operations
    "close": "file_op", "openat": "file_op", "fstat": "file_op",
    "stat": "file_op", "lstat": "file_op", "access": "file_op",
    "getdents64": "file_op", "unlink": "file_op", "unlinkat": "file_op",
    "fchmod": "file_op", "dup": "file_op", "dup2": "file_op", "dup3": "file_op",
    "umount": "file_op",
    # Process operations
    "clone": "process", "execve": "process", "kill": "process",
    "sched_process_exit": "process", "prctl": "process",
    "setuid": "process", "setgid": "process",
    "setreuid": "process", "setregid": "process",
    # Network operations
    "socket": "network", "connect": "network", "bind": "network",
    "accept": "network", "accept4": "network", "getsockname": "network",
    # Security hooks (Tracee-specific)
    "security_file_open": "security", "security_inode_unlink": "security",
    "security_bprm_check": "security", "cap_capable": "security",
}

# Sensitive path patterns
SENSITIVE_PATHS = ["/etc/passwd", "/etc/shadow", "/etc/ssh/", "/tmp/ssh-"]


# ═══════════════════════════════════════════════════════════
# ARGS PARSING FUNCTIONS
# ═══════════════════════════════════════════════════════════

def safe_parse_args(args_str):
    """Parse the args column (Python list-of-dicts string) safely."""
    try:
        if pd.isna(args_str) or args_str == "[]":
            return []
        return ast.literal_eval(args_str)
    except (ValueError, SyntaxError):
        return []


def extract_arg(args_list, arg_name):
    """Extract a specific argument value by name from parsed args."""
    for arg in args_list:
        if isinstance(arg, dict) and arg.get("name") == arg_name:
            return arg.get("value")
    return None


# ═══════════════════════════════════════════════════════════
# FEATURE ENGINEERING FUNCTIONS
# ═══════════════════════════════════════════════════════════

def get_path_prefix(pathname):
    """Extract the top-level directory prefix from a pathname."""
    if not isinstance(pathname, str) or not pathname.startswith("/"):
        return None
    parts = pathname.split("/")
    if len(parts) >= 2:
        return "/" + parts[1]  # e.g., /tmp, /etc, /proc, /sys
    return "/"


def has_sensitive_path(pathname):
    """Check if pathname matches any sensitive pattern."""
    if not isinstance(pathname, str):
        return False
    return any(pat in pathname for pat in SENSITIVE_PATHS)


def classify_flags(flags_str):
    """Classify file access flags into read/write/readwrite."""
    if not isinstance(flags_str, str):
        return None
    if "WRONLY" in flags_str:
        return "write"
    elif "RDWR" in flags_str:
        return "readwrite"
    elif "RDONLY" in flags_str or flags_str == "0":
        return "read"
    return "other"


# ═══════════════════════════════════════════════════════════
# CORE PRE-PROCESSING FUNCTION
# ═══════════════════════════════════════════════════════════

def preprocess_chunk(df):
    """
    Pre-process a single chunk DataFrame.
    Returns a list of dictionaries (one per syscall event),
    structured for Neo4j ingest.
    """
    # 1. Drop redundant columns
    df = df.drop(columns=[c for c in DROP_COLUMNS if c in df.columns], errors="ignore")

    # 2. Parse args column
    df["parsed_args"] = df["args"].apply(safe_parse_args)

    # 3. Extract fields from args
    df["pathname"]     = df["parsed_args"].apply(lambda a: extract_arg(a, "pathname"))
    df["flags_raw"]    = df["parsed_args"].apply(lambda a: extract_arg(a, "flags"))
    df["socket_domain"] = df["parsed_args"].apply(lambda a: extract_arg(a, "domain"))
    df["socket_type"]  = df["parsed_args"].apply(lambda a: extract_arg(a, "type"))
    df["fd"]           = df["parsed_args"].apply(lambda a: extract_arg(a, "fd"))

    # 4. Derive features
    df["path_prefix"]       = df["pathname"].apply(get_path_prefix)
    df["has_sensitive_path"] = df["pathname"].apply(has_sensitive_path)
    df["flags_category"]    = df["flags_raw"].apply(classify_flags)
    df["is_delete_op"]      = df["eventName"].isin(["unlink", "unlinkat", "security_inode_unlink"])
    df["is_exec_op"]        = df["eventName"].isin(["execve", "security_bprm_check"])
    df["is_network_op"]     = df["eventName"].isin(["socket", "connect", "bind", "accept", "accept4", "getsockname"])
    df["is_root"]           = df["userId"] == 0
    df["is_real_user"]      = df["userId"] >= 1000
    df["is_failed_syscall"] = df["returnValue"] < 0
    df["event_category"]    = df["eventName"].map(EVENT_CATEGORIES).fillna("other")

    # 5. Build Neo4j-structured JSON records
    records = []
    for _, row in df.iterrows():
        record = build_neo4j_record(row)
        records.append(record)

    return records


def build_neo4j_record(row):
    """
    Build a single JSON record structured for Neo4j ingest.

    Structure:
      - event: the SyscallEvent node properties
      - process: the Process node properties
      - host: the Host node properties
      - user: the User node properties
      - file_path: the FilePath node properties (if applicable)
      - socket: the SocketCall node properties (if applicable)
      - edges: relationship info for Cypher queries
    """
    record = {
        # ─── SyscallEvent node ───
        "event": {
            "eventName":        row["eventName"],
            "timestamp":        row["timestamp"],
            "returnValue":      int(row["returnValue"]),
            "sus":              int(row["sus"]),
            "evil":             int(row["evil"]),
            "event_category":   row["event_category"],
            "is_delete_op":     bool(row["is_delete_op"]),
            "is_exec_op":       bool(row["is_exec_op"]),
            "is_network_op":    bool(row["is_network_op"]),
            "is_failed_syscall": bool(row["is_failed_syscall"]),
        },

        # ─── Process node ───
        "process": {
            "processId":        int(row["processId"]),
            "parentProcessId":  int(row["parentProcessId"]),
            "processName":      row["processName"],
        },

        # ─── Host node ───
        "host": {
            "hostName": row["hostName"],
        },

        # ─── User node ───
        "user": {
            "userId":       int(row["userId"]),
            "is_root":      bool(row["is_root"]),
            "is_real_user": bool(row["is_real_user"]),
        },

        # ─── Edges (relationship metadata) ───
        "edges": {
            "process_host":     "RUNS_ON",
            "process_parent":   "CHILD_OF",
            "process_user":     "RUNS_AS",
            "process_event":    "EMITS",
        },
    }

    # ─── FilePath node (only if pathname exists) ───
    if pd.notna(row.get("pathname")) and row["pathname"] is not None:
        record["file_path"] = {
            "pathname":           row["pathname"],
            "path_prefix":        row["path_prefix"],
            "has_sensitive_path": bool(row["has_sensitive_path"]),
        }
        if row.get("flags_category") is not None:
            record["file_path"]["flags_raw"]      = row["flags_raw"]
            record["file_path"]["flags_category"]  = row["flags_category"]
        record["edges"]["event_file"] = "ACCESSES"

    # ─── SocketCall node (only if socket domain exists) ───
    if pd.notna(row.get("socket_domain")) and row["socket_domain"] is not None:
        record["socket"] = {
            "domain": row["socket_domain"],
        }
        if row.get("socket_type") is not None:
            record["socket"]["type"] = row["socket_type"]
        record["edges"]["event_socket"] = "OPENS"

    return record


# ═══════════════════════════════════════════════════════════
# FILE PROCESSING
# ═══════════════════════════════════════════════════════════

def get_chunk_files(folder_path):
    """Get all CSV chunk files from a folder, sorted by part number."""
    folder = Path(folder_path)
    if not folder.exists():
        print(f"  [WARNING] Folder not found: {folder}")
        return []

    csv_files = sorted(
        folder.glob("part_*.csv"),
        key=lambda f: int(f.stem.split("_")[1]) if f.stem.split("_")[1].isdigit() else 0
    )

    if not csv_files:
        # Try .xlsx if no CSV found (your screenshot shows Excel files)
        xlsx_files = sorted(
            folder.glob("part_*.xlsx"),
            key=lambda f: int(f.stem.split("_")[1]) if f.stem.split("_")[1].isdigit() else 0
        )
        if xlsx_files:
            return xlsx_files

    return csv_files


def read_chunk(file_path):
    """Read a chunk file (CSV or Excel)."""
    ext = file_path.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(file_path)
    elif ext in (".xlsx", ".xls"):
        return pd.read_excel(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def process_split(split_name, input_folder, output_folder):
    """Process all chunks for one split (train/val/test)."""
    chunk_files = get_chunk_files(input_folder)

    if not chunk_files:
        print(f"  [SKIP] No chunk files found in {input_folder}")
        return 0, 0

    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    total_files = 0

    for chunk_file in chunk_files:
        part_name = chunk_file.stem  # e.g., "part_1"
        output_file = output_folder / f"{part_name}.json"

        print(f"  Processing {chunk_file.name}...", end=" ", flush=True)
        t0 = time.time()

        try:
            df = read_chunk(chunk_file)
            records = preprocess_chunk(df)

            # Write JSON output (one JSON array per file)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2, default=str)

            elapsed = time.time() - t0
            print(f"{len(records)} rows → {output_file.name} ({elapsed:.1f}s)")
            total_rows += len(records)
            total_files += 1

        except Exception as e:
            print(f"ERROR: {e}")

    return total_files, total_rows


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("BETH Dataset Pre-processor → Neo4j JSON")
    print("=" * 70)
    print(f"\nBase directory: {BASE_DIR}")
    print(f"Output directory: {OUTPUT_DIR}\n")

    # Verify base directory exists
    if not BASE_DIR.exists():
        print(f"[ERROR] Base directory not found: {BASE_DIR}")
        print("Please update the BASE_DIR variable in this script.")
        sys.exit(1)

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    grand_total_files = 0
    grand_total_rows = 0

    for split_name, input_folder in INPUT_FOLDERS.items():
        output_folder = OUTPUT_DIR / split_name
        print(f"\n{'─' * 50}")
        print(f"Split: {split_name.upper()}")
        print(f"  Input:  {input_folder}")
        print(f"  Output: {output_folder}")
        print(f"{'─' * 50}")

        files, rows = process_split(split_name, input_folder, output_folder)
        grand_total_files += files
        grand_total_rows += rows

    # ─── Summary ───
    print(f"\n{'=' * 70}")
    print("PRE-PROCESSING COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Total files processed: {grand_total_files}")
    print(f"  Total rows processed:  {grand_total_rows}")
    print(f"  Output location:       {OUTPUT_DIR}")
    print(f"\nOutput structure:")
    print(f"  {OUTPUT_DIR}/")
    print(f"    ├── train/  (part_1.json, part_2.json, ...)")
    print(f"    ├── val/    (part_1.json, part_2.json, ...)")
    print(f"    └── test/   (part_1.json, part_2.json, ...)")

    # ─── Print sample record ───
    print(f"\n{'─' * 50}")
    print("SAMPLE OUTPUT RECORD (first record from first file):")
    print(f"{'─' * 50}")
    sample_path = OUTPUT_DIR / "train" / "part_1.json"
    if not sample_path.exists():
        # Try any available split
        for s in ["test", "val", "train"]:
            p = OUTPUT_DIR / s / "part_1.json"
            if p.exists():
                sample_path = p
                break

    if sample_path.exists():
        with open(sample_path, "r") as f:
            sample = json.load(f)
        if sample:
            print(json.dumps(sample[0], indent=2, default=str))
    else:
        print("  (no output files generated yet)")

    print(f"\n{'=' * 70}")
    print("Next step: Load these JSON files into Neo4j using")
    print("the Cypher ingest script (separate file).")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
