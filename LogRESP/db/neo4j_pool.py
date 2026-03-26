# db/neo4j_pool.py  —  Neo4j Connection Pool Manager
# Manages a single driver instance and provides session context managers.

from contextlib import contextmanager
from neo4j import GraphDatabase
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from utils.logger import get_logger

logger = get_logger(__name__)

# Global driver instance (singleton pattern)
_driver = None


def _get_driver():
    """Lazily initialize and return the Neo4j driver."""
    global _driver
    if _driver is None:
        logger.info("[Neo4j] Initializing driver for %s", NEO4J_URI)
        try:
            _driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD),
                encrypted=False
            )
            logger.info("[Neo4j] Driver initialized successfully")
        except Exception as e:
            logger.error("[Neo4j] Failed to initialize driver: %s", e, exc_info=True)
            raise
    return _driver


@contextmanager
def neo4j_session():
    """
    Context manager that provides a Neo4j session.
    Automatically closes the session when exiting the context.
    
    Usage:
        with neo4j_session() as session:
            result = session.run("MATCH (n) RETURN n LIMIT 1")
    """
    driver = _get_driver()
    session = driver.session()
    try:
        yield session
    finally:
        session.close()


def close_driver():
    """Close the global driver instance."""
    global _driver
    if _driver is not None:
        logger.info("[Neo4j] Closing driver")
        _driver.close()
        _driver = None
