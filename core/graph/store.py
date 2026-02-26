"""
Smart Medirag — Optimized Graph Store (Neo4j)

Production-grade:
- Safe MERGE usage
- Auto constraint creation
- Fully idempotent
- Batch ingestion (high performance)
- Batch sequence linking
- Fail-soft support
"""

from neo4j import GraphDatabase
from config.system_loader import get_database_config
from core.graph.schema import (
    CREATE_CONSTRAINTS,
    DOCUMENT,
    CHAPTER,
    SUBHEADING,
    CHUNK,
    EMOTION,
    HAS_CHAPTER,
    HAS_SUBHEADING,
    HAS_CHUNK,
    HAS_EMOTION,
    NEXT,
    DOC_ID,
    CHUNK_ID,
    NAME,
    TEXT,
    PAGE_LABEL,
    PAGE_PHYSICAL
)


class GraphStore:

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self):

        db_config = get_database_config()["graph_db"]
        conn = db_config["connection"]

        self.uri = conn["uri"]
        self.username = conn["username"]
        self.password = conn["password"]
        self.database = conn["database"]

        print("\n[GRAPH STORE] Connecting to Neo4j...")

        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.username, self.password),
            max_connection_pool_size=50
        )

        self._create_constraints()

        print("[GRAPH STORE] Connected successfully\n")

    # =====================================================
    # CONSTRAINT CREATION
    # =====================================================

    def _create_constraints(self):

        print("[GRAPH STORE] Creating constraints (if not exists)...")

        with self.driver.session(database=self.database) as session:
            for query in CREATE_CONSTRAINTS:
                session.run(query)

        print("[GRAPH STORE] Constraints verified\n")

    # =====================================================
    # BATCH INGESTION (HIGH PERFORMANCE)
    # =====================================================

    def batch_ingest(self, doc_id: str, chunks: list):
        """
        High-performance ingestion using UNWIND.
        Fully idempotent.
        Null-safe for MERGE.
        """

        query = f"""
        MERGE (d:{DOCUMENT} {{{DOC_ID}: $doc_id}})

        WITH d
        UNWIND $chunks AS chunk

        WITH d,
            chunk,
            COALESCE(chunk.chapter, "Unknown") AS chapter_name,
            COALESCE(chunk.subheading, "Unknown") AS subheading_name,
            COALESCE(chunk.emotion, "Neutral") AS emotion_name

        MERGE (c:{CHAPTER} {{{DOC_ID}: $doc_id, {NAME}: chapter_name}})
        MERGE (s:{SUBHEADING} {{{DOC_ID}: $doc_id, {NAME}: subheading_name}})
        MERGE (ch:{CHUNK} {{{CHUNK_ID}: chunk.chunk_id}})

        SET ch.{TEXT} = chunk.text,
            ch.{PAGE_LABEL} = chunk.page_label,
            ch.{PAGE_PHYSICAL} = chunk.page_physical

        MERGE (e:{EMOTION} {{{NAME}: emotion_name}})

        MERGE (d)-[:{HAS_CHAPTER}]->(c)
        MERGE (c)-[:{HAS_SUBHEADING}]->(s)
        MERGE (s)-[:{HAS_CHUNK}]->(ch)
        MERGE (ch)-[:{HAS_EMOTION}]->(e)
        """

        try:
            with self.driver.session(database=self.database) as session:
                session.run(query, {
                    "doc_id": doc_id,
                    "chunks": chunks
                })
        except Exception as e:
            print(f"[GRAPH BATCH INGEST ERROR] {e}")
            raise

    # =====================================================
    # BATCH SEQUENCE LINKING
    # =====================================================

    def batch_link(self, links: list):
        """
        Batch NEXT relationship creation.
        """

        query = f"""
        UNWIND $links AS pair
        MATCH (a:{CHUNK} {{{CHUNK_ID}: pair[0]}})
        MATCH (b:{CHUNK} {{{CHUNK_ID}: pair[1]}})
        MERGE (a)-[:{NEXT}]->(b)
        """

        try:
            with self.driver.session(database=self.database) as session:
                session.run(query, {"links": links})
        except Exception as e:
            print(f"[GRAPH BATCH LINK ERROR] {e}")
            raise

    # =====================================================
    # DOCUMENT EXISTS CHECK
    # =====================================================

    def document_exists(self, doc_id):

        query = f"""
        MATCH (d:{DOCUMENT} {{{DOC_ID}: $doc_id}})
        RETURN d LIMIT 1
        """

        with self.driver.session(database=self.database) as session:
            result = session.run(query, {"doc_id": doc_id})
            return result.single() is not None

    # =====================================================
    # CLOSE CONNECTION
    # =====================================================

    def close(self):
        self.driver.close()
        print("[GRAPH STORE] Connection closed")