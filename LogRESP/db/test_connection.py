from neo4j import GraphDatabase

URI      = "bolt://localhost:7687"
USER     = "neo4j"
PASSWORD = "test1-beth123"

try:
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    driver.verify_connectivity()
    print("✅ Connected to Neo4j successfully!")
    driver.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")