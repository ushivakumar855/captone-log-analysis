"""
validate_neo4j_load.py  —  BETH → Neo4j  Modular Validation Script
====================================================================
Each CHECK BLOCK below can be independently enabled/disabled.
To skip a block:  change  RUN_BLOCK_X = True  →  RUN_BLOCK_X = False
To run  a block:  change  RUN_BLOCK_X = False →  RUN_BLOCK_X = True

BLOCKS AVAILABLE:
    BLOCK 1  — Neo4j connection test
    BLOCK 2  — Locate and inspect part_5.json
    BLOCK 3  — Sample load (first 50 records from part_5.json)
    BLOCK 4  — Full file load check (counts all part_*.json vs Neo4j)
    BLOCK 5  — Node + relationship counts (what is in Neo4j right now)
    BLOCK 6  — Schema compatibility (LogRESP context_retriever.py fields)
    BLOCK 7  — Live data preview (sample rows from Neo4j)
    BLOCK 8  — Evil / suspicious event summary

Usage:
    python validate_neo4j_load.py
"""

import os
import sys
import json
import time
from pathlib import Path

try:
    from neo4j import GraphDatabase
except ImportError:
    print("[ERROR] neo4j driver not installed.  Run:  pip install neo4j")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════
#  CONFIGURATION  — update these to match your setup
# ══════════════════════════════════════════════════════════════

NEO4J_URI      = os.getenv("NEO4J_URI",  "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASS", "test1-beth123")

BETH_JSON_DIR  = Path(os.getenv(
    "BETH_JSON_DIR",
    r"C:\Users\Student\Downloads\test1\dataset\preprocessed\test"   # <- your path
))

SAMPLE_SIZE = 50   # how many records Block 3 loads for the smoke test


# ══════════════════════════════════════════════════════════════
#  TOGGLE EACH BLOCK HERE  (True = run it, False = skip it)
# ══════════════════════════════════════════════════════════════

RUN_BLOCK_1 = True    # Connection test
RUN_BLOCK_2 = True    # Inspect part_5.json
RUN_BLOCK_3 = False    # Sample load  *** CLEARS the database first! ***
RUN_BLOCK_4 = True    # Check all JSON files are represented in Neo4j
RUN_BLOCK_5 = True    # Node + relationship counts
RUN_BLOCK_6 = True    # Schema / field compatibility
RUN_BLOCK_7 = True    # Live data preview
RUN_BLOCK_8 = True    # Evil / suspicious summary


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def hdr(title):
    print(f"\n{'='*62}", flush=True)
    print(f"  {title}", flush=True)
    print(f"{'='*62}", flush=True)

def ok(label, detail=""):
    print(f"  [PASS]  {label}" + (f"  ->  {detail}" if detail else ""), flush=True)

def fail(label, detail=""):
    print(f"  [FAIL]  {label}" + (f"  ->  {detail}" if detail else ""), flush=True)

def info(label, detail=""):
    print(f"  [INFO]  {label}" + (f"  ->  {detail}" if detail else ""), flush=True)

def warn(label, detail=""):
    print(f"  [WARN]  {label}" + (f"  ->  {detail}" if detail else ""), flush=True)

def skipped(block_name):
    print(f"\n  -- {block_name} skipped (set to False) --", flush=True)


# ══════════════════════════════════════════════════════════════
#  SHARED: batched database clear  (safe for any DB size)
# ══════════════════════════════════════════════════════════════

def clear_db_batched(driver):
    """
    Delete all nodes in batches of 5,000.
    Using LIMIT avoids the hang that happens when you try to
    DETACH DELETE everything in one transaction on a large graph.
    """
    print("  Clearing database in batches of 5,000 nodes...", flush=True)
    with driver.session() as session:
        total = 0
        while True:
            result  = session.run(
                "MATCH (n) WITH n LIMIT 5000 DETACH DELETE n RETURN count(*) AS d"
            )
            deleted = result.single()["d"]
            if deleted == 0:
                break
            total += deleted
            print(f"    deleted {total:,} nodes so far...", flush=True)
    print(f"  Done. Cleared {total:,} nodes total.", flush=True)


# ══════════════════════════════════════════════════════════════
#  BLOCK 1 — Neo4j Connection Test
# ══════════════════════════════════════════════════════════════

