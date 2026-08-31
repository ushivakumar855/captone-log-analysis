import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class Neo4jRouter:
    def __init__(self):
        # THEIA Credentials
        self.theia_uri = os.getenv('NEO4J_THEIA_URI', 'bolt://localhost:7687')
        self.theia_user = os.getenv('NEO4J_THEIA_USER', 'neo4j')
        self.theia_pass = os.getenv('NEO4J_THEIA_PASS', 'neo4j123')
        self.theia_driver = None

        # BETH Credentials
        self.beth_uri = os.getenv('NEO4J_BETH_URI', 'bolt://localhost:7687')
        self.beth_user = os.getenv('NEO4J_BETH_USER', 'neo4j')
        self.beth_pass = os.getenv('NEO4J_BETH_PASS', 'beth_password_123')
        self.beth_driver = None

    def get_driver(self, dataset_tag):
        """Lazy loads the database connection ONLY when specifically requested."""
        if dataset_tag == 'darpa':
            if not self.theia_driver:
                self.theia_driver = GraphDatabase.driver(
                    self.theia_uri, auth=(self.theia_user, self.theia_pass), max_connection_pool_size=10
                )
            return self.theia_driver
        elif dataset_tag == 'beth':
            if not self.beth_driver:
                self.beth_driver = GraphDatabase.driver(
                    self.beth_uri, auth=(self.beth_user, self.beth_pass), max_connection_pool_size=10
                )
            return self.beth_driver
        else:
            raise ValueError("Unknown dataset tag.")

    def close(self):
        if self.theia_driver: self.theia_driver.close()
        if self.beth_driver: self.beth_driver.close()

    def query(self, dataset_tag, query, parameters=None):
        driver = self.get_driver(dataset_tag)
        try:
            with driver.session() as session:
                result = session.run(query, parameters)
                return [record.data() for record in result]
        except Exception as e:
            raise Exception(f"Query execution failed on {dataset_tag.upper()}: {e}")

# Global router instance for tools to import
db_router = Neo4jRouter()