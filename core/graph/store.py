"""
Smart Medirag — Production Graph Store (Neo4j)

Features:
- Safe MERGE-based ingestion
- Unique constraints auto-created
- Fully idempotent
- High-performance batch ingestion (UNWIND)
- Batch NEXT linking
- Public run_query() for retrievers
- Clean metadata storage
- Stores doc_id inside Chunk (CRITICAL FIX)

Author: Smart Medirag System
"""

from neo4j import GraphDatabase
from config.system_loader import get_database_config
from core.graph.schema import (
    CREATE_CONSTRAINTS,
    CREATE_INDEXES,
    CHUNK_TEXT_FULLTEXT_INDEX,
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
        self._create_indexes()

        print("[GRAPH STORE] Connected successfully\n")

    # =====================================================
    # CREATE CONSTRAINTS
    # =====================================================

    def _create_constraints(self):

        print("[GRAPH STORE] Creating constraints (if not exists)...")

        with self.driver.session(database=self.database) as session:
            for query in CREATE_CONSTRAINTS:
                session.run(query)

        print("[GRAPH STORE] Constraints verified\n")

    # =====================================================
    # CREATE INDEXES
    # =====================================================

    def _create_indexes(self):

        print("[GRAPH STORE] Creating indexes (if not exists)...")

        with self.driver.session(database=self.database) as session:
            for query in CREATE_INDEXES:
                session.run(query)

        print("[GRAPH STORE] Indexes verified\n")

    # =====================================================
    # BATCH INGESTION (FULLY CORRECTED)
    # =====================================================

    def batch_ingest(self, doc_id: str, chunks: list):
        """
        High-performance ingestion using UNWIND.
        Fully idempotent.
        Ensures:
            - doc_id stored inside Chunk
            - Proper chapter/subheading linking
            - Emotion node linking
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

        SET ch.{DOC_ID} = $doc_id,
            ch.{TEXT} = chunk.text,
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
            print("[GRAPH STORE] Batch ingestion failed:", e)
            raise

    # =====================================================
    # BATCH SEQUENTIAL LINKING
    # =====================================================

    def batch_link(self, links: list):
        """
        Creates NEXT relationships between chunks.
        links = [(chunk_id_1, chunk_id_2), ...]
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
            print("[GRAPH STORE] Batch link failed:", e)
            raise

    # =====================================================
    # DOCUMENT EXISTS CHECK
    # =====================================================

    def document_exists(self, doc_id: str) -> bool:

        query = f"""
        MATCH (d:{DOCUMENT} {{{DOC_ID}: $doc_id}})
        RETURN d LIMIT 1
        """

        with self.driver.session(database=self.database) as session:
            result = session.run(query, {"doc_id": doc_id})
            return result.single() is not None

    # =====================================================
    # PUBLIC READ QUERY METHOD
    # =====================================================

    def run_query(self, cypher: str, params: dict = None):
        """
        Standard read query executor.
        Used by GraphRetriever.
        """

        if params is None:
            params = {}

        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(cypher, params)
                return [record.data() for record in result]

        except Exception as e:
            print("[GRAPH STORE] Query failed:", e)
            return []

    # =====================================================
    # FULLTEXT SEARCH (OPTIONAL FAST PATH)
    # =====================================================

    def fulltext_query_chunks(
        self,
        query: str,
        limit: int,
        doc_id: str = None,
        emotion: str = None
    ):
        """
        Fast retrieval using fulltext index.
        Falls back to caller if index is unavailable.
        """

        cypher = f"""
        CALL db.index.fulltext.queryNodes("{CHUNK_TEXT_FULLTEXT_INDEX}", $query)
        YIELD node, score
        OPTIONAL MATCH (node)-[:HAS_EMOTION]->(e:Emotion)
        WHERE
            ($doc_id IS NULL OR node.doc_id = $doc_id)
            AND ($emotion IS NULL OR e.name = $emotion)
        RETURN
            node.chunk_id AS chunk_id,
            node.doc_id AS doc_id,
            node.text AS text,
            e.name AS emotion,
            score AS score
        ORDER BY score DESC
        LIMIT $limit
        """

        return self.run_query(
            cypher,
            {
                "query": query,
                "limit": limit,
                "doc_id": doc_id,
                "emotion": emotion
            }
        )

    # =====================================================
    # DELETE DOCUMENT (OPTIONAL UTILITY)
    # =====================================================

    def delete_document(self, doc_id: str):
        """
        Deletes document and its related structure.
        """

        query = f"""
        MATCH (d:{DOCUMENT} {{{DOC_ID}: $doc_id}})
        DETACH DELETE d
        """

        with self.driver.session(database=self.database) as session:
            session.run(query, {"doc_id": doc_id})

    # =====================================================
    # CLOSE CONNECTION
    # =====================================================

    def close(self):
        self.driver.close()
        print("[GRAPH STORE] Connection closed")
