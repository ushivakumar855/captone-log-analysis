# BETH Dataset → Neo4j Graph Loader
### LogRESP Capstone Project — Database Setup Guide

This guide documents how to load the pre-processed **BETH cybersecurity dataset** into a local **Neo4j graph database**, which is then queried by `context_retriever.py` inside the LogRESP pipeline.

---

## 📁 Files in This Module

| File | Purpose |
|------|---------|
| `test_connection.py` | Quick Neo4j connection test — run this first |
| `load_beth_to_neo4j.py` | Full data loader — loads all `part_*.json` files into Neo4j |
| `validate_neo4j_load.py` | Validation script — tests the load using only `part_1.json` |

---

## 🧰 Prerequisites

### 1. Software Required
- **Python 3.8+**
- **Neo4j Desktop** — [Download here](https://neo4j.com/download/)
- **Neo4j Python Driver**

```bash
pip install neo4j
```

### 2. Dataset Required
The pre-processed BETH JSON files output by `beth_preprocess.py`:
```
dataset/
└── preprocessed/
    └── train/
        ├── part_1.json
        ├── part_2.json
        └── ...
```

---

## ⚙️ Neo4j Desktop Setup (One-Time)

1. Open **Neo4j Desktop**
2. Create a new **Local DBMS** (or use an existing one)
3. Set a password — the default used in these scripts is `test1-beth123`
4. Click **▶ Start** and wait for the status dot to turn **green**
5. Keep Neo4j Desktop open while running any script

> **Important:** The Neo4j username is always `neo4j` — do **not** use the instance name (e.g. `test1-beth-data`) as the username. That is just a display label.

---

## 🚀 Step-by-Step Usage

### Step 1 — Test the Connection

Run this first to confirm Neo4j is reachable from Python:

```bash
python test_connection.py
```

**Expected output:**
```
✅ Connected to Neo4j successfully!
```

If you see a connection error, make sure your Neo4j DBMS is started (green dot in Neo4j Desktop) and your credentials match.

---

### Step 2 — Validate with a Single File

Before loading all your data, run the validation script. It uses only `part_1.json` and a sample of 50 records to do a full end-to-end check:

```bash
python validate_neo4j_load.py
```

This script will:
- ✅ Verify the Neo4j connection
- ✅ Locate and parse `part_1.json`
- ✅ Clear the database and load 50 sample records
- ✅ Confirm all node labels exist (`Host`, `User`, `Process`, `SyscallEvent`, `File`, `Network`)
- ✅ Confirm all relationship types exist (`RUNS_ON`, `RUNS_AS`, `SPAWNED`, `EMITS`, `ACCESSED`, `CONNECTED_TO`)
- ✅ Verify schema compatibility with `context_retriever.py`
- ✅ Show a live data preview from Neo4j

**Expected final output:**
```
  ✅  ALL CHECKS PASSED
  You are ready to run the full load:
      python load_beth_to_neo4j.py
```

> ⚠️ This script **clears** your Neo4j database before loading. Use it only on a dev/test instance.

---

### Step 3 — Full Data Load

Once validation passes, load all chunk files:

```bash
python load_beth_to_neo4j.py
```

You will see progress output like:
```
[Step 1/6] Connecting to Neo4j...
[Step 2/6] Clearing existing database...
[Step 3/6] Setting up schema...
[Step 4/6] Loading 5 chunk file(s) into Neo4j...
[File 1/5] Processing part_1.json...  12450 records -> 87234 graph elements (14.2s)
...
[Step 5/6] Load summary:
  Files loaded:  5
  Total records: 62,250
  Total time:    73.1s
[Step 6/6] Graph statistics:
  Host nodes ........................       2
  Process nodes .....................    8,543
  ...
```

---

## 🗂️ Graph Schema

The loader creates the following graph structure in Neo4j:

### Node Labels

| Label | Key Properties | Description |
|-------|---------------|-------------|
| `Host` | `hostName` | Machine the events were recorded on |
| `User` | `userId`, `is_root`, `is_real_user` | OS user running the process |
| `Process` | `processId`, `hostName`, `id`, `cmdLine`, `processName` | OS process |
| `SyscallEvent` | `eventName`, `timestamp`, `sus`, `evil`, `event_category` | Individual syscall |
| `File` | `path`, `path_prefix`, `has_sensitive_path`, `flags_category` | File touched by a process |
| `Network` | `domain`, `type` | Socket/network endpoint |

> `Process.id` = `str(processId)` and `Process.cmdLine` = `processName` — these are set for compatibility with `context_retriever.py`.

### Relationships

| Relationship | Direction | Meaning |
|-------------|-----------|---------|
| `RUNS_ON` | `(Process)→(Host)` | Process ran on this host |
| `RUNS_AS` | `(Process)→(User)` | Process ran under this user |
| `EMITS` | `(Process)→(SyscallEvent)` | Process made this syscall |
| `SPAWNED` | `(Process)→(Process)` | Parent process spawned child |
| `ACCESSED` | `(Process)→(File)` | Process accessed this file path |
| `CONNECTED_TO` | `(Process)→(Network)` | Process opened this socket |

---

## 🔧 Configuration

All scripts share the same configuration block at the top. You can override with environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt connection URI |
| `NEO4J_USER` | `neo4j` | Neo4j username (always `neo4j` for Desktop) |
| `NEO4J_PASS` | `test1-beth123` | Neo4j password you set in Desktop |
| `BETH_JSON_DIR` | *(hardcoded path)* | Path to `preprocessed/train/` folder |

### Setting the JSON folder path (Windows)

**Option A — Edit the script directly:**
```python
BETH_JSON_DIR = Path(r"C:\Users\YourName\path\to\dataset\preprocessed\train")
```

**Option B — Use an environment variable (CMD):**
```cmd
set BETH_JSON_DIR=C:\Users\YourName\path\to\dataset\preprocessed\train
python load_beth_to_neo4j.py
```

**Option B — Use an environment variable (PowerShell):**
```powershell
$env:BETH_JSON_DIR = "C:\Users\YourName\path\to\dataset\preprocessed\train"
python load_beth_to_neo4j.py
```

---

## 🐛 Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `ServiceUnavailable: Failed to establish connection` | Neo4j DBMS not running | Open Neo4j Desktop → click ▶ Start |
| `AuthError: {code: Neo.ClientError.Security.Unauthorized}` | Wrong username or password | Username must be `neo4j`, not the instance name |
| `[ERROR] JSON folder not found` | `BETH_JSON_DIR` path is wrong | Update the path in the script or set the env variable |
| `No part_*.json files found` | Wrong folder — missing `train/` subfolder | Make sure you point to `preprocessed/train/`, not `preprocessed/` |
| Script appears to freeze / no output | Buffered output or waiting for `input()` | `AUTO_CONFIRM = True` is already set — check for Python buffering issues |
| `Java heap space` error in Neo4j logs | Batch size too large | Lower `BATCH_SIZE` from 500 to 200 in the script |

---

## 🔍 Verifying the Load in Neo4j Browser

After loading, open **Neo4j Browser** (click **Open** in Neo4j Desktop) and run:

```cypher
-- Count all nodes
MATCH (n) RETURN labels(n), count(n) ORDER BY count(n) DESC

-- See a sample process and its events
MATCH (p:Process)-[:EMITS]->(e:SyscallEvent)
RETURN p.processName, e.eventName, e.evil LIMIT 20

-- Find evil events
MATCH (p:Process)-[:EMITS]->(e:SyscallEvent {evil: 1})
RETURN p.processName, e.eventName, e.timestamp LIMIT 10

-- Trace process lineage
MATCH path = (par:Process)-[:SPAWNED*1..3]->(child:Process)
RETURN path LIMIT 20
```

---

## 📌 Notes for Teammates

- **Do not change node labels or property names** — `context_retriever.py` relies on the exact names `Process`, `File`, `Network`, `id`, `cmdLine`, `path`, `ip`, `port` as described above.
- **The database is fully reproducible** — you can re-run `load_beth_to_neo4j.py` at any time to wipe and reload cleanly.
- **Part files are independent** — if a load is interrupted, just re-run the full loader. It clears first, so there is no risk of duplicated data (except for `SyscallEvent` nodes which use `CREATE` not `MERGE` — this is intentional, since two events at the same timestamp with the same name are distinct events).
- **`validate_neo4j_load.py` is safe to run repeatedly** — it always clears and reloads from just the first 50 records, leaving the database in a minimal state. Run `load_beth_to_neo4j.py` after to restore the full dataset.

---

## 👤 Author

Auto-generated for the **LogRESP Capstone Project**.  
BETH dataset: *Bridge from Exploration to Testing Hypotheses* — a labelled host-based intrusion detection dataset.
