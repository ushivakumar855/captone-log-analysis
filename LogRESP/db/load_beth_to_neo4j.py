"""
load_beth_to_neo4j.py — Load pre-processed BETH JSON chunks into Neo4j
========================================================================
Reads the pre-processed JSON files (from beth_preprocess.py) and creates
graph nodes + relationships in Neo4j that are COMPATIBLE with the existing
LogRESP context_retriever.py Cypher queries.

LogRESP's context_retriever expects:
    (:Process {id, cmdLine, timestamp})
    (:File    {path})
    (:Network {ip, port})
    (:Process)-[:SPAWNED]->(:Process)
    (:Process)-[:ACCESSED]->(:File)
    (:Process)-[:CONNECTED_TO]->(:Network)

Graph schema created by this script:

    Node labels:
        Host         — {hostName}
        User         — {userId, is_root, is_real_user}
        Process      — {processId, hostName, id (=str processId), cmdLine (=processName), processName}
        SyscallEvent — {eventName, timestamp, returnValue, sus, evil, event_category, ...}
        File         — {path, path_prefix, has_sensitive_path, flags_raw, flags_category}
        Network      — {domain, type}

    Relationships:
        (Process)-[:RUNS_ON]->(Host)
        (Process)-[:RUNS_AS]->(User)
        (Process)-[:EMITS]->(SyscallEvent)
        (parent:Process)-[:SPAWNED]->(child:Process)
        (Process)-[:ACCESSED]->(File)
        (Process)-[:CONNECTED_TO]->(Network)

Usage:
    cd LogRESP/db/
    python load_beth_to_neo4j.py

    Environment variable overrides:
        NEO4J_URI       bolt://localhost:7687   (default)
        NEO4J_USER      test1-beth-data         (default)
        NEO4J_PASS      test1-beth123           (default)
        BETH_JSON_DIR   path to preprocessed/train folder

Author: Auto-generated for LogRESP capstone project
"""

import os
import sys
import json
import time
from pathlib import Path

try:
    from neo4j import GraphDatabase
except ImportError:
    print("[ERROR] 'neo4j' Python driver not installed.")
    print("  Install it with:  pip install neo4j")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

# Neo4j connection — local Neo4j Desktop instance
NEO4J_URI      = os.getenv("NEO4J_URI",  "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")           # ← FIXED: was "test1-beth-data" (that's the instance name, not the user)
NEO4J_PASSWORD = os.getenv("NEO4J_PASS", "test1-beth123")

# Path to the pre-processed JSON folder (the train/ folder under preprocessed/)
# Update this path to match your local directory structure
BETH_JSON_DIR = Path(os.getenv(
    "BETH_JSON_DIR",
    r"C:\Users\Student\Downloads\test1\dataset\preprocessed\train"
))

# Batch size for Neo4j UNWIND operations
# 500 is a good balance between speed and memory for ~500-row chunk files.
# Increase to 1000 if your machine has plenty of RAM, or decrease to 200
# if you see Java heap errors in Neo4j Desktop.
BATCH_SIZE = 500


# ═══════════════════════════════════════════════════════════
# NEO4J DRIVER
# ═══════════════════════════════════════════════════════════

def get_driver():
    """Create and return a Neo4j driver."""
    print(f"[Neo4j] Connecting to {NEO4J_URI} as '{NEO4J_USER}'...")
    try:
        driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_pool_size=10,
            connection_timeout=30,
        )
        driver.verify_connectivity()
        print("[Neo4j] Connected successfully.\n")
        return driver
    except Exception as e:
        print(f"\n[Neo4j] Connection FAILED: {e}\n")
        print("Troubleshooting:")
        print("  1. Open Neo4j Desktop and make sure your DBMS is Started (green status).")
        print(f"  2. Check URI — current: {NEO4J_URI}")
        print(f"     For Neo4j Desktop the default is bolt://localhost:7687")
        print(f"  3. Check credentials — current user: '{NEO4J_USER}'")
        print(f"     If you haven't changed it, try user='neo4j' with your set password.")
        print("  4. Make sure no firewall is blocking port 7687.")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════
# SCHEMA SETUP — Indexes and Constraints
# ═══════════════════════════════════════════════════════════