def block1_connection():
    hdr("BLOCK 1 -- Neo4j Connection Test")
    print(f"  URI  : {NEO4J_URI}", flush=True)
    print(f"  User : {NEO4J_USER}", flush=True)
    try:
        driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            connection_timeout=10,
        )
        driver.verify_connectivity()
        ok("Connected to Neo4j", NEO4J_URI)
        return driver
    except Exception as e:
        fail("Connected to Neo4j", str(e))
        print("\n  Fixes:", flush=True)
        print("    - Neo4j Desktop: click the Start button on your DBMS", flush=True)
        print("    - Username must be 'neo4j', not the instance display name", flush=True)
        sys.exit(1)


# ══════════════════════════════════════════════════════════════
#  BLOCK 2 — Inspect part_5.json
# ══════════════════════════════════════════════════════════════

def block2_inspect_json():
    hdr("BLOCK 2 -- Inspect part_5.json")

    if not BETH_JSON_DIR.exists():
        fail("JSON folder exists", str(BETH_JSON_DIR))
        print(f"\n  Fix: update BETH_JSON_DIR at the top of this script.", flush=True)
        return None, None
    ok("JSON folder exists", str(BETH_JSON_DIR))

    json_path = BETH_JSON_DIR / "part_5.json"
    if not json_path.exists():
        fail("part_5.json exists")
        print("\n  Files present in folder:", flush=True)
        for f in sorted(BETH_JSON_DIR.iterdir()):
            print(f"    {f.name}", flush=True)
        return None, None
    ok("part_5.json exists", str(json_path))

    kb = json_path.stat().st_size / 1024
    ok("File size", f"{kb:,.0f} KB")

    try:
        with open(json_path, "r", encoding="utf-8") as fh:
            records = json.load(fh)
        ok("JSON parses cleanly", f"{len(records):,} records")
    except Exception as e:
        fail("JSON parses cleanly", str(e))
        return json_path, None

    first    = records[0]
    expected = {"host", "user", "process", "event"}
    present  = set(first.keys())
    if expected.issubset(present):
        ok("Core keys present (host, user, process, event)", str(sorted(present)))
    else:
        fail("Core keys present", f"missing: {expected - present}")

    has_file   = any("file_path" in r for r in records[:200])
    has_socket = any("socket"    in r for r in records[:200])
    info("file_path key (first 200 records)", "Yes" if has_file   else "No -- normal")
    info("socket    key (first 200 records)", "Yes" if has_socket else "No -- normal")

    return json_path, records


# ══════════════════════════════════════════════════════════════
#  BLOCK 3 — Sample Load (50 records, clears DB first)
# ══════════════════════════════════════════════════════════════

# Condensed Cypher — same logic as load_beth_to_neo4j.py
_H  = "UNWIND $b AS r MERGE (h:Host {hostName:r.host.hostName})"
_U  = "UNWIND $b AS r MERGE (u:User {userId:r.user.userId}) ON CREATE SET u.is_root=r.user.is_root,u.is_real_user=r.user.is_real_user"
_P  = "UNWIND $b AS r MERGE (p:Process {processId:r.process.processId,hostName:r.host.hostName}) ON CREATE SET p.id=toString(r.process.processId),p.cmdLine=r.process.processName,p.processName=r.process.processName"
_RO = "UNWIND $b AS r MATCH (p:Process{processId:r.process.processId,hostName:r.host.hostName}) MATCH (h:Host{hostName:r.host.hostName}) MERGE (p)-[:RUNS_ON]->(h)"
_RA = "UNWIND $b AS r MATCH (p:Process{processId:r.process.processId,hostName:r.host.hostName}) MATCH (u:User{userId:r.user.userId}) MERGE (p)-[:RUNS_AS]->(u)"
_SP = "UNWIND $b AS r WITH r WHERE r.process.parentProcessId > 0 MERGE (par:Process{processId:r.process.parentProcessId,hostName:r.host.hostName}) ON CREATE SET par.id=toString(r.process.parentProcessId),par.cmdLine='unknown' MERGE (ch:Process{processId:r.process.processId,hostName:r.host.hostName}) MERGE (par)-[:SPAWNED]->(ch)"
_EV = "UNWIND $b AS r CREATE (e:SyscallEvent{eventName:r.event.eventName,timestamp:r.event.timestamp,returnValue:r.event.returnValue,sus:r.event.sus,evil:r.event.evil,event_category:r.event.event_category,is_delete_op:r.event.is_delete_op,is_exec_op:r.event.is_exec_op,is_network_op:r.event.is_network_op,is_failed_syscall:r.event.is_failed_syscall}) WITH e,r MATCH (p:Process{processId:r.process.processId,hostName:r.host.hostName}) CREATE (p)-[:EMITS]->(e)"
_FI = "UNWIND $b AS r MERGE (f:File{path:r.file_path.pathname}) ON CREATE SET f.path_prefix=r.file_path.path_prefix,f.has_sensitive_path=r.file_path.has_sensitive_path SET f.flags_raw=COALESCE(r.file_path.flags_raw,f.flags_raw),f.flags_category=COALESCE(r.file_path.flags_category,f.flags_category) WITH f,r MATCH (p:Process{processId:r.process.processId,hostName:r.host.hostName}) MERGE (p)-[:ACCESSED]->(f)"
_SK = "UNWIND $b AS r MERGE (n:Network{domain:r.socket.domain}) ON CREATE SET n.type=r.socket.type WITH n,r MATCH (p:Process{processId:r.process.processId,hostName:r.host.hostName}) MERGE (p)-[:CONNECTED_TO]->(n)"

