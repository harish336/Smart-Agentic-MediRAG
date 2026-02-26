"""
Smart Medirag — Optimized Graph Schema

Production-safe:
- Unique constraints
- No duplicate ingestion
- Scoped hierarchy
- Emotion modeling
"""

# =====================================================
# NODE LABELS
# =====================================================

DOCUMENT = "Document"
CHAPTER = "Chapter"
SUBHEADING = "Subheading"
CHUNK = "Chunk"
EMOTION = "Emotion"

# =====================================================
# RELATIONSHIP TYPES
# =====================================================

HAS_CHAPTER = "HAS_CHAPTER"
HAS_SUBHEADING = "HAS_SUBHEADING"
HAS_CHUNK = "HAS_CHUNK"
NEXT = "NEXT"
HAS_EMOTION = "HAS_EMOTION"

# =====================================================
# PROPERTY KEYS
# =====================================================

DOC_ID = "doc_id"
CHUNK_ID = "chunk_id"
NAME = "name"
TEXT = "text"
PAGE_LABEL = "page_label"
PAGE_PHYSICAL = "page_physical"

# =====================================================
# CONSTRAINTS (NO DUPLICATES)
# =====================================================

CREATE_CONSTRAINTS = [

    # Document unique
    f"""
    CREATE CONSTRAINT IF NOT EXISTS
    FOR (d:{DOCUMENT})
    REQUIRE d.{DOC_ID} IS UNIQUE
    """,

    # Chunk unique
    f"""
    CREATE CONSTRAINT IF NOT EXISTS
    FOR (c:{CHUNK})
    REQUIRE c.{CHUNK_ID} IS UNIQUE
    """,

    # Chapter scoped uniqueness
    f"""
    CREATE CONSTRAINT IF NOT EXISTS
    FOR (c:{CHAPTER})
    REQUIRE (c.{DOC_ID}, c.{NAME}) IS UNIQUE
    """,

    # Subheading scoped uniqueness
    f"""
    CREATE CONSTRAINT IF NOT EXISTS
    FOR (s:{SUBHEADING})
    REQUIRE (s.{DOC_ID}, s.{NAME}) IS UNIQUE
    """,

    # Emotion unique
    f"""
    CREATE CONSTRAINT IF NOT EXISTS
    FOR (e:{EMOTION})
    REQUIRE e.{NAME} IS UNIQUE
    """
]