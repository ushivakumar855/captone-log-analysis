# validate_context_retriever.py — Validate Neo4j data and context retriever functionality
# Run this BEFORE executing the main pipeline to verify data integrity and Neo4j connectivity

import sys
import os
from pathlib import Path
import time

# Add parent directory to path so we can import db module
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.neo4j_pool import neo4j_session
from utils.logger import get_logger

logger = get_logger(__name__)

def validate_neo4j_connection():
    """Test Neo4j connection."""
    logger.info("="*70)
    logger.info("[VALIDATION] Step 1: Testing Neo4j Connection")
    logger.info("="*70)
    
    try:
        with neo4j_session() as session:
            result = session.run("RETURN 1")
            result.single()
        logger.info("✅ Neo4j connection successful")
        return True
    except Exception as e:
        logger.error("❌ Neo4j connection failed: %s", e)
        return False


def validate_graph_structure():
    """Verify graph structure and node counts."""
    logger.info("\n" + "="*70)
    logger.info("[VALIDATION] Step 2: Checking Graph Structure")
    logger.info("="*70)
    
    node_labels = ["Host", "User", "Process", "SyscallEvent", "File", "Network"]
    
    try:
        with neo4j_session() as session:
            for label in node_labels:
                query = f"MATCH (n:{label}) RETURN count(n) AS cnt"
                result = session.run(query)
                count = result.single()["cnt"]
                status = "✅" if count > 0 else "⚠️"
                logger.info("%s  %s nodes: %d", status, label, count)
        return True
    except Exception as e:
        logger.error("❌ Graph structure validation failed: %s", e)
        return False


def validate_evil_suspicious_distribution():
    """Check distribution of evil and suspicious events."""
    logger.info("\n" + "="*70)
    logger.info("[VALIDATION] Step 3: Checking Evil/Suspicious Distribution")
    logger.info("="*70)
    
    try:
        with neo4j_session() as session:
            # Total events
            query_total = "MATCH (e:SyscallEvent) RETURN count(e) AS total"
            result = session.run(query_total)
            total = result.single()["total"]
            logger.info("Total SyscallEvent nodes: %d", total)
            
            # Evil events (evil=1)
            query_evil = "MATCH (e:SyscallEvent {evil: 1}) RETURN count(e) AS evil_count"
            result = session.run(query_evil)
            evil_count = result.single()["evil_count"]
            logger.info("  ⚠️  Evil events (evil=1): %d (%.1f%%)", evil_count, 100*evil_count/total if total > 0 else 0)
            
            # Benign events (evil=0)
            query_benign = "MATCH (e:SyscallEvent {evil: 0}) RETURN count(e) AS benign_count"
            result = session.run(query_benign)
            benign_count = result.single()["benign_count"]
            logger.info("  ✅ Benign events (evil=0): %d (%.1f%%)", benign_count, 100*benign_count/total if total > 0 else 0)
            
            # Suspicious events
            query_sus = "MATCH (e:SyscallEvent {sus: 1}) RETURN count(e) AS sus_count"
            result = session.run(query_sus)
            sus_count = result.single()["sus_count"]
            logger.info("  🔍 Suspicious events (sus=1): %d (%.1f%%)", sus_count, 100*sus_count/total if total > 0 else 0)
            
        return True
    except Exception as e:
        logger.error("❌ Evil/suspicious distribution check failed: %s", e)
        return False


