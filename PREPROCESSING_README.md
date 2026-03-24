# BETH Dataset Pre-processing Pipeline

> Transforms raw BETH syscall CSV data into Neo4j-ready JSON with feature engineering, column pruning, and graph-structured output.

---

## Table of Contents

- [Overview](#overview)
- [About the BETH Dataset](#about-the-beth-dataset)
- [Why Pre-processing is Needed](#why-pre-processing-is-needed)
- [Data Exploration Findings](#data-exploration-findings)
  - [Dataset Structure](#dataset-structure)
  - [Label Distribution](#label-distribution)
  - [The Attack Pattern (evil = 1)](#the-attack-pattern-evil--1)
  - [Suspicious vs Evil — The Key Difference](#suspicious-vs-evil--the-key-difference)
- [Column Decisions](#column-decisions)
  - [Columns Dropped (5)](#columns-dropped-5)
  - [Columns Kept (9)](#columns-kept-9)
  - [Fields Extracted from args (5)](#fields-extracted-from-args-5)
  - [Derived Features Engineered (10)](#derived-features-engineered-10)
- [Pre-processing Pipeline Steps](#pre-processing-pipeline-steps)
- [Output JSON Structure](#output-json-structure)
  - [Neo4j Graph Schema](#neo4j-graph-schema)
  - [Sample Output Record](#sample-output-record)
- [Directory Structure](#directory-structure)
- [How to Run](#how-to-run)
- [Dependencies](#dependencies)
- [Validation Results](#validation-results)

---

## Overview

This pre-processing script is **Stage 2** of our capstone pipeline:

```
Raw BETH CSV → [Pre-processing] → Neo4j-ready JSON → [Neo4j Ingest] → Graph Database → [Agent Queries]
                  ▲ YOU ARE HERE
```

The script reads chunked CSV/Excel files from three splits (train, val, test), applies column pruning, feature extraction, and feature engineering, then outputs structured JSON files where each record maps directly to Neo4j graph nodes and edges.

---

## About the BETH Dataset

The **BETH (Benchmarking, Evaluation, and Testing for Host-based intrusion detection)** dataset is a collection of **Linux kernel syscall traces** captured from cloud machines using **Tracee**, an eBPF-based tracing tool.

| Split | Full Size | Chunk Size | Source |
|-------|-----------|------------|--------|
| Training data | 763,145 rows | ~500 rows per chunk | [Kaggle - BETH Dataset](https://www.kaggle.com/datasets/katehighnam/beth-dataset) |
| Validation data | 188,968 rows | ~500 rows per chunk | Same |
| Test data | 188,968 rows | ~500 rows per chunk | Same |

Each row represents **one syscall event** — a single process doing one thing at the OS level (opening a file, creating a socket, exiting, etc.). The dataset has **16 columns** (14 features + 2 labels).

**Original 16 columns:**

```
timestamp, processId, threadId, parentProcessId, userId, mountNamespace,
processName, hostName, eventId, eventName, stackAddresses, argsNum,
returnValue, args, sus, evil
```

---

## Why Pre-processing is Needed

The raw CSV cannot be loaded into Neo4j directly for three reasons:

1. **Redundant columns** — 5 of the 16 columns add zero information (e.g., `threadId` equals `processId` 99.4% of the time, `eventId` is a 1-to-1 numeric alias of `eventName`).
2. **The `args` column is a raw string** — It contains a Python list-of-dicts string like `[{'name': 'pathname', 'type': 'const char*', 'value': '/tmp/ssh-xyz/agent.1407'}]`. The critical fields (`pathname`, `flags`, `socket domain`) are buried inside and must be parsed out.
3. **No derived features** — Security-relevant signals like "is this a delete operation?", "is this a root user?", "does this touch a sensitive path?" need to be computed and added as properties for effective graph queries.

---

## Data Exploration Findings

### Dataset Structure

We performed a comprehensive exploration on Part 1 samples (5,000 rows each from train, val, test = 15,000 rows total). Key findings:

- **Zero nulls** across all 16 columns — the data is clean
- **33 unique syscall types** (eventName), dominated by `close` (26.3%), `openat` (25.6%), `security_file_open` (15.1%)
- **22 unique process names**, dominated by `ps` (32.6%), `systemd-udevd` (29.3%), `systemd` (13.9%)
- **6 unique userIds**: 0 (root, 96.3%), 100-109 (service accounts), 1000 (real user, 1.9%)
- **10 unique hostnames** — all AWS EC2 instances (`ip-10-100-1-*`) plus one `ubuntu`

### Label Distribution

```
           Train (Part 1)    Val (Part 1)     Test (Part 1)
sus = 0    4,727 (94.5%)     4,985 (99.7%)    4,033 (80.7%)
sus = 1      273 (5.5%)         15 (0.3%)      967 (19.3%)
evil = 0   5,000 (100%)      5,000 (100%)     4,984 (99.7%)
evil = 1       0 (0%)            0 (0%)          16 (0.3%)
```

**Critical finding:** All 16 evil=1 rows are also sus=1. Evil implies sus, but sus does NOT imply evil.

### The Attack Pattern (evil = 1)

All 16 evil rows exist only in the test set and represent an **SSH session hijack / credential theft** attack:

- **Host:** `ip-10-100-1-217` (single host)
- **Process:** `sshd` (SSH daemon) + one `sd-pam` process
- **User:** `userId = 1000` (a real user account, not root)
- **returnValue:** All 0 (success — the attack worked)

The attack sequence per process follows this exact pattern:

```
close(fd=10)
  → security_inode_unlink(/tmp/ssh-XXXXXXXX/agent.<PID>)
  → unlink(/tmp/ssh-XXXXXXXX/agent.<PID>)
  → close(fd=4)
  → sched_process_exit
```

**What this means:** The attacker's sshd processes, running as a real user (uid=1000), delete SSH agent socket files from `/tmp/ssh-*/agent.*` and then exit. This is consistent with **SSH credential theft** — the attacker used the SSH agent socket to impersonate the user, then cleaned up the socket files to cover tracks.

The 4 syscall types used in the attack:
| Syscall | Count | Role |
|---------|-------|------|
| `close` | 6 | Close file descriptors before cleanup |
| `security_inode_unlink` | 3 | Security hook triggered before file deletion |
| `unlink` | 3 | Actual file deletion of agent socket |
| `sched_process_exit` | 4 | Process termination after cleanup |

### Suspicious vs Evil — The Key Difference

| | sus = 1 | evil = 1 |
|---|---|---|
| **What it means** | Heuristic flag: "this looks unusual" | Ground truth: confirmed malicious |
| **How it's set** | Automated rules (like an IDS alert) | Human annotation of known attacks |
| **Volume** | 1,255 rows (8.4%) in Part 1 samples | 16 rows (0.1%) — only in test |
| **Noise level** | High — many are benign (e.g., `ps` monitoring) | None — every evil row is a real attack |
| **Key processes** | `sshd` (58%), `systemd` (20%), `sh` (9%), `run-parts` (9%) | `sshd` (15 rows), `sd-pam` (1 row) |

The `ps` process generates 32.6% of all rows but has a **0% sus rate** — it's a monitoring tool producing legitimate noise. Meanwhile, `sh` and `run-parts` are flagged sus 100% of the time purely because heuristic rules blanket-flag shell and cron activity.

---

## Column Decisions

### Columns Dropped (5)

| Column | Reason for Dropping | Evidence |
|--------|-------------------|----------|
| `threadId` | Nearly identical to `processId` | Equal in 99.4% of rows; 87 vs 76 unique values |
| `eventId` | Perfect 1-to-1 mapping to `eventName` | Verified: every eventId maps to exactly one eventName — fully redundant numeric alias |
| `argsNum` | Derivable from `args` column | `argsNum == len(args)` in 100% of rows |
| `stackAddresses` | Raw memory pointers, mostly empty | 57.1% empty (`[]`), 2,163 unique values, no interpretable pattern for graph analysis |
| `mountNamespace` | Near-constant, only 4-5 values | 67.6% share value `4026531840`, 29.3% share `4026532217` — 97% concentrated in two values |

### Columns Kept (9)

| Column | Role in Neo4j | Key Stats |
|--------|--------------|-----------|
| `timestamp` | SyscallEvent property; temporal ordering | Unique per row, range 124–3614 seconds |
| `processId` | Process node identity | 76 unique values |
| `parentProcessId` | CHILD_OF edge to parent Process | 30 unique values; enables process tree |
| `processName` | Process node label | 22 unique values |
| `eventName` | SyscallEvent type | 33 unique syscall types |
| `userId` | User node identity | 6 values (0=root, 100-109=service, 1000=real user) |
| `hostName` | Host node identity | 10 unique hosts |
| `returnValue` | SyscallEvent property | 0=success (69%), -2=ENOENT (5.3%), negatives=failures |
| `sus` / `evil` | Labels on SyscallEvent node | Binary (0/1) |

### Fields Extracted from args (5)

The `args` column is a Python list-of-dicts string that requires parsing. We extract:

| Extracted Field | Source in args | Present in | Example Value |
|----------------|---------------|------------|---------------|
| `pathname` | `args[name='pathname'].value` | ~51.6% of rows | `/tmp/ssh-ITim7SZsmg/agent.1407` |
| `flags_raw` | `args[name='flags'].value` | ~41.3% of rows | `O_RDONLY\|O_CLOEXEC` |
| `socket_domain` | `args[name='domain'].value` | Network events only | `AF_UNIX`, `AF_INET` |
| `socket_type` | `args[name='type'].value` | Network events only | `SOCK_STREAM`, `SOCK_DGRAM` |
| `fd` | `args[name='fd'].value` | ~50% of rows | `4`, `10`, `15` |

**Parsing method:** `ast.literal_eval()` converts the string representation into an actual Python list, then we iterate over the dicts looking for specific `name` keys.

### Derived Features Engineered (10)

| Feature | Logic | Purpose |
|---------|-------|---------|
| `path_prefix` | First directory from pathname (e.g., `/tmp`, `/etc`, `/proc`) | FilePath node grouping; enables "show all /tmp access" queries |
| `has_sensitive_path` | `True` if pathname contains `/etc/passwd`, `/etc/shadow`, `/etc/ssh/`, or `/tmp/ssh-` | Boolean flag for high-risk file access detection |
| `flags_category` | Classifies raw flags into `read` / `write` / `readwrite` / `other` | Simplifies write-access detection in queries |
| `is_delete_op` | `True` if eventName is `unlink`, `unlinkat`, or `security_inode_unlink` | Key attack indicator (the evil rows use delete ops) |
| `is_exec_op` | `True` if eventName is `execve` or `security_bprm_check` | Flags process execution events |
| `is_network_op` | `True` if eventName is `socket`, `connect`, `bind`, `accept`, `accept4`, or `getsockname` | Flags network activity |
| `is_root` | `True` if `userId == 0` | Privilege context for User node |
| `is_real_user` | `True` if `userId >= 1000` | Distinguishes real human users from system/service accounts |
| `is_failed_syscall` | `True` if `returnValue < 0` | Negative return = error (e.g., -2 = ENOENT, file not found) |
| `event_category` | Maps eventName → `file_op` / `process` / `network` / `security` / `other` | High-level grouping of 33 syscall types into 4 categories |

**Event category mapping:**

```
file_op:   close, openat, fstat, stat, lstat, access, getdents64,
           unlink, unlinkat, fchmod, dup, dup2, dup3, umount
process:   clone, execve, kill, sched_process_exit, prctl,
           setuid, setgid, setreuid, setregid
network:   socket, connect, bind, accept, accept4, getsockname
security:  security_file_open, security_inode_unlink,
           security_bprm_check, cap_capable
```

---

## Pre-processing Pipeline Steps

The script processes each chunk file through these 5 sequential stages:

```
┌─────────────────────────────────────────────────────────┐
│  Stage 1: DROP redundant columns                        │
│  Remove threadId, eventId, argsNum, stackAddresses,     │
│  mountNamespace (5 columns → 11 remaining)              │
├─────────────────────────────────────────────────────────┤
│  Stage 2: PARSE the args column                         │
│  ast.literal_eval() converts string → Python list       │
│  Handles empty args ([]) and malformed strings safely    │
├─────────────────────────────────────────────────────────┤
│  Stage 3: EXTRACT fields from parsed args               │
│  Pull out: pathname, flags, socket_domain, socket_type, │
│  fd from the list-of-dicts                              │
├─────────────────────────────────────────────────────────┤
│  Stage 4: ENGINEER derived features                     │
│  Compute: path_prefix, has_sensitive_path, is_delete_op,│
│  is_exec_op, is_network_op, is_root, is_real_user,      │
│  is_failed_syscall, event_category, flags_category       │
├─────────────────────────────────────────────────────────┤
│  Stage 5: BUILD Neo4j-structured JSON                   │
│  Each row → one JSON record with separate node objects  │
│  (event, process, host, user, file_path, socket)        │
│  and an edges map defining relationship types            │
└─────────────────────────────────────────────────────────┘
```

---

## Output JSON Structure

### Neo4j Graph Schema

Each JSON record maps to this graph model:

```
(:Host {hostName})
  ─[:RUNS_ON]→ (:Process {processId, processName, parentProcessId})
                  ─[:CHILD_OF]→ (:Process)          ← parent process
                  ─[:RUNS_AS]→ (:User {userId, is_root, is_real_user})
                  ─[:EMITS]→ (:SyscallEvent {eventName, timestamp, returnValue,
                  │              sus, evil, event_category, is_delete_op,
                  │              is_exec_op, is_network_op, is_failed_syscall})
                  │
                  ├──[:ACCESSES]→ (:FilePath {pathname, path_prefix,
                  │                 has_sensitive_path, flags_raw, flags_category})
                  │
                  └──[:OPENS]→ (:SocketCall {domain, type})
```

**Nodes (6 types):** Host, Process, User, SyscallEvent, FilePath, SocketCall

**Edges (6 types):** RUNS_ON, CHILD_OF, RUNS_AS, EMITS, ACCESSES, OPENS

> FilePath and SocketCall nodes are **conditional** — they only appear when the syscall has a pathname or socket domain in its args. Not every event touches a file or opens a socket.

### Sample Output Record

A typical record for a file operation:

```json
{
  "event": {
    "eventName": "security_inode_unlink",
    "timestamp": 132.486591,
    "returnValue": 0,
    "sus": 1,
    "evil": 1,
    "event_category": "security",
    "is_delete_op": false,
    "is_exec_op": false,
    "is_network_op": false,
    "is_failed_syscall": false
  },
  "process": {
    "processId": 1323,
    "parentProcessId": 1246,
    "processName": "sshd"
  },
  "host": {
    "hostName": "ip-10-100-1-217"
  },
  "user": {
    "userId": 1000,
    "is_root": false,
    "is_real_user": true
  },
  "edges": {
    "process_host": "RUNS_ON",
    "process_parent": "CHILD_OF",
    "process_user": "RUNS_AS",
    "process_event": "EMITS",
    "event_file": "ACCESSES"
  },
  "file_path": {
    "pathname": "/tmp/ssh-5SWwFPe55l/agent.1323",
    "path_prefix": "/tmp",
    "has_sensitive_path": true,
    "flags_raw": null,
    "flags_category": null
  }
}
```

This record represents one of the **evil=1 attack events**: process `sshd` (pid=1323) running as a real user (uid=1000) on host `ip-10-100-1-217` is deleting the SSH agent socket file `/tmp/ssh-5SWwFPe55l/agent.1323`.

---

## Directory Structure

### Input (your chunked dataset)

```
C:\Users\shiva\OneDrive\Desktop\capstone\dataset\
├── train_chunks/
│   ├── part_1.csv (or .xlsx)
│   ├── part_2.csv
│   ├── part_3.csv
│   └── ... (each ~500 rows)
├── val_chunks/
│   ├── part_1.csv
│   ├── part_2.csv
│   └── ...
└── test_chunks/
    ├── part_1.csv
    ├── part_2.csv
    └── ...
```

### Output (generated by the script)

```
C:\Users\shiva\OneDrive\Desktop\capstone\dataset\preprocessed\
├── train/
│   ├── part_1.json
│   ├── part_2.json
│   └── ...
├── val/
│   ├── part_1.json
│   ├── part_2.json
│   └── ...
└── test/
    ├── part_1.json
    ├── part_2.json
    └── ...
```

Each output JSON file is an array of records, one per syscall event, matching the chunk structure of the input.

---

## How to Run

### 1. Install dependencies

```bash
pip install pandas openpyxl
```

### 2. Verify your directory structure

Make sure your chunked data is at:
```
C:\Users\shiva\OneDrive\Desktop\capstone\dataset\
  ├── train_chunks/
  ├── val_chunks/
  └── test_chunks/
```

If your dataset is at a different path, edit the `BASE_DIR` variable at line 35 of `beth_preprocess.py`.

### 3. Run the script

```bash
python beth_preprocess.py
```

### 4. Check the output

The script prints progress for each chunk file and a summary at the end:

```
======================================================================
BETH Dataset Pre-processor → Neo4j JSON
======================================================================

Base directory: C:\Users\shiva\OneDrive\Desktop\capstone\dataset
Output directory: C:\Users\shiva\OneDrive\Desktop\capstone\dataset\preprocessed

──────────────────────────────────────────────────
Split: TRAIN
  Input:  C:\Users\shiva\...\train_chunks
  Output: C:\Users\shiva\...\preprocessed\train
──────────────────────────────────────────────────
  Processing part_1.csv... 500 rows → part_1.json (1.2s)
  Processing part_2.csv... 500 rows → part_2.json (1.1s)
  ...

======================================================================
PRE-PROCESSING COMPLETE
======================================================================
  Total files processed: 30
  Total rows processed:  15000
  Output location:       ...\preprocessed
```

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| Python | >= 3.8 | Runtime |
| pandas | >= 1.3.0 | CSV/Excel reading and DataFrame operations |
| openpyxl | >= 3.0.0 | Required by pandas for reading .xlsx files |

All other imports (`os`, `sys`, `ast`, `json`, `time`, `pathlib`) are Python standard library.

---

## Validation Results

Tested on Part 1 samples (5,000 rows each):

| Check | Result |
|-------|--------|
| Train rows processed | 5,000 / 5,000 |
| Test rows processed | 5,000 / 5,000 |
| Val rows processed | 5,000 / 5,000 |
| Evil rows captured (test) | 16 / 16 |
| Sus rows captured (all) | 1,255 / 1,255 |
| Records with FilePath node | 2,874 / 5,000 (train) |
| Records with SocketCall node | 7 / 5,000 (train) |
| Event category distribution | file_op: 3,503, security: 1,369, process: 117, network: 11 |
| All evil rows show SSH credential theft pattern | Confirmed |
| No data loss or corruption | Confirmed |

---

## Next Step

The output JSON files from this script feed directly into the **Neo4j ingest stage**, where each record creates graph nodes and edges using Cypher queries.
