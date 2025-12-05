#!/usr/bin/env python3
"""
Curate main-author-diverse ORCA samples from the NOMAD Repository (v1 API).

- Fetch all visible ORCA entries via /entries/query
- Stratify by "system" derived from results.material.structural_type
- Within each system, try to pick entries from as many different main_author's
  as possible (global uniqueness preference)
- Draw reproducible samples of target sizes
- Write JSON and CSV manifests for each sample size

Run:
    python script.py
"""

import csv
import json
import random
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Sequence, Set

import requests

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
NOMAD_API_URL = "https://nomad-lab.eu/prod/v1/api/v1"

# "visible" = what you see in the GUI when logged in
# Use "public" if you want only published entries.
OWNER = "visible"

# You can change or set PROGRAM_NAME = None to remove the code filter.
PROGRAM_NAME = "ORCA"

PAGE_SIZE = 1000             # entries per page
TARGET_SIZES = [500, 2000]   # sample sizes you want
RNG_SEED = 123456            # for reproducible sampling


# ----------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------
@dataclass
class RepoEntry:
    """
    Minimal representation of an entry for sampling.
    """
    entry_id: str
    upload_id: Optional[str]
    mainfile: Optional[str]
    main_author: Optional[str]
    system: str                     # classification used for stratification
    structural_type: Optional[str]

    @classmethod
    def from_api_result(cls, d: dict) -> "RepoEntry":
        """
        Build RepoEntry from a single hit of /entries/query.

        Expected structure (since we use required.include):

            {
              "entry_id": "...",
              "upload_id": "...",
              "mainfile": "...",
              "main_author": <string or object>,
              "results": {
                "material": {
                  "structural_type": "molecule / cluster" | "bulk" | ...
                }
              }
            }

        We try to normalize main_author to a string.
        """
        entry_id = d["entry_id"]

        upload_id = d.get("upload_id")
        mainfile = d.get("mainfile")

        raw_ma = d.get("main_author")
        main_author: Optional[str]
        if isinstance(raw_ma, str):
            main_author = raw_ma.strip() or None
        elif isinstance(raw_ma, dict):
            # Heuristic: prefer name, then email, then repr
            name = raw_ma.get("name")
            email = raw_ma.get("email")
            if isinstance(name, str) and name.strip():
                main_author = name.strip()
            elif isinstance(email, str) and email.strip():
                main_author = email.strip()
            else:
                # Fallback: some stable string representation
                main_author = json.dumps(raw_ma, sort_keys=True)
        else:
            main_author = None

        results = d.get("results") or {}
        material = results.get("material") or {}
        structural_type = material.get("structural_type")

        # use structural_type as our "system" label; fall back to "unknown"
        system = structural_type if structural_type else "unknown"

        return cls(
            entry_id=entry_id,
            upload_id=upload_id,
            mainfile=mainfile,
            main_author=main_author,
            system=system,
            structural_type=structural_type,
        )


# ----------------------------------------------------------------------
# API: fetch full ORCA population via /entries/query
# ----------------------------------------------------------------------
def fetch_all_entries() -> List[RepoEntry]:
    """
    Fetch entries using the v1 /entries/query API.

    Uses value-based pagination via `next_page_after_value`.
    If PROGRAM_NAME is set, filters by results.method.simulation.program_name.
    """
    print("[info] Fetching population from NOMAD (v1 /entries/query)...")

    query: Dict[str, object] = {}
    if PROGRAM_NAME is not None:
        query["results.method.simulation.program_name"] = PROGRAM_NAME

    json_body = {
        "owner": OWNER,
        "query": query,
        "pagination": {
            "page_size": PAGE_SIZE,
            "order_by": "entry_id",
            "order": "asc",
        },
        "required": {
            # doc quantities (not metadata.*)
            "include": [
                "entry_id",
                "upload_id",
                "mainfile",
                "main_author",
                "results.material.structural_type",
            ]
        },
    }

    all_entries: List[RepoEntry] = []
    page = 0

    while True:
        resp = requests.post(f"{NOMAD_API_URL}/entries/query", json=json_body)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            print("[error] status:", resp.status_code)
            print("[error] body:", resp.text[:2000])
            raise

        data = resp.json()
        hits = data.get("data", [])
        if not hits:
            break

        for d in hits:
            try:
                entry = RepoEntry.from_api_result(d)
                all_entries.append(entry)
            except KeyError:
                # Skip malformed hits (should be rare)
                continue

        page += 1
        print(
            f"[page] {page}: fetched {len(hits)} entries, "
            f"total so far {len(all_entries)}"
        )

        pagination = data.get("pagination") or {}
        next_val = pagination.get("next_page_after_value")
        if not next_val:
            # no further pages
            break

        # Continue after this entry_id in subsequent request
        json_body["pagination"]["page_after_value"] = next_val

    print(f"[info] Done. Total entries fetched: {len(all_entries)}")
    return all_entries


