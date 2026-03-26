"""
load_beth_to_neo4j.py — Fixed version
Loads ALL pre-processed BETH JSON chunks (train + val + test) into Neo4j.
Filters evil=1 rows from TRAIN to keep GNN training graph clean.
"""

import os
import sys
import json
import time
from pathlib import Path

try:
    from neo4j import GraphDatabase
except ImportError:
    print("[ERROR] neo4j driver not installed. Run: pip install neo4j")
    sys.exit(1)

sys.stdout.reconfigure(encoding='utf-8')

# ═══════════════════════════════════════════════════════════
# CONFIGURATION — update BASE_DIR to your actual path
# ═══════════════════════════════════════════════════════════
BASE_DIR = Path(r"C:\Users\Student\Downloads\test1\dataset\preprocessed")

# All three splits — script loads them all in order
SPLITS = {
    "train": {
        "folder":      BASE_DIR / "train",
        "filter_evil": True,   # ← CRITICAL: exclude evil=1 from GNN training graph
    },
    "val": {
        "folder":      BASE_DIR / "val",
        "filter_evil": False,  # val has no evil rows anyway
    },
    "test": {
        "folder":      BASE_DIR / "test",
        "filter_evil": False,  # load ALL test rows including evil=1 (agents need full context)
    },
}

NEO4J_URI      = os.getenv("NEO4J_URI",  "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASS", "test2-beth123")

BATCH_SIZE = 500   # rows per Cypher UNWIND call


# ═══════════════════════════════════════════════════════════
# CYPHER QUERIES
# ═══════════════════════════════════════════════════════════

CREATE_HOSTS = """
UNWIND $batch AS rec
MERGE (h:Host {hostName: rec.host.hostName})
"""

CREATE_USERS = """
UNWIND $batch AS rec
MERGE (u:User {userId: rec.user.userId})
ON CREATE SET u.is_root      = rec.user.is_root,
              u.is_real_user = rec.user.is_real_user
"""

# id = string version of processId (used by context_retriever: MATCH (p:Process {id: $pid}))
# cmdLine = processName (used by context_retriever for display)
CREATE_PROCESSES = """
UNWIND $batch AS rec
MERGE (p:Process {processId: rec.process.processId, hostName: rec.host.hostName})
ON CREATE SET p.id          = toString(rec.process.processId),
              p.cmdLine     = rec.process.processName,
              p.processName = rec.process.processName
"""

CREATE_RUNS_ON = """
UNWIND $batch AS rec
MATCH (p:Process {processId: rec.process.processId, hostName: rec.host.hostName})
MATCH (h:Host    {hostName: rec.host.hostName})
MERGE (p)-[:RUNS_ON]->(h)
"""

CREATE_RUNS_AS = """
UNWIND $batch AS rec
MATCH (p:Process {processId: rec.process.processId, hostName: rec.host.hostName})
MATCH (u:User    {userId: rec.user.userId})
MERGE (p)-[:RUNS_AS]->(u)
"""

# Skip parentProcessId=0 (kernel init — no real parent)
CREATE_SPAWNED = """
UNWIND $batch AS rec
WITH rec WHERE rec.process.parentProcessId > 0
MERGE (parent:Process {processId: rec.process.parentProcessId, hostName: rec.host.hostName})
ON CREATE SET parent.id      = toString(rec.process.parentProcessId),
              parent.cmdLine = 'unknown'
MERGE (child:Process  {processId: rec.process.processId,       hostName: rec.host.hostName})
MERGE (parent)-[:SPAWNED]->(child)
"""

# CREATE (not MERGE) — every syscall event is a unique occurrence
CREATE_EVENTS = """
UNWIND $batch AS rec
CREATE (e:SyscallEvent {
    eventName:          rec.event.eventName,
    timestamp:          rec.event.timestamp,
    returnValue:        rec.event.returnValue,
    sus:                rec.event.sus,
    evil:               rec.event.evil,
    event_category:     rec.event.event_category,
    is_delete_op:       rec.event.is_delete_op,
    is_exec_op:         rec.event.is_exec_op,
    is_network_op:      rec.event.is_network_op,
    is_failed_syscall:  rec.event.is_failed_syscall
})
WITH e, rec
MATCH (p:Process {processId: rec.process.processId, hostName: rec.host.hostName})
CREATE (p)-[:EMITS]->(e)
"""