def _run_cypher(session, query, batch, label):
    try:
        s = session.run(query, b=batch).consume()
        n = s.counters.nodes_created + s.counters.relationships_created
        print(f"    [PASS]  {label:<42}  +{n} elements", flush=True)
        return n
    except Exception as e:
        print(f"    [FAIL]  {label:<42}  {e}", flush=True)
        return -1

def block3_sample_load(driver, records):
    hdr(f"BLOCK 3 -- Sample Load ({SAMPLE_SIZE} records from part_5.json)")
    print("  NOTE: This block CLEARS your Neo4j database before loading.", flush=True)
    print("        Set RUN_BLOCK_3 = False if you want to keep existing data.\n", flush=True)

    if records is None:
        warn("Skipping load -- no records available (Block 2 must run first)")
        return

    sample     = records[:SAMPLE_SIZE]
    file_batch = [r for r in sample if "file_path" in r]
    sock_batch = [r for r in sample if "socket"    in r]

    print(f"  Sample size    : {len(sample)}", flush=True)
    print(f"  With file_path : {len(file_batch)}", flush=True)
    print(f"  With socket    : {len(sock_batch)}", flush=True)
    print(flush=True)

    clear_db_batched(driver)
    print(flush=True)

    t0    = time.time()
    total = 0
    errs  = 0

    with driver.session() as s:
        steps = [
            (_H,  sample,      "Host nodes"),
            (_U,  sample,      "User nodes"),
            (_P,  sample,      "Process nodes"),
            (_RO, sample,      "RUNS_ON relationships"),
            (_RA, sample,      "RUNS_AS relationships"),
            (_SP, sample,      "SPAWNED relationships"),
            (_EV, sample,      "SyscallEvent nodes + EMITS"),
        ]
        if file_batch:
            steps.append((_FI, file_batch, "File nodes + ACCESSED"))
        if sock_batch:
            steps.append((_SK, sock_batch, "Network nodes + CONNECTED_TO"))

        for query, batch, label in steps:
            n = _run_cypher(s, query, batch, label)
            if n >= 0:
                total += n
            else:
                errs += 1

    elapsed = time.time() - t0
    print(f"\n  Total: {total:,} graph elements in {elapsed:.2f}s", flush=True)
    if errs == 0:
        ok("No Cypher errors during sample load")
    else:
        fail("Cypher errors during load", f"{errs} step(s) failed -- see above")


# ══════════════════════════════════════════════════════════════
#  BLOCK 4 — Check All JSON Files Are Represented in Neo4j
# ══════════════════════════════════════════════════════════════

