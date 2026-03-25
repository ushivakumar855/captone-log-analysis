# db/neo4j_pool.py  —  shared connection pool, context manager
# Every agent uses get_driver() instead of opening its own connection.

# this is very old code


import time
from contextlib import contextmanager
from neo4j import GraphDatabase
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from utils.logger import get_logger

logger = get_logger(__name__)

_driver = None   # module-level singleton
_session_count = 0  # Track active sessions

def get_driver():
    """Return the shared Neo4j driver, creating it on first call."""
    global _driver
    if _driver is None:
        logger.info("[Neo4j] Initializing driver for %s (first-time setup)", NEO4J_URI)
        logger.debug("[Neo4j] Connection pool max size: 20 | Timeout: 10s")
        try:
            init_start = time.time()
            _driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD),
                max_connection_pool_size=20,
                connection_timeout=10,
            )
            init_time = time.time() - init_start
            logger.info("[Neo4j] Driver initialized successfully in %.3fs", init_time)
        except Exception as e:
            logger.error("[Neo4j] Driver initialization failed: %s", e, exc_info=True)
            raise
    else:
        logger.debug("[Neo4j] Using cached driver instance")
    return _driver

@contextmanager
def neo4j_session():
    """Context manager — guarantees the session is always closed."""
    global _session_count
    driver = get_driver()
    
    logger.debug("[Neo4j Pool] Creating session (active=%d)", _session_count)
    session_start = time.time()
    session = driver.session()
    _session_count += 1
    
    try:
        logger.debug("[Neo4j Pool] Session created (total_active=%d)", _session_count)
        yield session
        
    except Exception as exc:
        session_time = time.time() - session_start
        logger.error("[Neo4j Pool] Session error after %.2fs: %s", session_time, exc, exc_info=True)
        raise
        
    finally:
        _session_count -= 1
        session_time = time.time() - session_start
        logger.debug("[Neo4j Pool] Session closed (duration=%.3fs, remaining=%d)", session_time, _session_count)

def close_driver():
    """Call at application shutdown."""
    global _driver, _session_count
    if _driver:
        logger.info("[Neo4j] Closing driver (active sessions at close: %d)", _session_count)
        if _session_count > 0:
            logger.warning("[Neo4j] Warning: %d sessions still active at close time", _session_count)
        try:
            _driver.close()
            _driver = None
            logger.info("[Neo4j] Driver closed successfully")
        except Exception as e:
            logger.error("[Neo4j] Error closing driver: %s", e, exc_info=True)
            _driver = None