# ----------------------------------------------------------------------
# main_author-diverse stratified sampling
# ----------------------------------------------------------------------
def main_author_diverse_stratified_sample(
    entries: Sequence[RepoEntry],
    target_size: int,
    rng: random.Random,
) -> List[RepoEntry]:
    """
    Stratified random sample over RepoEntry.system, *favoring* main_author diversity.

    Steps:
    - Bucket entries by `system`.
    - Compute per-system allocation approximately proportional to bucket size.
    - For each system:
        - Shuffle bucket.
        - First pass: pick entries whose main_author is NOT yet used globally.
        - Second pass (if still needed): fill up to allocation ignoring main_author overlap.
    - Trim / top up globally to match `target_size` exactly.
    """
    if target_size <= 0:
        raise ValueError("target_size must be positive")

    n_total = len(entries)
    if n_total == 0:
        raise ValueError("no entries available for sampling")

    if target_size > n_total:
        print(
            f"[warn] target_size {target_size} > total {n_total}, "
            f"reducing to {n_total}"
        )
        target_size = n_total

    # Bucket entries by system label
    buckets: Dict[str, List[RepoEntry]] = {}
    for e in entries:
        buckets.setdefault(e.system, []).append(e)

    # --- compute proportional allocation per system ---
    alloc: Dict[str, int] = {}
    for system, bucket in buckets.items():
        frac = len(bucket) / n_total
        k = int(round(frac * target_size))
        if k < 1 and len(bucket) > 0:
            k = 1
        alloc[system] = k

    # Adjust allocation to match target_size exactly
    current = sum(alloc.values())
    systems_sorted = sorted(
        buckets.keys(),
        key=lambda s: len(buckets[s]),
        reverse=True,
    )

    if current < target_size:
        # Distribute remaining samples to largest buckets
        remaining = target_size - current
        idx = 0
        while remaining > 0:
            s = systems_sorted[idx % len(systems_sorted)]
            alloc[s] += 1
            remaining -= 1
            idx += 1
    elif current > target_size:
        # Remove surplus from largest buckets, but keep at least 1 per non-empty bucket
        surplus = current - target_size
        idx = 0
        while surplus > 0 and any(v > 1 for v in alloc.values()):
            s = systems_sorted[idx % len(systems_sorted)]
            if alloc[s] > 1:
                alloc[s] -= 1
                surplus -= 1
            idx += 1

    # --- main_author-diverse selection ---
    used_authors: Set[str] = set()
    selected: List[RepoEntry] = []

    for system in systems_sorted:
        bucket = buckets[system]
        need = alloc.get(system, 0)
        if need <= 0 or not bucket:
            continue

        bucket_copy = bucket[:]
        rng.shuffle(bucket_copy)

        system_selected: List[RepoEntry] = []

        # First pass: prefer unseen main_author
        for e in bucket_copy:
            if len(system_selected) >= need:
                break
            if e.main_author is None:
                continue
            if e.main_author not in used_authors:
                system_selected.append(e)
                used_authors.add(e.main_author)

        # Second pass: fill remaining slots ignoring author overlap
        if len(system_selected) < need:
            for e in bucket_copy:
                if len(system_selected) >= need:
                    break
                if e in system_selected:
                    continue
                system_selected.append(e)

        selected.extend(system_selected)

    # --- global trim / top-up to exact target_size ---
    if len(selected) > target_size:
        selected = rng.sample(selected, target_size)
    elif len(selected) < target_size:
        selected_ids = {e.entry_id for e in selected}
        remaining_pool = [e for e in entries if e.entry_id not in selected_ids]
        k_extra = min(target_size - len(selected), len(remaining_pool))
        if k_extra > 0:
            selected.extend(rng.sample(remaining_pool, k_extra))

    return selected


# ----------------------------------------------------------------------
# Output helpers
# ----------------------------------------------------------------------
def write_json(filename: str, entries: List[RepoEntry]) -> None:
    data = [asdict(e) for e in entries]
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[info] Wrote JSON sample: {filename}")


def write_csv(filename: str, entries: List[RepoEntry]) -> None:
    fieldnames = [
        "entry_id",
        "upload_id",
        "mainfile",
        "main_author",
        "system",
        "structural_type",
    ]
    with open(filename, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in entries:
            writer.writerow(asdict(e))
    print(f"[info] Wrote CSV sample:  {filename}")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> None:
    rng = random.Random(RNG_SEED)

    all_entries = fetch_all_entries()
    if not all_entries:
        print("[error] No entries fetched, aborting.")
        return

    # Global system stats
    global_system_dist: Dict[str, int] = {}
    for e in all_entries:
        global_system_dist[e.system] = global_system_dist.get(e.system, 0) + 1
    print(f"[info] Global system distribution: {global_system_dist}")

    # Global main_author stats
    distinct_main_authors: Set[str] = set(
        e.main_author for e in all_entries if e.main_author is not None
    )
    print(f"[info] Global distinct main_author's: {len(distinct_main_authors)}")

    for size in TARGET_SIZES:
        if size <= 0:
            continue

        if size > len(all_entries):
            print(
                f"[warn] Requested {size} entries but only {len(all_entries)} "
                f"are available. Using {len(all_entries)} instead."
            )
            size = len(all_entries)


        print(
            f"[info] Creating main-author-diverse stratified sample of size {size}..."
        )
        sample = main_author_diverse_stratified_sample(all_entries, size, rng)

        # Sample stats
        sample_system_dist: Dict[str, int] = {}
        sample_authors: Set[str] = set()
        for e in sample:
            sample_system_dist[e.system] = sample_system_dist.get(e.system, 0) + 1
            if e.main_author is not None:
                sample_authors.add(e.main_author)

        print(f"[info] Sample {size} system distribution: {sample_system_dist}")
        print(f"[info] Sample {size} distinct main_author's: {len(sample_authors)}")

        json_name = f"sample_mainauthor_{size}.json"
        csv_name = f"sample_mainauthor_{size}.csv"

        write_json(json_name, sample)
        write_csv(csv_name, sample)
        print()

    print("[done] Sampling finished.")


if __name__ == "__main__":
    main()
