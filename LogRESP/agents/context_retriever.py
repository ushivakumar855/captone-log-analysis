# agents/context_retriever.py  —  Multi-hop Graph RAG agent
# Used by BOTH logresp_pipeline and ir_pipeline — no duplication.

from db.neo4j_pool import neo4j_session
from utils.logger import get_logger

logger = get_logger(__name__)

_QUERY = """
MATCH (p:Process {id: $pid})
OPTIONAL MATCH (parent:Process)-[:SPAWNED]->(p)
OPTIONAL MATCH (grandparent:Process)-[:SPAWNED]->(parent)
OPTIONAL MATCH (p)-[:ACCESSED]->(f:File)
OPTIONAL MATCH (p)-[:CONNECTED_TO]->(n:Network)
RETURN
    grandparent.cmdLine AS Grandparent,
    parent.cmdLine      AS Parent,
    p.cmdLine           AS TargetCmd,
    collect(DISTINCT f.path) AS TouchedFiles,
    collect(DISTINCT n.ip)   AS NetworkConnections
"""

def context_retriever_node(state: dict) -> dict:
    pid = state.get("process_id", "UNKNOWN")
    logger.info("[Retriever] Fetching multi-hop context for PID=%s", pid)

    try:
        with neo4j_session() as session:
            row = session.run(_QUERY, pid=pid).single()

        if not row:
            return {"neo4j_context": "No graph context found for this process."}

        gp    = row["Grandparent"]   or "Unknown"
        par   = row["Parent"]        or "Unknown"
        tgt   = row["TargetCmd"]     or "Unknown"
        files = row["TouchedFiles"]  or []
        nets  = row["NetworkConnections"] or []

        context = (
            "--- EXECUTION CHAIN ---\n"
            f"Grandparent : {gp}\n"
            f"  └── Parent: {par}\n"
            f"        └── Target: {tgt}\n\n"
            "--- ARTIFACTS ---\n"
            f"Files   : {', '.join(files[:5]) or 'None'}\n"
            f"Networks: {', '.join(nets[:3])  or 'None'}"
        )
    except Exception as exc:
        logger.error("[Retriever] Neo4j error: %s", exc)
        context = "Graph context unavailable (Neo4j error)."

    return {"neo4j_context": context}