def validate_sample_process_context():
    """Validate context retriever can fetch data for a sample process."""
    logger.info("\n" + "="*70)
    logger.info("[VALIDATION] Step 4: Testing Sample Process Context Retrieval")
    logger.info("="*70)
    
    try:
        with neo4j_session() as session:
            # Get a sample process with events
            query = """
            MATCH (e:SyscallEvent)<-[:EMITS]-(p:Process)
            RETURN DISTINCT p.id AS pid, p.processName AS processName, count(e) AS event_count
            LIMIT 1
            """
            result = session.run(query)
            row = result.single()
            
            if not row:
                logger.warning("⚠️  No process with events found")
                return False
            
            pid = row["pid"]
            process_name = row["processName"]
            event_count = row["event_count"]
            
            logger.info("Found sample process: PID=%s (%s) with %d events", pid, process_name, event_count)
            
            # Test the context retriever query
            retriever_query = """
            MATCH (p:Process {id: $pid})
            OPTIONAL MATCH (parent:Process)-[:SPAWNED]->(p)
            OPTIONAL MATCH (grandparent:Process)-[:SPAWNED]->(parent)
            OPTIONAL MATCH (p)-[:ACCESSED]->(f:File)
            OPTIONAL MATCH (p)-[:CONNECTED_TO]->(n:Network)
            OPTIONAL MATCH (p)-[:EMITS]->(e:SyscallEvent)
            RETURN
                grandparent.cmdLine AS Grandparent,
                parent.cmdLine AS Parent,
                p.cmdLine AS TargetCmd,
                collect(DISTINCT f.path) AS TouchedFiles,
                collect(DISTINCT n.domain) AS NetworkConnections,
                count(DISTINCT e) AS event_count,
                sum(CASE WHEN e.evil = 1 THEN 1 ELSE 0 END) AS evil_events,
                sum(CASE WHEN e.sus = 1 THEN 1 ELSE 0 END) AS suspicious_events
            """
            
            result = session.run(retriever_query, pid=pid)
            context_row = result.single()
            
            if context_row:
                logger.info("✅ Context retrieval successful:")
                logger.info("  - Target: %s", context_row["TargetCmd"])
                logger.info("  - Parent: %s", context_row["Parent"] or "Unknown")
                logger.info("  - Grandparent: %s", context_row["Grandparent"] or "Unknown")
                logger.info("  - Files accessed: %d", len(context_row["TouchedFiles"] or []))
                logger.info("  - Network connections: %d", len(context_row["NetworkConnections"] or []))
                logger.info("  - Total events: %d", context_row["event_count"] or 0)
                logger.info("  - Evil events: %d", context_row["evil_events"] or 0)
                logger.info("  - Suspicious events: %d", context_row["suspicious_events"] or 0)
                return True
            else:
                logger.warning("⚠️  Context retrieval returned no results")
                return False
        
    except Exception as e:
        logger.error("❌ Sample process context retrieval failed: %s", e)
        return False


def validate_relationships():
    """Check that all required relationships exist."""
    logger.info("\n" + "="*70)
    logger.info("[VALIDATION] Step 5: Checking Graph Relationships")
    logger.info("="*70)
    
    relationships = [
        "RUNS_ON", "RUNS_AS", "EMITS", "SPAWNED", "ACCESSED", "CONNECTED_TO"
    ]
    
    try:
        with neo4j_session() as session:
            for rel in relationships:
                query = f"MATCH ()-[:{rel}]->() RETURN count(*) AS cnt"
                result = session.run(query)
                count = result.single()["cnt"]
                status = "✅" if count > 0 else "⚠️"
                logger.info("%s  %s relationships: %d", status, rel, count)
        return True
    except Exception as e:
        logger.error("❌ Relationship validation failed: %s", e)
        return False


def main():
    logger.info("\n\n")
    logger.info("╔" + "="*68 + "╗")
    logger.info("║" + " "*15 + "CONTEXT RETRIEVER VALIDATION" + " "*25 + "║")
    logger.info("╚" + "="*68 + "╝")
    
    start_time = time.time()
    
    checks = [
        ("Neo4j Connection", validate_neo4j_connection),
        ("Graph Structure", validate_graph_structure),
        ("Evil/Suspicious Distribution", validate_evil_suspicious_distribution),
        ("Relationships", validate_relationships),
        ("Sample Process Context", validate_sample_process_context),
    ]
    
    results = {}
    for check_name, check_func in checks:
        try:
            results[check_name] = check_func()
        except Exception as e:
            logger.error("❌ Unexpected error in %s: %s", check_name, e)
            results[check_name] = False
    
    # Summary
    elapsed = time.time() - start_time
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    logger.info("\n" + "="*70)
    logger.info("[SUMMARY] Validation Results")
    logger.info("="*70)
    for check_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info("%s  %s", status, check_name)
    
    logger.info("="*70)
    logger.info("Total: %d/%d checks passed (%.2fs)", passed, total, elapsed)
    logger.info("="*70)
    
    if passed == total:
        logger.info("\n🎉 ALL VALIDATION CHECKS PASSED! Ready to run the pipeline.")
    else:
        logger.warning("\n⚠️  SOME VALIDATION CHECKS FAILED. Fix issues before running the pipeline.")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