def setup_schema(driver):
    """Create indexes and constraints for fast lookups."""
    print("[Schema] Creating indexes and constraints...")

    schema_queries = [
        # ── Uniqueness constraints (auto-create indexes) ──
        ("Host(hostName)",     "CREATE CONSTRAINT IF NOT EXISTS FOR (h:Host) REQUIRE h.hostName IS UNIQUE"),
        ("User(userId)",       "CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.userId IS UNIQUE"),

        # ── Composite index for Process (same PID on different hosts) ──
        ("Process(processId,hostName)", "CREATE INDEX IF NOT EXISTS FOR (p:Process) ON (p.processId, p.hostName)"),

        # ── Index on Process.id for context_retriever.py compatibility ──
        ("Process(id)",        "CREATE INDEX IF NOT EXISTS FOR (p:Process) ON (p.id)"),

        # ── File path lookups ──
        ("File(path)",         "CREATE INDEX IF NOT EXISTS FOR (f:File) ON (f.path)"),

        # ── Network domain lookups ──
        ("Network(domain)",    "CREATE INDEX IF NOT EXISTS FOR (n:Network) ON (n.domain)"),

        # ── SyscallEvent time-range and threat filtering ──
        ("SyscallEvent(timestamp)", "CREATE INDEX IF NOT EXISTS FOR (e:SyscallEvent) ON (e.timestamp)"),
        ("SyscallEvent(evil)",      "CREATE INDEX IF NOT EXISTS FOR (e:SyscallEvent) ON (e.evil)"),
        ("SyscallEvent(sus)",       "CREATE INDEX IF NOT EXISTS FOR (e:SyscallEvent) ON (e.sus)"),
    ]

    with driver.session() as session:
        for label, q in schema_queries:
            try:
                session.run(q)
                print(f"  [OK] {label}")
            except Exception as e:
                print(f"  [SKIP] {label} — {str(e)[:80]}")

    print("[Schema] Done.\n")


# ═══════════════════════════════════════════════════════════
# CYPHER QUERIES FOR BATCH LOADING
# ═══════════════════════════════════════════════════════════

# ── 1. Host nodes ──
CREATE_HOSTS = """
UNWIND $batch AS rec
MERGE (h:Host {hostName: rec.host.hostName})
"""

# ── 2. User nodes ──
CREATE_USERS = """
UNWIND $batch AS rec
MERGE (u:User {userId: rec.user.userId})
ON CREATE SET
    u.is_root      = rec.user.is_root,
    u.is_real_user = rec.user.is_real_user
"""

# ── 3. Process nodes ──
# processId+hostName = composite key (same PID may exist on different hosts)
# .id = string(processId) → used by context_retriever.py: MATCH (p:Process {id: $pid})
# .cmdLine = processName  → used by context_retriever.py for display
CREATE_PROCESSES = """
UNWIND $batch AS rec
MERGE (p:Process {processId: rec.process.processId, hostName: rec.host.hostName})
ON CREATE SET
    p.id          = toString(rec.process.processId),
    p.cmdLine     = rec.process.processName,
    p.processName = rec.process.processName
"""

# ── 4. Process → Host (RUNS_ON) ──
CREATE_RUNS_ON = """
UNWIND $batch AS rec
MATCH (p:Process {processId: rec.process.processId, hostName: rec.host.hostName})
MATCH (h:Host {hostName: rec.host.hostName})
MERGE (p)-[:RUNS_ON]->(h)
"""

# ── 5. Process → User (RUNS_AS) ──
CREATE_RUNS_AS = """
UNWIND $batch AS rec
MATCH (p:Process {processId: rec.process.processId, hostName: rec.host.hostName})
MATCH (u:User {userId: rec.user.userId})
MERGE (p)-[:RUNS_AS]->(u)
"""

# ── 6. Parent → Child Process (SPAWNED) ──
# parentProcessId=0 means no parent (init) → skip those
CREATE_SPAWNED = """
UNWIND $batch AS rec
WITH rec
WHERE rec.process.parentProcessId > 0
MERGE (parent:Process {processId: rec.process.parentProcessId, hostName: rec.host.hostName})
ON CREATE SET
    parent.id      = toString(rec.process.parentProcessId),
    parent.cmdLine = 'unknown'
MERGE (child:Process {processId: rec.process.processId, hostName: rec.host.hostName})
MERGE (parent)-[:SPAWNED]->(child)
"""

