# LogRESP — Continuation Prompt for New Chat Window
# Save this file as: LOGRESP_CONTINUATION_PROMPT.md
# Paste the content between the === lines into any new Claude/ChatGPT chat window
# to continue this project exactly where you left off.

===========================================================================

You are a senior Python and cybersecurity AI engineer helping me continue
building a project called LogRESP. I have already designed and built
this system in a previous conversation. I will give you the full context
below. Read everything carefully before responding.

---

## WHAT THIS PROJECT IS

LogRESP is a multi-agent AI cybersecurity system that:
1. Analyzes Linux system logs from DARPA datasets (Trace, Theia) and BETH dataset
2. Detects APT (Advanced Persistent Threat) attacks using a Two-Tier AI pipeline:
   - Tier 1: GNN (Graph Neural Network) fast anomaly filter
   - Tier 2: Local LLM (via Ollama) deep analysis — only runs on flagged logs
3. Responds to detected threats using IR (Incident Response) agents
4. Maps attacks to MITRE ATT&CK framework
5. Uses Neo4j graph database to store Linux process provenance graphs

---

## DATASETS

- DARPA Trace dataset: 126 GB total. Using 1.31 GB training, 1.25 GB validation, 1.00 GB testing
- DARPA Theia dataset: 30 GB total. Using 1.60 GB training, 1.27 GB validation, 1.00 GB testing
- BETH dataset: 885 MB total, fully labeled (is_evil field = 0 or 1)
  BETH has 3 pre-split files: labelled_training_data.csv, labelled_validation_data.csv, labelled_testing_data.csv

---

## NEO4J SETUP

- Neo4j Desktop version 2.1.3 installed locally on Windows
- Instance name: log | Password: capstone123
- Connection URI: bolt://localhost:7687 / bolt://10.30.203.135:7687 (team access via WiFi)
- Graph schema:
  Nodes:  (:Process {id, cmdLine, timestamp}), (:File {path}), (:Network {ip, port})
  Edges:  [:SPAWNED] (process → process), [:ACCESSED] (process → file),
          [:CONNECTED_TO] (process → network)

---

## COMPLETE DIRECTORY STRUCTURE (ALREADY BUILT)

LogRESP/
├── config.py                     # all paths, URIs, thresholds, model names
├── run_unified_pipeline.py       # main SOC entry point
├── evaluate_model.py             # evaluate default model on BETH test set
├── requirements.txt
├── .env
├── db/
│   └── neo4j_pool.py             # shared connection pool + context manager
├── agents/
│   ├── state.py                  # LogRESPState TypedDict — defined once
│   ├── context_retriever.py      # multi-hop Graph RAG from Neo4j
│   ├── ttp_analyzer.py           # MITRE ATT&CK classifier via Ollama LLM
│   └── ir_agents.py              # strategist + command generator + auditor
├── gnn/
│   ├── scorer.py                 # GraphAutoencoder + honest score_log()
│   ├── extract_pyg.py            # Neo4j → benign_graph.pt
│   └── train_gnn.py              # trains GNN → ocr_apt_model.pth
├── pipelines/
│   ├── logresp_pipeline.py       # detection: retriever → analyzer
│   ├── ir_pipeline.py            # IR: retriever→analyzer→strategy→cmds→audit
│   └── benchmark_pipeline.py     # multi-model eval → terminal + CSV
├── data/
│   ├── beth_adapter.py           # BETH CSV → unified JSONL
│   └── trace_extractor.py        # DARPA Theia .gz → unified JSONL
└── utils/
    ├── logger.py                 # structured logging
    └── metrics.py                # ConfusionMatrix, precision, recall, F1

---

## 10 AGENTS DESIGN (from architecture whiteboard)