CREATE_FILES = """
UNWIND $batch AS rec
MERGE (f:File {path: rec.file_path.pathname})
ON CREATE SET f.path_prefix        = rec.file_path.path_prefix,
              f.has_sensitive_path = rec.file_path.has_sensitive_path
SET   f.flags_raw      = COALESCE(rec.file_path.flags_raw,      f.flags_raw),
      f.flags_category = COALESCE(rec.file_path.flags_category, f.flags_category)
WITH f, rec
MATCH (p:Process {processId: rec.process.processId, hostName: rec.host.hostName})
MERGE (p)-[:ACCESSED]->(f)
"""

CREATE_SOCKETS = """
UNWIND $batch AS rec
MERGE (n:Network {domain: rec.socket.domain})
ON CREATE SET n.type = rec.socket.type
WITH n, rec
MATCH (p:Process {processId: rec.process.processId, hostName: rec.host.hostName})
MERGE (p)-[:CONNECTED_TO]->(n)
"""

SETUP_SCHEMA = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (h:Host)    REQUIRE h.hostName IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (u:User)    REQUIRE u.userId   IS UNIQUE",
    "CREATE INDEX IF NOT EXISTS FOR (p:Process)     ON (p.processId, p.hostName)",
    "CREATE INDEX IF NOT EXISTS FOR (p:Process)     ON (p.id)",
    "CREATE INDEX IF NOT EXISTS FOR (f:File)        ON (f.path)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Network)     ON (n.domain)",
    "CREATE INDEX IF NOT EXISTS FOR (e:SyscallEvent) ON (e.timestamp)",
    "CREATE INDEX IF NOT EXISTS FOR (e:SyscallEvent) ON (e.evil)",
    "CREATE INDEX IF NOT EXISTS FOR (e:SyscallEvent) ON (e.sus)",
]


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def connect(uri, user, password):
    print(f"[Neo4j] Connecting to {uri} as '{user}'...")
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password),
                                      max_connection_pool_size=10,
                                      connection_timeout=30)
        driver.verify_connectivity()
        print("[Neo4j] Connected.\n")
        return driver
    except Exception as e:
        print(f"[Neo4j] FAILED: {e}")
        print("  → Is Neo4j Desktop running? Is the instance Started (green)?")
        sys.exit(1)


def clear_db(driver):
    print("[Clear] Deleting all existing nodes and relationships...")
    with driver.session() as s:
        count = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        if count == 0:
            print("  Already empty.\n")
            return
        deleted = 0
        while True:
            d = s.run("MATCH (n) WITH n LIMIT 10000 DETACH DELETE n RETURN count(*) AS d").single()["d"]
            if d == 0:
                break
            deleted += d
            print(f"  Deleted {deleted:,} nodes...", end="\r")
        print(f"  Cleared {deleted:,} nodes.\n")


def setup_schema(driver):
    print("[Schema] Creating indexes...")
    with driver.session() as s:
        for q in SETUP_SCHEMA:
            try:
                s.run(q)
            except Exception as e:
                print(f"  [skip] {str(e)[:60]}")
    print("[Schema] Done.\n")


def run_batch(session, query, batch, label):
    if not batch:
        return 0
    try:
        result  = session.run(query, batch=batch)
        summary = result.consume()
        return summary.counters.nodes_created + summary.counters.relationships_created
    except Exception as e:
        print(f"\n  [ERROR] {label}: {e}")
        return 0


def get_json_files(folder):
    files = sorted(
        Path(folder).glob("part_*.json"),
        key=lambda f: int(f.stem.split("_")[1]) if f.stem.split("_")[1].isdigit() else 0
    )
    return files


# ═══════════════════════════════════════════════════════════
# LOAD ONE JSON FILE
# ═══════════════════════════════════════════════════════════

