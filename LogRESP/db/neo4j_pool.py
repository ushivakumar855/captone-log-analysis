# db/neo4j_pool.py  —  shared connection pool, context manager
# Every agent uses get_driver() instead of opening its own connection.

from contextlib import contextmanager
from neo4j import GraphDatabase
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from utils.logger import get_logger

logger = get_logger(__name__)

_driver = None   # module-level singleton

def get_driver():
    """Return the shared Neo4j driver, creating it on first call."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_pool_size=20,
            connection_timeout=10,
        )
        logger.info("Neo4j driver initialised at %s", NEO4J_URI)
    return _driver

@contextmanager
def neo4j_session():
    """Context manager — guarantees the session is always closed."""
    driver = get_driver()
    session = driver.session()
    try:
        yield session
    except Exception as exc:
        logger.error("Neo4j session error: %s", exc, exc_info=True)
        raise
    finally:
        session.close()

def close_driver():
    """Call at application shutdown."""
    global _driver
    if _driver:
        _driver.close()
        _driver = None
        logger.info("Neo4j driver closed.")
