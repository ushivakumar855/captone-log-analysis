# LogRESP — Complete Project Documentation
# Save this file as: LOGRESP_DOCUMENTATION.md in your GitHub repo root

---

## 1. Project Overview

LogRESP is a multi-agent AI system for detecting and responding to
cyber attacks in Linux system logs. It analyzes two DARPA datasets
(Trace + Theia) and the BETH dataset using:

- A Graph Neural Network (GNN) as a fast anomaly filter (Tier 1)
- Local LLMs via Ollama for deep threat analysis (Tier 2)
- Neo4j graph database for provenance graph storage
- LangGraph for multi-agent orchestration
- MITRE ATT&CK framework for attack classification

---

## 2. Datasets Used

| Dataset        | Total Size | Training  | Validation | Testing  |
|----------------|------------|-----------|------------|----------|
| DARPA Trace    | 126 GB     | 1.31 GB   | 1.25 GB    | 1.00 GB  |
| DARPA Theia    | 30 GB      | 1.60 GB   | 1.27 GB    | 1.00 GB  |
| BETH           | 885 MB     | labeled   | labeled    | labeled  |

BETH is the primary evaluation dataset because it has ground truth
labels (is_evil field = 0 or 1). DARPA datasets are used for
provenance graph construction and GNN training.

---

## 3. Complete Directory Structure

LogRESP/
├── config.py                        # Single source of truth — all paths, URIs, thresholds
├── run_unified_pipeline.py          # Main SOC pipeline entry point
├── evaluate_model.py                # Evaluate default model on BETH test set
├── requirements.txt                 # All Python dependencies
├── .env                             # Secrets — never commit to GitHub
│
├── db/
│   └── neo4j_pool.py                # Shared Neo4j connection pool + context manager
│
├── agents/
│   ├── state.py                     # LogRESPState TypedDict — defined once, used everywhere
│   ├── context_retriever.py         # Multi-hop Graph RAG — fetches provenance from Neo4j
│   ├── ttp_analyzer.py              # MITRE ATT&CK classifier using local LLM
│   └── ir_agents.py                 # IR Strategist + Command Generator + Safety Auditor
│
├── gnn/
│   ├── scorer.py                    # GraphAutoencoder + score_log() — honest scoring
│   ├── extract_pyg.py               # Neo4j → benign_graph.pt (run once)
│   └── train_gnn.py                 # Trains GNN → ocr_apt_model.pth (run once)
│
├── pipelines/
│   ├── logresp_pipeline.py          # Detection pipeline: retriever → analyzer
│   ├── ir_pipeline.py               # IR pipeline: retriever → analyzer → strategy → cmds → audit
│   └── benchmark_pipeline.py        # Multi-model benchmark → terminal + CSV
│
├── data/
│   ├── beth_adapter.py              # BETH CSV → unified JSONL
│   └── trace_extractor.py           # DARPA Theia .gz Avro → unified JSONL
│
└── utils/
    ├── logger.py                    # Structured logging — replaces all print() calls
    └── metrics.py                   # ConfusionMatrix, precision, recall, F1, accuracy

---

## 4. How to Run (Step by Step)

### Step 1 — Install dependencies
pip install neo4j langgraph langchain-ollama torch torch-geometric
pip install fastavro python-dotenv fastapi uvicorn httpx

### Step 2 — Start Neo4j Desktop
Open Neo4j Desktop → start your "log" instance
Connection: bolt://localhost:7687
User: neo4j | Password: capstone123

### Step 3 — Start Ollama
ollama serve
ollama pull qwen2.5-coder:7b

### Step 4 — Prepare data (run once)
python -m data.beth_adapter
python -m data.trace_extractor

### Step 5 — Build the GNN (run once)
python -m gnn.extract_pyg
python -m gnn.train_gnn

### Step 6 — Run the system
python run_unified_pipeline.py          # Full SOC pipeline
python evaluate_model.py                # Single model evaluation
python -m pipelines.benchmark_pipeline  # Compare all models → saves CSV

---

## 5. File-by-File Explanation

### config.py
PURPOSE: Single source of truth. Every path, URI, model name, and
threshold is defined here. No other file has hardcoded values.