def load_file(driver, json_path, filter_evil=False):
    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    # For train split: filter out evil=1 to keep GNN training graph clean
    if filter_evil:
        before = len(records)
        records = [r for r in records if r.get("event", {}).get("evil", 0) == 0]
        filtered = before - len(records)
        if filtered > 0:
            print(f"    [filter] Removed {filtered} evil=1 rows from train (GNN safety)", flush=True)

    if not records:
        return 0

    total_created = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch        = records[i: i + BATCH_SIZE]
        file_batch   = [r for r in batch if "file_path" in r]
        socket_batch = [r for r in batch if "socket"    in r]

        with driver.session() as s:
            # Nodes first
            total_created += run_batch(s, CREATE_HOSTS,     batch,        "Host")
            total_created += run_batch(s, CREATE_USERS,     batch,        "User")
            total_created += run_batch(s, CREATE_PROCESSES, batch,        "Process")
            # Relationships
            total_created += run_batch(s, CREATE_RUNS_ON,   batch,        "RUNS_ON")
            total_created += run_batch(s, CREATE_RUNS_AS,   batch,        "RUNS_AS")
            total_created += run_batch(s, CREATE_SPAWNED,   batch,        "SPAWNED")
            # Events (one per syscall — always present)
            total_created += run_batch(s, CREATE_EVENTS,    batch,        "EMITS")
            # Optional nodes
            if file_batch:
                total_created += run_batch(s, CREATE_FILES,   file_batch,   "ACCESSED")
            if socket_batch:
                total_created += run_batch(s, CREATE_SOCKETS, socket_batch, "CONNECTED_TO")

    return len(records)


# ═══════════════════════════════════════════════════════════
# LOAD ONE SPLIT (all files in a folder)
# ═══════════════════════════════════════════════════════════

def load_split(driver, split_name, folder, filter_evil):
    folder = Path(folder)
    print(f"\n{'='*60}")
    print(f"  Loading split: {split_name.upper()}")
    print(f"  Folder: {folder}")
    print(f"  Filter evil=1: {filter_evil}")
    print(f"{'='*60}\n", flush=True)

    if not folder.exists():
        print(f"  [ERROR] Folder not found: {folder}")
        print(f"  → Update BASE_DIR in this script to your actual path.")
        return 0, 0

    json_files = get_json_files(folder)

    if not json_files:
        print(f"  [ERROR] No part_*.json files found in {folder}")
        print(f"  Files present: {[f.name for f in folder.iterdir()][:10]}")
        return 0, 0

    print(f"  Found {len(json_files)} chunk files.")
    print(f"  Estimated rows: ~{len(json_files) * 500:,} (500 rows/file)\n")

    total_rows  = 0
    start       = time.time()

    for idx, jf in enumerate(json_files, 1):
        t0 = time.time()
        rows = load_file(driver, jf, filter_evil=filter_evil)
        elapsed = time.time() - t0
        total_rows += rows
        pct = idx / len(json_files) * 100
        print(f"  [{idx:>4}/{len(json_files)}] {jf.name:<20} "
              f"{rows:>5} rows  {elapsed:>5.1f}s  "
              f"cumulative: {total_rows:>7,}  ({pct:.0f}%)", flush=True)

    elapsed_total = time.time() - start
    speed = total_rows / elapsed_total if elapsed_total > 0 else 0
    print(f"\n  Split '{split_name}' complete: {total_rows:,} rows in {elapsed_total:.1f}s ({speed:.0f} rows/s)")
    return len(json_files), total_rows


# ═══════════════════════════════════════════════════════════
# GRAPH STATS + VERIFICATION
# ═══════════════════════════════════════════════════════════