# ── 7. SyscallEvent nodes + Process→Event (EMITS) ──
CREATE_EVENTS = """
UNWIND $batch AS rec
CREATE (e:SyscallEvent {
    eventName:         rec.event.eventName,
    timestamp:         rec.event.timestamp,
    returnValue:       rec.event.returnValue,
    sus:               rec.event.sus,
    evil:              rec.event.evil,
    event_category:    rec.event.event_category,
    is_delete_op:      rec.event.is_delete_op,
    is_exec_op:        rec.event.is_exec_op,
    is_network_op:     rec.event.is_network_op,
    is_failed_syscall: rec.event.is_failed_syscall
})
WITH e, rec
MATCH (p:Process {processId: rec.process.processId, hostName: rec.host.hostName})
CREATE (p)-[:EMITS]->(e)
"""

# ── 8. File nodes + Process→File (ACCESSED) ──
# Only records that have a file_path key
CREATE_FILES = """
UNWIND $batch AS rec
MERGE (f:File {path: rec.file_path.pathname})
ON CREATE SET
    f.path_prefix       = rec.file_path.path_prefix,
    f.has_sensitive_path = rec.file_path.has_sensitive_path
SET
    f.flags_raw      = COALESCE(rec.file_path.flags_raw, f.flags_raw),
    f.flags_category = COALESCE(rec.file_path.flags_category, f.flags_category)
WITH f, rec
MATCH (p:Process {processId: rec.process.processId, hostName: rec.host.hostName})
MERGE (p)-[:ACCESSED]->(f)
"""

# ── 9. Network/Socket nodes + Process→Network (CONNECTED_TO) ──
# Only records that have a socket key
CREATE_SOCKETS = """
UNWIND $batch AS rec
MERGE (n:Network {domain: rec.socket.domain})
ON CREATE SET
    n.type = rec.socket.type
WITH n, rec
MATCH (p:Process {processId: rec.process.processId, hostName: rec.host.hostName})
MERGE (p)-[:CONNECTED_TO]->(n)
"""


# ═══════════════════════════════════════════════════════════
# BATCH LOADER
# ═══════════════════════════════════════════════════════════

def run_batch(session, query, batch, label):
    """Execute a Cypher UNWIND query with a batch of records."""
    if not batch:
        return 0
    try:
        result = session.run(query, batch=batch)
        summary = result.consume()
        return summary.counters.nodes_created + summary.counters.relationships_created
    except Exception as e:
        print(f"\n    [ERROR] {label}: {e}")
        return 0


def load_json_file(driver, json_path):
    """Load a single pre-processed JSON file into Neo4j."""
    print(f"  Loading {json_path.name}...", end=" ", flush=True)
    t0 = time.time()

    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    total_records = len(records)
    total_created = 0

    # Process in batches
    for i in range(0, total_records, BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]

        # Pre-filter sub-batches for optional nodes (Python-side, not Cypher)
        file_batch   = [r for r in batch if "file_path" in r]
        socket_batch = [r for r in batch if "socket" in r]

        with driver.session() as session:
            # Order matters — nodes before relationships

            # 1. Host + User + Process nodes
            total_created += run_batch(session, CREATE_HOSTS, batch, "Hosts")
            total_created += run_batch(session, CREATE_USERS, batch, "Users")
            total_created += run_batch(session, CREATE_PROCESSES, batch, "Processes")

            # 2. Relationships between existing nodes
            total_created += run_batch(session, CREATE_RUNS_ON, batch, "RUNS_ON")
            total_created += run_batch(session, CREATE_RUNS_AS, batch, "RUNS_AS")
            total_created += run_batch(session, CREATE_SPAWNED, batch, "SPAWNED")

            # 3. Events (one per record — always present)
            total_created += run_batch(session, CREATE_EVENTS, batch, "Events+EMITS")

            # 4. Optional: File nodes + ACCESSED
            if file_batch:
                total_created += run_batch(session, CREATE_FILES, file_batch, "Files+ACCESSED")

            # 5. Optional: Network nodes + CONNECTED_TO
            if socket_batch:
                total_created += run_batch(session, CREATE_SOCKETS, socket_batch, "Sockets+CONNECTED_TO")

    elapsed = time.time() - t0
    print(f"{total_records} records -> {total_created} graph elements ({elapsed:.1f}s)")
    return total_records