def block4_all_files_loaded(driver):
    hdr("BLOCK 4 -- All JSON Files Loaded Check")
    print("  Compares record counts on disk vs. SyscallEvent count in Neo4j.", flush=True)
    print("  Run this AFTER load_beth_to_neo4j.py finishes the full load.\n", flush=True)

    json_files = sorted(BETH_JSON_DIR.glob("part_*.json"))
    if not json_files:
        warn("No part_*.json files found on disk")
        return

    print(f"  JSON files on disk: {len(json_files)}", flush=True)

    total_disk = 0
    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as fh:
                recs = json.load(fh)
            kb = jf.stat().st_size / 1024
            print(f"    {jf.name:<20}  {len(recs):>7,} records  ({kb:,.0f} KB)", flush=True)
            total_disk += len(recs)
        except Exception as e:
            print(f"    {jf.name:<20}  ERROR: {e}", flush=True)

    print(f"    {'TOTAL':<20}  {total_disk:>7,} records", flush=True)

    with driver.session() as session:
        event_count = session.run("MATCH (e:SyscallEvent) RETURN count(e) AS c").single()["c"]
        proc_count  = session.run("MATCH (p:Process)      RETURN count(p) AS c").single()["c"]
        node_count  = session.run("MATCH (n)              RETURN count(n) AS c").single()["c"]

    print(f"\n  Neo4j state:", flush=True)
    print(f"    Total nodes      : {node_count:>10,}", flush=True)
    print(f"    Processes        : {proc_count:>10,}", flush=True)
    print(f"    SyscallEvents    : {event_count:>10,}", flush=True)
    print(f"    Expected events  : {total_disk:>10,}  (one per record)", flush=True)

    if event_count >= int(total_disk * 0.95):
        ok("SyscallEvent count matches disk records",
           f"{event_count:,} / {total_disk:,}")
    elif event_count > 0:
        pct = event_count / total_disk * 100
        warn("Neo4j has fewer events than expected",
             f"{event_count:,} / {total_disk:,}  ({pct:.1f}%)")
        print("       -> Run load_beth_to_neo4j.py to do the full load.", flush=True)
    else:
        fail("Neo4j is empty",
             "Run load_beth_to_neo4j.py first, then re-run this check.")


# ══════════════════════════════════════════════════════════════
#  BLOCK 5 — Node + Relationship Counts
# ══════════════════════════════════════════════════════════════

def block5_counts(driver):
    hdr("BLOCK 5 -- Node + Relationship Counts")

    queries = [
        ("Total nodes",          "MATCH (n) RETURN count(n) AS c"),
        ("Total relationships",  "MATCH ()-[r]-() RETURN count(r) AS c"),
        (None, None),
        ("Host nodes",           "MATCH (n:Host)         RETURN count(n) AS c"),
        ("User nodes",           "MATCH (n:User)         RETURN count(n) AS c"),
        ("Process nodes",        "MATCH (n:Process)      RETURN count(n) AS c"),
        ("SyscallEvent nodes",   "MATCH (n:SyscallEvent) RETURN count(n) AS c"),
        ("File nodes",           "MATCH (n:File)         RETURN count(n) AS c"),
        ("Network nodes",        "MATCH (n:Network)      RETURN count(n) AS c"),
        (None, None),
        ("RUNS_ON edges",        "MATCH ()-[r:RUNS_ON]-()      RETURN count(r) AS c"),
        ("RUNS_AS edges",        "MATCH ()-[r:RUNS_AS]-()      RETURN count(r) AS c"),
        ("SPAWNED edges",        "MATCH ()-[r:SPAWNED]-()      RETURN count(r) AS c"),
        ("EMITS edges",          "MATCH ()-[r:EMITS]-()        RETURN count(r) AS c"),
        ("ACCESSED edges",       "MATCH ()-[r:ACCESSED]-()     RETURN count(r) AS c"),
        ("CONNECTED_TO edges",   "MATCH ()-[r:CONNECTED_TO]-() RETURN count(r) AS c"),
    ]

    must_have = {"Total nodes", "Process nodes", "SyscallEvent nodes", "EMITS edges"}

    with driver.session() as session:
        for label, q in queries:
            if label is None:
                print("  " + "-" * 48, flush=True)
                continue
            try:
                c = session.run(q).single()["c"]
                if c > 0:
                    icon = "[PASS]"
                elif label in must_have:
                    icon = "[FAIL]"
                else:
                    icon = "[INFO]"
                print(f"  {icon}  {label:<32}  {c:>10,}", flush=True)
            except Exception as e:
                print(f"  [FAIL]  {label:<32}  ERROR: {e}", flush=True)


# ══════════════════════════════════════════════════════════════
#  BLOCK 6 — Schema Compatibility (context_retriever.py)
# ══════════════════════════════════════════════════════════════