def print_stats(driver):
    print(f"\n{'='*60}")
    print("  GRAPH STATISTICS")
    print(f"{'='*60}")
    queries = [
        ("Total nodes",            "MATCH (n) RETURN count(n) AS c"),
        ("Total relationships",    "MATCH ()-[r]-() RETURN count(r) AS c"),
        ("──────────────────",     None),
        ("Host nodes",             "MATCH (n:Host)         RETURN count(n) AS c"),
        ("Process nodes",          "MATCH (n:Process)      RETURN count(n) AS c"),
        ("User nodes",             "MATCH (n:User)         RETURN count(n) AS c"),
        ("SyscallEvent nodes",     "MATCH (n:SyscallEvent) RETURN count(n) AS c"),
        ("File nodes",             "MATCH (n:File)         RETURN count(n) AS c"),
        ("Network nodes",          "MATCH (n:Network)      RETURN count(n) AS c"),
        ("──────────────────",     None),
        ("SPAWNED edges",          "MATCH ()-[r:SPAWNED]-()       RETURN count(r) AS c"),
        ("EMITS edges",            "MATCH ()-[r:EMITS]-()         RETURN count(r) AS c"),
        ("ACCESSED edges",         "MATCH ()-[r:ACCESSED]-()      RETURN count(r) AS c"),
        ("CONNECTED_TO edges",     "MATCH ()-[r:CONNECTED_TO]-()  RETURN count(r) AS c"),
        ("──────────────────",     None),
        ("Evil events (evil=1)",   "MATCH (e:SyscallEvent {evil:1}) RETURN count(e) AS c"),
        ("Suspicious (sus=1)",     "MATCH (e:SyscallEvent {sus:1})  RETURN count(e) AS c"),
    ]
    with driver.session() as s:
        for label, q in queries:
            if q is None:
                print(f"  {'-'*40}")
                continue
            try:
                c = s.run(q).single()["c"]
                print(f"  {label:<30} {c:>12,}")
            except Exception as e:
                print(f"  {label:<30} ERROR: {e}")


def verify(driver):
    print(f"\n{'='*60}")
    print("  VERIFICATION — context_retriever.py compatibility")
    print(f"{'='*60}")
    checks = [
        ("Process.id + cmdLine exist",
         "MATCH (p:Process) WHERE p.id IS NOT NULL AND p.cmdLine IS NOT NULL RETURN count(p) AS c"),
        ("SPAWNED relationships exist",
         "MATCH ()-[:SPAWNED]->() RETURN count(*) AS c"),
        ("ACCESSED (File) relationships",
         "MATCH ()-[:ACCESSED]->(:File) RETURN count(*) AS c"),
        ("CONNECTED_TO (Network) relationships",
         "MATCH ()-[:CONNECTED_TO]->(:Network) RETURN count(*) AS c"),
        ("Evil events in graph",
         "MATCH (e:SyscallEvent {evil:1}) RETURN count(e) AS c"),
    ]
    with driver.session() as s:
        for label, q in checks:
            try:
                c = s.run(q).single()["c"]
                status = "[PASS]" if c > 0 else "[WARN — 0 found]"
                print(f"  {status} {label}: {c:,}")
            except Exception as e:
                print(f"  [FAIL] {label}: {e}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  BETH → Neo4j Full Loader (train + val + test)")
    print("=" * 60)
    print(f"  Base dir   : {BASE_DIR}")
    print(f"  Neo4j URI  : {NEO4J_URI}")
    print(f"  Batch size : {BATCH_SIZE}\n")

    # Verify all folders exist before starting
    missing = []
    for name, cfg in SPLITS.items():
        if not cfg["folder"].exists():
            missing.append(str(cfg["folder"]))
    if missing:
        print("[ERROR] These folders were not found:")
        for m in missing:
            print(f"  → {m}")
        print("\n  Update BASE_DIR at the top of this script to your actual path.")
        sys.exit(1)

    driver = connect(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        clear_db(driver)
        setup_schema(driver)

        grand_files = 0
        grand_rows  = 0
        grand_start = time.time()

        for split_name, cfg in SPLITS.items():
            files, rows = load_split(
                driver,
                split_name,
                cfg["folder"],
                cfg["filter_evil"]
            )
            grand_files += files
            grand_rows  += rows

        grand_elapsed = time.time() - grand_start

        print(f"\n{'='*60}")
        print("  ALL SPLITS LOADED")
        print(f"{'='*60}")
        print(f"  Total files  : {grand_files}")
        print(f"  Total rows   : {grand_rows:,}")
        print(f"  Total time   : {grand_elapsed:.1f}s")
        print(f"  Speed        : {grand_rows/grand_elapsed:,.0f} rows/s")

        print_stats(driver)
        verify(driver)

        print(f"\n{'='*60}")
        print("  Neo4j is ready. Run extract_pyg.py next.")
        print(f"{'='*60}\n")

    finally:
        driver.close()
        print("[Neo4j] Driver closed.")


if __name__ == "__main__":
    main()
