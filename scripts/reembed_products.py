"""
One-off script: rebuild the Chroma search text for ALL products so it
includes the `size` field (see build_search_text in database/chroma/utils.py).

Batches upserts so each batch costs one embedding API call instead of one per product.

Run from the repo root:
    python -m scripts.reembed_products
Add --dry-run to preview the new search text without writing to Chroma:
    python -m scripts.reembed_products --dry-run
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from onereside_chatbot.database.collections import product
from onereside_chatbot.database.chroma.utils import _get_collections, build_search_text

BATCH_SIZE = 100


def main(dry_run: bool = False) -> None:
    docs = list(product.find({}, {"_id": 0, "media_url": 0}))
    print(f"Found {len(docs)} products in MongoDB.")

    with_size = sum(1 for d in docs if d.get("size"))
    print(f"{with_size} of them have a size field populated.")

    if dry_run:
        for d in docs[:10]:
            print(f"\n--- {d['product_id']} ({d.get('name', '')}) ---")
            print(build_search_text(d))
        print(f"\nDry run — nothing written. Showing 10 of {len(docs)} search texts.")
        return

    product_col, _ = _get_collections()

    updated = 0
    failed = []
    for start in range(0, len(docs), BATCH_SIZE):
        batch = docs[start:start + BATCH_SIZE]
        try:
            product_col.upsert(
                ids=[d["product_id"] for d in batch],
                documents=[build_search_text(d) for d in batch],
                metadatas=[
                    {
                        "brand_id": d.get("brand_id", ""),
                        "category": d.get("category", ""),
                        "product_id": d["product_id"],
                    }
                    for d in batch
                ],
            )
            updated += len(batch)
            print(f"Upserted {updated}/{len(docs)}")
        except Exception as e:
            failed.extend(d["product_id"] for d in batch)
            print(f"Batch starting at {start} failed: {e}")

    print(f"\nDone. Updated: {updated}, Failed: {len(failed)}")
    if failed:
        print("Failed product_ids:")
        for pid in failed:
            print(f"  {pid}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-embed all product search texts (now including size).")
    parser.add_argument("--dry-run", action="store_true", help="Print sample search texts without writing to Chroma.")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