def block6_schema(driver):
    hdr("BLOCK 6 -- Schema Compatibility (LogRESP context_retriever.py)")

    with driver.session() as s:

        # Process.id and Process.cmdLine
        rows = list(s.run(
            "MATCH (p:Process) WHERE p.id IS NOT NULL AND p.cmdLine IS NOT NULL "
            "RETURN p.id AS id, p.cmdLine AS cmd LIMIT 3"
        ))
        if rows:
            ok("Process.id and Process.cmdLine fields exist")
            for r in rows:
                print(f"       id='{r['id']}'   cmdLine='{r['cmd']}'", flush=True)
        else:
            fail("Process.id / Process.cmdLine not found")

        # File.path
        row = s.run("MATCH (f:File) RETURN f.path AS p LIMIT 1").single()
        if row:
            ok("File.path exists", row["p"])
        else:
            info("File.path", "no File nodes (normal for small sample with no file records)")

        # Network.domain
        row = s.run("MATCH (n:Network) RETURN n.domain AS d LIMIT 1").single()
        if row:
            ok("Network.domain exists", row["d"])
        else:
            info("Network.domain", "no Network nodes (normal if no socket records)")

        # SPAWNED
        row = s.run(
            "MATCH (a:Process)-[:SPAWNED]->(b:Process) "
            "RETURN a.processName AS a, b.processName AS b LIMIT 1"
        ).single()
        if row:
            ok("SPAWNED relationship exists", f"{row['a']} -> {row['b']}")
        else:
            info("SPAWNED relationship", "none (possible if all parentProcessId=0)")

        # ACCESSED
        row = s.run(
            "MATCH (p:Process)-[:ACCESSED]->(f:File) "
            "RETURN p.processName AS p, f.path AS f LIMIT 1"
        ).single()
        if row:
            ok("ACCESSED relationship exists", f"{row['p']} -> {row['f']}")
        else:
            info("ACCESSED relationship", "none in current DB")

        # CONNECTED_TO
        row = s.run(
            "MATCH (p:Process)-[:CONNECTED_TO]->(n:Network) "
            "RETURN p.processName AS p, n.domain AS d LIMIT 1"
        ).single()
        if row:
            ok("CONNECTED_TO relationship exists", f"{row['p']} -> {row['d']}")
        else:
            info("CONNECTED_TO relationship", "none in current DB")

        # SyscallEvent required fields
        row = s.run(
            "MATCH (e:SyscallEvent) WHERE e.timestamp IS NOT NULL "
            "RETURN e.eventName AS n, e.sus AS s, e.evil AS ev LIMIT 1"
        ).single()
        if row:
            ok("SyscallEvent has timestamp / eventName / sus / evil",
               f"name='{row['n']}'  sus={row['s']}  evil={row['ev']}")
        else:
            fail("SyscallEvent fields missing or no events found")


# ══════════════════════════════════════════════════════════════
#  BLOCK 7 — Live Data Preview
# ══════════════════════════════════════════════════════════════

def block7_preview(driver):
    hdr("BLOCK 7 -- Live Data Preview")

    with driver.session() as s:

        print("\n  Top 5 processes by syscall count:", flush=True)
        rows = list(s.run("""
            MATCH (p:Process)-[:EMITS]->(e:SyscallEvent)
            RETURN p.processName AS name, p.processId AS pid, count(e) AS n
            ORDER BY n DESC LIMIT 5
        """))
        if rows:
            for r in rows:
                print(f"    pid={r['pid']:>6}   {r['name']:<30}   {r['n']:,} events", flush=True)
        else:
            print("    (no data)", flush=True)

        print("\n  5 most recent syscall events:", flush=True)
        rows = list(s.run("""
            MATCH (p:Process)-[:EMITS]->(e:SyscallEvent)
            RETURN p.processName AS proc, e.eventName AS ev,
                   e.timestamp AS ts, e.evil AS evil
            ORDER BY e.timestamp DESC LIMIT 5
        """))
        if rows:
            for r in rows:
                tag = "  *** EVIL ***" if r["evil"] == 1 else ""
                print(f"    t={r['ts']:<14.4f}  [{r['ev']:<22}]  {r['proc']}{tag}", flush=True)
        else:
            print("    (no data)", flush=True)

        print("\n  Hosts in graph:", flush=True)
        rows = list(s.run("MATCH (h:Host) RETURN h.hostName AS h ORDER BY h.hostName"))
        if rows:
            for r in rows:
                print(f"    {r['h']}", flush=True)
        else:
            print("    (no Host nodes)", flush=True)


# ══════════════════════════════════════════════════════════════
#  BLOCK 8 — Evil / Suspicious Event Summary
# ══════════════════════════════════════════════════════════════