KEY CONTENTS:
- BASE_DATA_DIR — root data folder, overridable via LOGRESP_DATA env var
- NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD — database connection config
- ANOMALY_THRESHOLD = 0.85 — GNN cutoff between normal and anomalous
- BENCHMARK_MODELS — list of Ollama models to evaluate
- OLLAMA_BASE_URL, DEFAULT_MODEL — LLM configuration

CONNECTS TO: Every single file imports from here.
DESIGN PRINCIPLE: Single Responsibility + DRY (Don't Repeat Yourself)

---

### utils/logger.py
PURPOSE: Replaces every bare print() with structured, timestamped logging.

KEY CONTENTS:
- get_logger(name) — returns a configured logger with format:
  HH:MM:SS  LEVEL     module  message

CONNECTS TO: Imported by every module.
DESIGN PRINCIPLE: Cross-cutting concern handled once.

---

### utils/metrics.py
PURPOSE: Shared evaluation math — defined once, used by both
evaluate_model.py and benchmark_pipeline.py.

KEY CONTENTS:
- ConfusionMatrix dataclass
- update(actual_evil, predicted_evil) — updates TP/TN/FP/FN counts
- Properties: precision, recall, f1, accuracy
- summary() — returns clean dict of all metrics rounded to 2 decimal places

CONNECTS TO: evaluate_model.py and benchmark_pipeline.py
DESIGN PRINCIPLE: DRY — original code had identical metric blocks in 3 files

---

### db/neo4j_pool.py
PURPOSE: One shared Neo4j driver for the entire application lifetime.

KEY CONTENTS:
- _driver — module-level singleton
- get_driver() — creates driver on first call, returns it on all subsequent calls
- neo4j_session() — context manager, guarantees session always closes
- close_driver() — called at application shutdown

CONNECTS TO: agents/context_retriever.py, gnn/extract_pyg.py
DESIGN PRINCIPLE: Connection pooling. Original code opened/closed
a new driver inside every single agent call — 240 unnecessary TCP
connections during a full benchmark run.

---

### agents/state.py
PURPOSE: Single shared data structure flowing through every LangGraph agent.

KEY CONTENTS:
class LogRESPState(TypedDict):
    raw_log:           dict    # the original log entry
    process_id:        str     # PID being analyzed
    anomaly_score:     float   # GNN score (0-1)
    neo4j_context:     str     # execution chain from graph
    ttp_analysis:      str     # LLM classification output
    ir_strategy:       str     # containment bullet points
    raw_commands:      str     # initial bash commands
    verified_commands: str     # audited safe commands
    final_analysis:    str     # final LLM output

CONNECTS TO: All agents and all pipelines.
DESIGN PRINCIPLE: Single definition. Original code had two separate
AgentState TypedDicts in logresp_agent.py and ir_copilot.py that
could silently diverge.

---

### agents/context_retriever.py
PURPOSE: Agent 5 from whiteboard (ContextRetriever). Queries Neo4j
with a multi-hop Cypher query to get the full execution chain.

KEY CONTENTS:
- context_retriever_node(state) — runs 4 optional matches in one query:
  grandparent process, parent process, touched files, network IPs
- Formats result as readable execution chain string

CYPHER QUERY does:
MATCH (p:Process {id: $pid})
OPTIONAL MATCH (grandparent)-[:SPAWNED]->(parent)-[:SPAWNED]->(p)
OPTIONAL MATCH (p)-[:ACCESSED]->(f:File)
OPTIONAL MATCH (p)-[:CONNECTED_TO]->(n:Network)

CONNECTS TO: logresp_pipeline.py, ir_pipeline.py, neo4j_pool.py
DESIGN PRINCIPLE: Single Responsibility — retrieves only, never analyzes.

---

### agents/ttp_analyzer.py
PURPOSE: Agent 3 from whiteboard (TTPMapper). Sends log + graph
context to local Ollama LLM to classify and map to MITRE ATT&CK.

KEY CONTENTS:
- _build_llm(model_name) — creates ChatOllama, accepts model override
- ttp_analyzer_node(state, model_name) — runs LLM chain
- System prompt trains the LLM to check execution chain context —
  a benign tool spawned by suspicious parent = Malicious

CONNECTS TO: logresp_pipeline.py, benchmark_pipeline.py, config.py
DESIGN PRINCIPLE: Open/Closed — swap model via model_name parameter.

---

### agents/ir_agents.py
PURPOSE: Three IR agents — Planner, Mitigator, Reflector (agents 8/9/10
from whiteboard). Form a sequential chain.

KEY CONTENTS:
- ir_strategist_node — 3 containment bullet points (Planner)
- command_generator_node — raw Bash commands targeting malicious PID (Mitigator)
- safety_auditor_node — reviews and blocks catastrophic commands (Reflector)
  Blocks: rm -rf /, database wipes, full server shutdowns

CONNECTS TO: ir_pipeline.py
DESIGN PRINCIPLE: Chain of Responsibility.

---

### gnn/scorer.py
PURPOSE: Loads trained GNN and scores any log. HONEST scoring only.

KEY CONTENTS:
- GraphAutoencoder — 2-layer GCN: input→hidden→hidden/2
- _load_model() — lazy singleton, loads weights once
- _hash_feature(text) — deterministic feature vector from process name
- score_log(log) — returns float in [0,1], high = anomalous
- is_anomalous(log, threshold) — returns (bool, score) tuple

CRITICAL FIX: Original code added +0.90 to score for certain keywords.
This was removed entirely. Score = 1.0 - sigmoid(model_output). Period.

CONNECTS TO: run_unified_pipeline.py, train_gnn.py
DESIGN PRINCIPLE: Single architecture definition. train_gnn.py imports
GraphAutoencoder from here — defined in exactly one place.

---

### gnn/extract_pyg.py
PURPOSE: One-time script. Pulls Process nodes + SPAWNED edges from
Neo4j and saves as PyTorch Geometric Data object (benign_graph.pt).

KEY CONTENTS:
- extract_graph() — queries Neo4j, builds feature matrix + edge index
- _hash_feature() — same function as scorer.py for consistency

RUN: python -m gnn.extract_pyg  (before training)
CONNECTS TO: neo4j_pool.py, train_gnn.py

---

### gnn/train_gnn.py
PURPOSE: Trains Graph Autoencoder on benign provenance graph.
One-class learning: model learns normal, flags deviations.

KEY CONTENTS:
- train() — 50 epochs, Adam lr=0.01
- Positive edges: real benign execution chains → label 1
- Negative edges: synthetic anomalous chains via negative_sampling → label 0
- Saves ocr_apt_model.pth

RUN: python -m gnn.train_gnn  (after extract_pyg)
CONNECTS TO: scorer.py (imports GraphAutoencoder), config.py

---

### pipelines/logresp_pipeline.py
PURPOSE: Compiles detection pipeline into runnable LangGraph app.

KEY CONTENTS:
- build_logresp_pipeline(model_name) — factory function
- logresp_app — default compiled instance

GRAPH: context_retriever → ttp_analyzer → END
CONNECTS TO: evaluate_model.py (uses logresp_app)
             benchmark_pipeline.py (uses build_logresp_pipeline)
DESIGN PRINCIPLE: Factory pattern — one function, multiple configurations.

---

### pipelines/ir_pipeline.py
PURPOSE: Compiles full IR pipeline. 5 agents chained sequentially.

GRAPH: retriever → analyzer → strategist → cmd_gen → auditor → END
KEY CONTENTS:
- ir_app — compiled LangGraph
- run_ir(process_id, anomaly_score) — clean 2-argument callable API

CONNECTS TO: run_unified_pipeline.py
DESIGN PRINCIPLE: Facade — hides LangGraph complexity behind simple call.

---

### pipelines/benchmark_pipeline.py
PURPOSE: Tests every model in BENCHMARK_MODELS on balanced BETH test
set. Prints table to terminal AND saves CSV.

KEY CONTENTS:
- _load_balanced() — equal samples of benign + malicious logs
- _predict_evil() — parses LLM text output to boolean
- run_benchmark() — outer loop: models. inner loop: logs.

OUTPUT: terminal comparison table + benchmark_results.csv
CONNECTS TO: build_logresp_pipeline, ConfusionMatrix, config.py
DESIGN PRINCIPLE: Strategy pattern — each model = different strategy,
same evaluation harness.

---

### data/beth_adapter.py
PURPOSE: Converts BETH CSV to unified JSONL schema.

KEY CONTENTS:
- _translate_row(row) — maps BETH columns to unified field names
  Maps processName → cmdLine for consistency with DARPA schema
  Keeps is_suspicious and is_evil ground truth labels
- convert_split(split_name) — processes one split
- run_all() — converts training, validation, testing

RUN: python -m data.beth_adapter
DESIGN PRINCIPLE: Adapter pattern.

---

### data/trace_extractor.py
PURPOSE: Extracts high-value events from DARPA Theia .gz Avro files.

KEY CONTENTS:
- HIGH_VALUE_EVENTS — only APT-relevant types (EXECUTE, FORK, CONNECT etc.)
- _extract_record() — parses CDM20 Avro nested structure
- _process_file() — worker function, one per CPU core
- process_split() — orchestrates ProcessPoolExecutor

RUN: python -m data.trace_extractor
DESIGN PRINCIPLE: Parallel worker pattern.

---

## 6. The 10-Agent Design (from whiteboard)

Agent 1  — LogParser          → data/beth_adapter.py + trace_extractor.py
Agent 2  — SequenceScorer     → gnn/scorer.py
Agent 3  — TTPMapper          → agents/ttp_analyzer.py
Agent 4  — RuleMatcher        → Cypher query in context_retriever.py
Agent 5  — ContextRetriever   → agents/context_retriever.py
Agent 6  — DescriptionGen     → part of ttp_analyzer_node output
Agent 7  — ThreatLooker       → part of ir_strategist_node output
Agent 8  — Planner            → ir_agents.py → ir_strategist_node
Agent 9  — Mitigator          → ir_agents.py → command_generator_node
Agent 10 — Reflector          → ir_agents.py → safety_auditor_node

Human-in-the-loop:
- HIGH/CRITICAL anomaly score (>0.95) → wait for human approval
- LOW anomaly score (0.85-0.95)       → auto-mitigate

---

## 7. Two-Tier Architecture

TIER 1 — GNN Fast Filter
  Every log → score_log() → anomaly score in milliseconds
  score < 0.85 → DISCARD (benign, no further processing)
  score > 0.85 → PASS TO TIER 2

TIER 2 — LLM Deep Analysis (expensive, only for flagged logs)
  Flagged log → context_retriever → neo4j multi-hop query
             → ttp_analyzer → local LLM → Benign/Malicious
             → if Malicious → ir_pipeline → commands → auditor

WHY TWO TIERS: Running an LLM on every log in a 1 GB file = hours.
GNN pre-filtering reduces LLM calls by ~95%, making the system
feasible for real-time SOC use.

---

## 8. All Problems Fixed

| Problem                        | Original Code            | Fixed Code                        |
|-------------------------------|--------------------------|-----------------------------------|
| Fake +0.90 score boost         | run_unified_pipeline.py  | Removed — scorer.py honest only   |
| New Neo4j driver per call      | Every agent              | neo4j_pool.py singleton           |
| Duplicate AgentState TypedDict | logresp_agent + copilot  | agents/state.py defined once      |
| Hardcoded Windows paths        | 6 different files        | config.py + env var override      |
| Duplicate agent definitions    | logresp_agent + benchmark| agents/ folder, imported once     |
| Bare print() everywhere        | 40+ print statements     | utils/logger.py structured logs   |
| Non-reproducible benchmark     | No random seed           | EVAL_RANDOM_SEED = 42 in config   |
| GraphAutoencoder defined twice | train_gnn + pipeline     | Defined once in gnn/scorer.py     |

---

## 9. Neo4j Graph Schema

Nodes:
  (:Process {id, cmdLine, timestamp})
  (:File    {path})
  (:Network {ip, port})

Relationships:
  (:Process)-[:SPAWNED]->(:Process)       # parent-child process tree
  (:Process)-[:ACCESSED]->(:File)         # file read/write
  (:Process)-[:CONNECTED_TO]->(:Network)  # outbound network connection

Connection:
  URI:      bolt://localhost:7687
  User:     neo4j
  Password: capstone123 (set in .env, never hardcode)

---

## 10. Tech Stack

| Component       | Technology                          |
|----------------|-------------------------------------|
| Graph DB        | Neo4j Desktop 2.1.3 (local)         |
| GNN             | PyTorch + PyTorch Geometric          |
| LLM Agents      | LangGraph + LangChain Ollama         |
| Local LLMs      | Ollama (qwen2.5-coder:7b default)   |
| Data format     | JSONL (unified schema)              |
| Avro parsing    | fastavro                            |
| Config          | python-dotenv + os.getenv           |
| Logging         | Python logging module               |
| Python version  | 3.11+                               |