# ═══════════════════════════════════════════════════════════
# CLEAR DATABASE (batched for large graphs)
# ═══════════════════════════════════════════════════════════

def clear_database(driver):
    """Remove all existing nodes and relationships in batches."""
    print("[Clear] Checking existing data...")

    with driver.session() as session:
        count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        print(f"  Existing nodes: {count:,}")

        if count == 0:
            print("  Database already empty — nothing to clear.\n")
            return

        print(f"  Deleting in batches of 10,000...")
        deleted_total = 0
        while True:
            result = session.run("""
                MATCH (n)
                WITH n LIMIT 10000
                DETACH DELETE n
                RETURN count(*) AS deleted
            """)
            deleted = result.single()["deleted"]
            if deleted == 0:
                break
            deleted_total += deleted
            print(f"    ...deleted {deleted_total:,} nodes so far", end="\r")

        print(f"  [OK] Cleared {deleted_total:,} nodes (and their relationships).\n")


# ═══════════════════════════════════════════════════════════
# GRAPH STATS + VERIFICATION
# ═══════════════════════════════════════════════════════════

def print_graph_stats(driver):
    """Print summary statistics of the loaded graph."""
    print("\n[Stats] Graph database contents:")

    queries = [
        ("Total nodes",          "MATCH (n) RETURN count(n) AS c"),
        ("Total relationships",  "MATCH ()-[r]-() RETURN count(r) AS c"),
        ("",                     None),  # divider
        ("Host nodes",           "MATCH (n:Host) RETURN count(n) AS c"),
        ("Process nodes",        "MATCH (n:Process) RETURN count(n) AS c"),
        ("User nodes",           "MATCH (n:User) RETURN count(n) AS c"),
        ("SyscallEvent nodes",   "MATCH (n:SyscallEvent) RETURN count(n) AS c"),
        ("File nodes",           "MATCH (n:File) RETURN count(n) AS c"),
        ("Network nodes",        "MATCH (n:Network) RETURN count(n) AS c"),
        ("",                     None),  # divider
        ("RUNS_ON edges",        "MATCH ()-[r:RUNS_ON]-() RETURN count(r) AS c"),
        ("RUNS_AS edges",        "MATCH ()-[r:RUNS_AS]-() RETURN count(r) AS c"),
        ("SPAWNED edges",        "MATCH ()-[r:SPAWNED]-() RETURN count(r) AS c"),
        ("EMITS edges",          "MATCH ()-[r:EMITS]-() RETURN count(r) AS c"),
        ("ACCESSED edges",       "MATCH ()-[r:ACCESSED]-() RETURN count(r) AS c"),
        ("CONNECTED_TO edges",   "MATCH ()-[r:CONNECTED_TO]-() RETURN count(r) AS c"),
        ("",                     None),  # divider
        ("Evil events (evil=1)", "MATCH (e:SyscallEvent {evil: 1}) RETURN count(e) AS c"),
        ("Suspicious (sus=1)",   "MATCH (e:SyscallEvent {sus: 1}) RETURN count(e) AS c"),
    ]

    with driver.session() as session:
        for label, query in queries:
            if query is None:
                print("  " + "-" * 40)
                continue
            try:
                count = session.run(query).single()["c"]
                print(f"  {label:.<35} {count:>10,}")
            except Exception as e:
                print(f"  {label:.<35} ERROR: {e}")


