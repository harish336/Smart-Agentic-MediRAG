"""
Frequency Analyzer (Standalone)
"""

import sys
import json
from collections import Counter
from pprint import pformat
from typing import List, Any

from core.utils.logging_utils import get_component_logger

# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("FrequencyAnalyzer", component="ingestion")


class FrequencyAnalyzer:

    def __init__(self, data: List[Any]):
        self.data = data
        self.counter = Counter()

    # -------------------------------------------------
    # STEP 1: Build frequency map
    # -------------------------------------------------
    def compute(self):

        logger.info("[STEP 1] Computing frequency distribution...")

        try:
            for item in self.data:
                if item is None:
                    continue

                if isinstance(item, dict):
                    self.counter.update(item.values())
                elif isinstance(item, list):
                    self.counter.update(item)
                else:
                    self.counter[item] += 1

            logger.info("Frequency computation completed")
            return self.counter

        except Exception:
            logger.exception("Frequency computation failed")
            raise

    # -------------------------------------------------
    # STEP 2: Get most common
    # -------------------------------------------------
    def most_common(self, n: int = 10):

        logger.info(f"Fetching top {n} most common values")
        return self.counter.most_common(n)

    # -------------------------------------------------
    # STEP 3: Detect dominant value
    # -------------------------------------------------
    def dominant(self):

        if not self.counter:
            logger.warning("Counter empty — no dominant value")
            return None

        dominant_value, count = self.counter.most_common(1)[0]
        logger.info(f"Dominant Value={dominant_value} | Count={count}")
        return dominant_value

    # -------------------------------------------------
    # STEP 4: Filter by minimum frequency
    # -------------------------------------------------
    def filter_min_frequency(self, min_count: int):

        logger.info(f"Filtering items with frequency >= {min_count}")

        filtered = {
            k: v for k, v in self.counter.items() if v >= min_count
        }

        logger.info(f"Items after filtering: {len(filtered)}")
        return filtered

    # -------------------------------------------------
    # STEP 5: Normalize frequencies
    # -------------------------------------------------
    def normalize(self):

        logger.info("Normalizing frequency values")

        total = sum(self.counter.values())

        if total == 0:
            logger.warning("Total frequency is zero")
            return {}

        normalized = {
            k: round(v / total, 4)
            for k, v in self.counter.items()
        }

        return normalized

    # -------------------------------------------------
    # RUN FULL ANALYSIS
    # -------------------------------------------------
    def run(self):

        try:
            self.compute()

            logger.info("SUMMARY:")
            logger.info(pformat(self.counter))

            logger.info("TOP 5:")
            logger.info(pformat(self.most_common(5)))

            logger.info("DOMINANT VALUE:")
            self.dominant()

            return self.counter

        except Exception:
            logger.exception("Frequency analysis failed")
            raise


# ============================================================
# STANDALONE RUNNER
# ============================================================

def main():

    if len(sys.argv) < 2:
        logger.warning("Usage: python frequency.py <input_json>")
        sys.exit(1)

    input_file = sys.argv[1]

    logger.info("=" * 100)
    logger.info("FREQUENCY ANALYZER STARTED")
    logger.info(f"Input file: {input_file}")
    logger.info("=" * 100)

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        logger.exception("Failed to load input JSON")
        sys.exit(1)

    try:
        analyzer = FrequencyAnalyzer(data)
        counter = analyzer.run()

        logger.info("FINAL FREQUENCY MAP:")
        logger.info(pformat(counter))

    except Exception:
        logger.exception("Frequency analyzer crashed")
        sys.exit(1)

    logger.info("=" * 100)
    logger.info("FREQUENCY ANALYZER COMPLETED")
    logger.info("=" * 100)


if __name__ == "__main__":
    main()
