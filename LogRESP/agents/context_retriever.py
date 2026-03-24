# agents/context_retriever.py  —  Multi-hop Graph RAG agent
# Used by BOTH logresp_pipeline and ir_pipeline — no duplication.

import time
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
        query_start = time.time()
        logger.debug("[Retriever] Executing multi-hop Cypher query...")
        
        with neo4j_session() as session:
            result = session.run(_QUERY, pid=pid)
            row = result.single()
        
        query_time = time.time() - query_start
        logger.debug("[Retriever] Query completed in %.3fs", query_time)

        if not row:
            logger.info("[Retriever] No graph context found for PID=%s", pid)
            return {"neo4j_context": "No graph context found for this process."}

        # Extract and log field population
        gp    = row["Grandparent"]   or None
        par   = row["Parent"]        or None
        tgt   = row["TargetCmd"]     or None
        files = row["TouchedFiles"]  or []
        nets  = row["NetworkConnections"] or []
        
        logger.debug("[Retriever] Field extraction: gp=%s, parent=%s, target=%s, files=%d, nets=%d",
                     "YES" if gp else "NO", "YES" if par else "NO", "YES" if tgt else "NO",
                     len(files), len(nets))
        
        # Build execution chain with actual values or Unknown
        gp_display  = gp if gp else "Unknown"
        par_display = par if par else "Unknown"
        tgt_display = tgt if tgt else "Unknown"
        
        context = (
            "--- EXECUTION CHAIN ---\n"
            f"Grandparent : {gp_display}\n"
            f"  └── Parent: {par_display}\n"
            f"        └── Target: {tgt_display}\n\n"
            "--- ARTIFACTS ---\n"
            f"Files   : {', '.join(files[:5]) or 'None'}\n"
            f"Networks: {', '.join(nets[:3])  or 'None'}"
        )
        
        logger.info("[Retriever] Context assembled (chain_depth=%d, files=%d, networks=%d)",
                    sum([1 for x in [gp, par, tgt] if x]), len(files), len(nets))
        logger.debug("[Retriever] Context preview: %s", context[:150])
        
        return {"neo4j_context": context}
        
    except Exception as exc:
        logger.error("[Retriever] Neo4j query failed for PID=%s: %s", pid, exc, exc_info=True)
        context = "Graph context unavailable (Neo4j error)."
        return {"neo4j_context": context}