Agent 1  — LogParser        → data/beth_adapter.py + trace_extractor.py
Agent 2  — SequenceScorer   → gnn/scorer.py (GNN anomaly score)
Agent 3  — TTPMapper        → agents/ttp_analyzer.py (MITRE ATT&CK)
Agent 4  — RuleMatcher      → Cypher query inside context_retriever.py
Agent 5  — ContextRetriever → agents/context_retriever.py (Neo4j Graph RAG)
Agent 6  — DescriptionGen   → part of ttp_analyzer_node output
Agent 7  — ThreatLooker     → part of ir_strategist_node output
Agent 8  — Planner          → ir_agents.py → ir_strategist_node
Agent 9  — Mitigator        → ir_agents.py → command_generator_node
Agent 10 — Reflector        → ir_agents.py → safety_auditor_node

Human-in-the-loop logic:
- anomaly score > 0.95 (HIGH/CRITICAL) → wait for human approval before running commands
- anomaly score 0.85–0.95 (MEDIUM/LOW) → auto-mitigate

---

## KEY DESIGN DECISIONS ALREADY MADE

1. NO fine-tuning separate LLMs per agent. Using ONE stateless LLM (Ollama)
   with different system prompts per agent. This is the correct approach.

2. Graph RAG over Neo4j. NOT flat vector RAG. Process trees are relational
   — Neo4j Cypher multi-hop queries are the right tool.

3. GNN is trained ONE-CLASS on benign graphs only. It learns normal behavior.
   Anything that deviates scores high anomaly. No labeled attack data needed for GNN.

4. Benchmark compares these models: phi4-mini, qwen2.5-coder:7b,
   llama3.1:8b, deepseek-r1:14b. Default model: qwen2.5-coder:7b

5. ANOMALY_THRESHOLD = 0.85 (configurable in config.py)

---

## PROBLEMS FIXED IN REWRITE (DO NOT REINTRODUCE THESE)

- REMOVED: +0.90 artificial score boost for suspicious keywords in scorer.py
- FIXED: Neo4j driver now uses connection pool (neo4j_pool.py), not per-call open/close
- FIXED: AgentState TypedDict defined once in agents/state.py, not duplicated
- FIXED: All hardcoded Windows paths moved to config.py with env var override
- FIXED: Duplicate agent code (logresp_agent + benchmark_models) merged into agents/
- FIXED: All print() replaced with utils/logger.py structured logging
- FIXED: Random seed added for reproducible benchmark evaluation
- FIXED: GraphAutoencoder defined once in gnn/scorer.py, imported everywhere

---

## TECH STACK

- Python 3.11+
- Neo4j Desktop 2.1.3 (local Windows)
- PyTorch + PyTorch Geometric (GNN)
- LangGraph + LangChain (agent orchestration)
- Ollama (local LLM inference)
- fastavro + gzip (DARPA Avro file parsing)
- python-dotenv (environment config)

---

## WHAT WE HAVE NOT DONE YET (NEXT STEPS)

1. n8n automation — completely separate project, not connected to Python code.
   n8n will handle:
   - Trigger pipeline when new logs arrive
   - Send Slack/email alerts on anomaly detection
   - Schedule benchmark runs
   - Human-in-the-loop approval for mitigation commands
   We will start n8n from scratch as a standalone workflow project.

2. Ingesting DARPA logs into Neo4j — the graph schema is defined but the
   actual ingestion script that reads the JSONL output from trace_extractor.py
   and creates Neo4j nodes/edges has not been written yet.

3. The LogParser agent (Agent 1) needs to be wired into the LangGraph
   pipeline formally — right now it exists as standalone data adapter scripts.

---

## HOW TO CONTINUE

When I give you a new task, use everything above as context.
Do NOT rewrite files that are already done unless I ask you to fix something.
Always read config.py values instead of hardcoding anything.
Always use neo4j_pool.py for database access.
Always use utils/logger.py instead of print().
Always use utils/metrics.py for evaluation metrics.
Always import LogRESPState from agents/state.py.

My machine: Windows, local Neo4j, local Ollama, VS Code with GitHub Copilot.
My team: 2-5 people, connecting to Neo4j via WiFi IP 10.30.203.135:7687

===========================================================================
