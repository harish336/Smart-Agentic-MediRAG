"""
Frequency Analyzer (Standalone)

Purpose:
- Compute frequency statistics for text, numbers, sizes, labels
- Used for:
  - Header/footer detection
  - Font-size dominance
  - Page-number frequency
  - Offset anchoring
  - Noise removal

This file CAN be run independently.
"""

import sys
import json
from collections import Counter
from pprint import pprint
from typing import List, Any, Dict


class FrequencyAnalyzer:
    def __init__(self, data: List[Any]):
        """
        data:
          - list of strings
          - list of numbers
          - list of dicts (with key extraction)
        """
        self.data = data
        self.counter = Counter()

    # -------------------------------------------------
    # STEP 1: Build frequency map
    # -------------------------------------------------
    def compute(self):
        print("[STEP 1] Computing frequency distribution...")

        for item in self.data:
            if item is None:
                continue

            if isinstance(item, dict):
                self.counter.update(item.values())
            elif isinstance(item, list):
                self.counter.update(item)
            else:
                self.counter[item] += 1

        print("[INFO] Frequency computation completed")
        return self.counter

    # -------------------------------------------------
    # STEP 2: Get most common
    # -------------------------------------------------
    def most_common(self, n: int = 10):
        print(f"\n[STEP 2] Fetching top {n} most common values")
        return self.counter.most_common(n)

    # -------------------------------------------------
    # STEP 3: Detect dominant value
    # -------------------------------------------------
    def dominant(self):
        if not self.counter:
            print("[WARN] Counter empty — no dominant value")
            return None

        dominant_value, count = self.counter.most_common(1)[0]
        print(f"[DOMINANT] Value={dominant_value} | Count={count}")
        return dominant_value

    # -------------------------------------------------
    # STEP 4: Filter by minimum frequency
    # -------------------------------------------------
    def filter_min_frequency(self, min_count: int):
        print(f"\n[STEP 4] Filtering items with frequency >= {min_count}")

        filtered = {
            k: v for k, v in self.counter.items() if v >= min_count
        }

        print(f"[INFO] Items after filtering: {len(filtered)}")
        return filtered

    # -------------------------------------------------
    # STEP 5: Normalize frequencies
    # -------------------------------------------------
    def normalize(self):
        print("\n[STEP 5] Normalizing frequency values")

        total = sum(self.counter.values())
        if total == 0:
            print("[WARN] Total frequency is zero")
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
        self.compute()

        print("\n[SUMMARY]")
        pprint(self.counter)

        print("\n[TOP 5]")
        pprint(self.most_common(5))

        print("\n[DOMINANT VALUE]")
        self.dominant()

        return self.counter


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python frequency.py <input_json>")
        print("\nExample input JSON formats:")
        print("  ['a', 'b', 'a', 'c']")
        print("  [12, 12, 13, 14]")
        print("  [{'size': 12}, {'size': 12}, {'size': 14}]")
        sys.exit(1)

    input_file = sys.argv[1]

    print("=" * 100)
    print("FREQUENCY ANALYZER STARTED")
    print(f"Input file: {input_file}")
    print("=" * 100)

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load input JSON: {e}")
        sys.exit(1)

    analyzer = FrequencyAnalyzer(data)
    counter = analyzer.run()

    print("\n[FINAL FREQUENCY MAP]")
    pprint(counter)

    print("=" * 100)
    print("FREQUENCY ANALYZER COMPLETED")
    print("=" * 100)


if __name__ == "__main__":
    main()