def block8_evil_summary(driver):
    hdr("BLOCK 8 -- Evil / Suspicious Event Summary")

    with driver.session() as s:
        total      = s.run("MATCH (e:SyscallEvent)          RETURN count(e) AS c").single()["c"]
        evil_count = s.run("MATCH (e:SyscallEvent {evil:1}) RETURN count(e) AS c").single()["c"]
        sus_count  = s.run("MATCH (e:SyscallEvent {sus:1})  RETURN count(e) AS c").single()["c"]

        print(f"\n  Total SyscallEvents  : {total:>10,}", flush=True)
        print(f"  Evil  (evil=1)       : {evil_count:>10,}", flush=True)
        print(f"  Suspicious (sus=1)   : {sus_count:>10,}", flush=True)
        if total > 0:
            print(f"  Evil ratio           : {evil_count/total*100:>9.2f}%", flush=True)

        if evil_count > 0:
            print(f"\n  Sample evil events (earliest 5):", flush=True)
            rows = list(s.run("""
                MATCH (p:Process)-[:EMITS]->(e:SyscallEvent {evil:1})
                RETURN p.processName AS proc, e.eventName AS ev, e.timestamp AS ts
                ORDER BY e.timestamp LIMIT 5
            """))
            for r in rows:
                print(f"    [{r['ev']:<22}]  by {r['proc']:<25}  t={r['ts']:.4f}", flush=True)
        else:
            info("No evil=1 events in current DB",
                 "normal for test split or small sample")

        if sus_count > 0:
            print(f"\n  Sample suspicious events (earliest 5):", flush=True)
            rows = list(s.run("""
                MATCH (p:Process)-[:EMITS]->(e:SyscallEvent {sus:1})
                RETURN p.processName AS proc, e.eventName AS ev, e.timestamp AS ts
                ORDER BY e.timestamp LIMIT 5
            """))
            for r in rows:
                print(f"    [{r['ev']:<22}]  by {r['proc']:<25}  t={r['ts']:.4f}", flush=True)
        else:
            info("No sus=1 events in current DB", "normal for small sample")


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print(flush=True)
    print("╔══════════════════════════════════════════════════════╗", flush=True)
    print("║   BETH -> Neo4j   MODULAR VALIDATION SCRIPT         ║", flush=True)
    print("╚══════════════════════════════════════════════════════╝", flush=True)
    print(f"\n  Toggle blocks ON/OFF at the top of this file:", flush=True)
    print(f"    RUN_BLOCK_1 = {RUN_BLOCK_1}   (Connection test)", flush=True)
    print(f"    RUN_BLOCK_2 = {RUN_BLOCK_2}   (Inspect part_5.json)", flush=True)
    print(f"    RUN_BLOCK_3 = {RUN_BLOCK_3}   (Sample load -- CLEARS DB)", flush=True)
    print(f"    RUN_BLOCK_4 = {RUN_BLOCK_4}   (All files loaded check)", flush=True)
    print(f"    RUN_BLOCK_5 = {RUN_BLOCK_5}   (Counts)", flush=True)
    print(f"    RUN_BLOCK_6 = {RUN_BLOCK_6}   (Schema compatibility)", flush=True)
    print(f"    RUN_BLOCK_7 = {RUN_BLOCK_7}   (Data preview)", flush=True)
    print(f"    RUN_BLOCK_8 = {RUN_BLOCK_8}   (Evil/sus summary)", flush=True)

    # BLOCK 1 — always needed for a driver object
    if RUN_BLOCK_1:
        driver = block1_connection()
    else:
        skipped("BLOCK 1 -- Connection")
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        except Exception as e:
            print(f"[ERROR] Cannot create driver even with Block 1 off: {e}", flush=True)
            sys.exit(1)

    records = None

    if RUN_BLOCK_2:
        _, records = block2_inspect_json()
    else:
        skipped("BLOCK 2 -- JSON Inspection")

    if RUN_BLOCK_3:
        block3_sample_load(driver, records)
    else:
        skipped("BLOCK 3 -- Sample Load")

    if RUN_BLOCK_4:
        block4_all_files_loaded(driver)
    else:
        skipped("BLOCK 4 -- All Files Loaded Check")

    if RUN_BLOCK_5:
        block5_counts(driver)
    else:
        skipped("BLOCK 5 -- Counts")

    if RUN_BLOCK_6:
        block6_schema(driver)
    else:
        skipped("BLOCK 6 -- Schema Compatibility")

    if RUN_BLOCK_7:
        block7_preview(driver)
    else:
        skipped("BLOCK 7 -- Data Preview")

    if RUN_BLOCK_8:
        block8_evil_summary(driver)
    else:
        skipped("BLOCK 8 -- Evil/Sus Summary")

    driver.close()

    print(f"\n{'='*62}", flush=True)
    print("  Validation complete.", flush=True)
    print(f"{'='*62}\n", flush=True)


if __name__ == "__main__":
    main()