def run_verification(driver):
    """Run sample queries to verify compatibility with LogRESP's context_retriever."""
    print(f"\n{'─' * 60}")
    print("VERIFICATION — context_retriever.py compatibility")
    print(f"{'─' * 60}")

    with driver.session() as session:
        # Test 1: Process.id + Process.cmdLine exist
        rows = list(session.run("""
            MATCH (p:Process)
            WHERE p.id IS NOT NULL AND p.cmdLine IS NOT NULL
            RETURN p.id AS id, p.cmdLine AS cmd
            LIMIT 3
        """))
        if rows:
            print("\n  [PASS] Process.id and Process.cmdLine present:")
            for r in rows:
                print(f"         id='{r['id']}', cmdLine='{r['cmd']}'")
        else:
            print("\n  [FAIL] No Process nodes with id/cmdLine found!")

        # Test 2: SPAWNED relationship
        rows = list(session.run("""
            MATCH (parent:Process)-[:SPAWNED]->(child:Process)
            RETURN parent.processName AS parent, parent.processId AS ppid,
                   child.processName AS child, child.processId AS cpid
            LIMIT 3
        """))
        if rows:
            print("\n  [PASS] SPAWNED relationships:")
            for r in rows:
                print(f"         {r['parent']} (pid={r['ppid']}) -[:SPAWNED]-> {r['child']} (pid={r['cpid']})")
        else:
            print("\n  [WARN] No SPAWNED relationships (possible if all parentProcessId=0)")

        # Test 3: ACCESSED relationship
        rows = list(session.run("""
            MATCH (p:Process)-[:ACCESSED]->(f:File)
            RETURN p.processName AS proc, f.path AS path
            LIMIT 3
        """))
        if rows:
            print("\n  [PASS] ACCESSED relationships:")
            for r in rows:
                print(f"         {r['proc']} -[:ACCESSED]-> {r['path']}")
        else:
            print("\n  [WARN] No ACCESSED (File) relationships found")

        # Test 4: CONNECTED_TO relationship
        rows = list(session.run("""
            MATCH (p:Process)-[:CONNECTED_TO]->(n:Network)
            RETURN p.processName AS proc, n.domain AS domain
            LIMIT 3
        """))
        if rows:
            print("\n  [PASS] CONNECTED_TO relationships:")
            for r in rows:
                print(f"         {r['proc']} -[:CONNECTED_TO]-> {r['domain']}")
        else:
            print("\n  [INFO] No CONNECTED_TO (Network) relationships (normal if training data has no sockets)")

        # Test 5: Evil events
        rows = list(session.run("""
            MATCH (p:Process)-[:EMITS]->(e:SyscallEvent {evil: 1})
            RETURN p.processName AS proc, e.eventName AS event, e.timestamp AS ts
            LIMIT 5
        """))
        if rows:
            print(f"\n  [PASS] Evil events found ({len(rows)} samples):")
            for r in rows:
                print(f"         {r['proc']} emitted '{r['event']}' @ t={r['ts']:.6f}")
        else:
            print("\n  [INFO] No evil=1 events (normal for some training splits)")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    # ── All prints use flush=True so output appears immediately in any terminal/IDE ──
    print("=" * 60, flush=True)
    print("  BETH Dataset → Neo4j Graph Loader", flush=True)
    print("  (LogRESP Capstone Project)", flush=True)
    print("=" * 60, flush=True)
    print(f"\n  Neo4j URI:    {NEO4J_URI}", flush=True)
    print(f"  Neo4j User:   {NEO4J_USER}", flush=True)
    print(f"  JSON folder:  {BETH_JSON_DIR}", flush=True)
    print(f"  Batch size:   {BATCH_SIZE}", flush=True)

    # ── DEBUG: Show exactly what Python sees for the path ──
    print(f"\n[DEBUG] Checking JSON folder path...", flush=True)
    print(f"[DEBUG] Resolved path : {BETH_JSON_DIR.resolve()}", flush=True)
    print(f"[DEBUG] Folder exists : {BETH_JSON_DIR.exists()}", flush=True)
    if BETH_JSON_DIR.exists():
        all_files = list(BETH_JSON_DIR.iterdir())
        print(f"[DEBUG] Files in folder: {len(all_files)}", flush=True)
        for f in all_files[:10]:  # show first 10 files
            print(f"[DEBUG]   -> {f.name}", flush=True)
        if len(all_files) > 10:
            print(f"[DEBUG]   ... and {len(all_files)-10} more", flush=True)

    # ── Validate JSON folder ──
    if not BETH_JSON_DIR.exists():
        print(f"\n[ERROR] JSON folder not found:\n  {BETH_JSON_DIR}", flush=True)
        print("\n  SOLUTION: Set the correct path using an environment variable:", flush=True)
        print('    Windows CMD:  set BETH_JSON_DIR=C:\\your\\actual\\path\\to\\train', flush=True)
        print('    PowerShell:   $env:BETH_JSON_DIR="C:\\your\\actual\\path\\to\\train"', flush=True)
        print("    Then run:     python load_beth_to_neo4j.py", flush=True)
        sys.exit(1)

    # ── Find part_*.json files ──
    print(f"\n[DEBUG] Searching for part_*.json files...", flush=True)
    json_files = sorted(
        BETH_JSON_DIR.glob("part_*.json"),
        key=lambda f: int(f.stem.split("_")[1]) if f.stem.split("_")[1].isdigit() else 0
    )
    print(f"[DEBUG] Found {len(json_files)} matching file(s).", flush=True)

    if not json_files:
        print(f"\n[ERROR] No part_*.json files found in:\n  {BETH_JSON_DIR}", flush=True)
        print("\n  Expected files named like: part_1.json, part_2.json, ...", flush=True)
        print("\n  Files actually present in that folder:", flush=True)
        for f in BETH_JSON_DIR.iterdir():
            print(f"    {f.name}", flush=True)
        sys.exit(1)

    print(f"\n  Found {len(json_files)} JSON chunk file(s):", flush=True)
    total_size_kb = 0
    for jf in json_files:
        sz = jf.stat().st_size / 1024
        total_size_kb += sz
        print(f"    {jf.name:>20}  ({sz:,.0f} KB)", flush=True)
    print(f"    {'Total':>20}  ({total_size_kb:,.0f} KB)", flush=True)

    # ── Auto-confirm (no silent hang waiting for input) ──
    # If you want the confirmation prompt back, change AUTO_CONFIRM to False
    AUTO_CONFIRM = True
    print(f"\n{'─' * 60}", flush=True)
    if AUTO_CONFIRM:
        print("[INFO] AUTO_CONFIRM=True — skipping prompt, proceeding with load.", flush=True)
    else:
        answer = input("This will CLEAR the database and reload all data. Continue? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.", flush=True)
            sys.exit(0)

    # ── Connect ──
    print("\n[Step 1/6] Connecting to Neo4j...", flush=True)
    driver = get_driver()

    try:
        # Step 2: Clear existing data
        print("\n[Step 2/6] Clearing existing database...", flush=True)
        clear_database(driver)

        # Step 3: Create indexes + constraints
        print("[Step 3/6] Setting up schema...", flush=True)
        setup_schema(driver)

        # Step 4: Load each JSON chunk
        print(f"{'─' * 60}", flush=True)
        print(f"[Step 4/6] Loading {len(json_files)} chunk file(s) into Neo4j...", flush=True)
        print(f"{'─' * 60}", flush=True)

        grand_total = 0
        grand_start = time.time()

        for idx, json_file in enumerate(json_files, 1):
            print(f"\n[File {idx}/{len(json_files)}] Processing {json_file.name}...", flush=True)
            grand_total += load_json_file(driver, json_file)

        grand_elapsed = time.time() - grand_start

        # Step 5: Summary
        print(f"\n[Step 5/6] Load summary:", flush=True)
        print(f"\n{'=' * 60}", flush=True)
        print("  LOADING COMPLETE", flush=True)
        print(f"{'=' * 60}", flush=True)
        print(f"  Files loaded:  {len(json_files)}", flush=True)
        print(f"  Total records: {grand_total:,}", flush=True)
        print(f"  Total time:    {grand_elapsed:.1f}s", flush=True)
        if grand_elapsed > 0:
            print(f"  Speed:         {grand_total / grand_elapsed:,.0f} records/sec", flush=True)

        # Step 6: Stats
        print(f"\n[Step 6/6] Graph statistics:", flush=True)
        print_graph_stats(driver)

        # Verification
        run_verification(driver)

        print(f"\n{'=' * 60}", flush=True)
        print("  Your BETH training data is now in Neo4j.", flush=True)
        print("  The LogRESP context_retriever.py can query it via Process.id", flush=True)
        print(f"{'=' * 60}\n", flush=True)

    finally:
        driver.close()
        print("[Neo4j] Driver closed.")


if __name__ == "__main__":
    main()