#!/usr/bin/env python3
"""
Curate stratified ORCA samples from the NOMAD Repository (v1 API).

- Fetch all visible ORCA entries via /entries/query
- Stratify by a derived "system" label from results.material.structural_type
- Draw stratified, reproducible samples of target sizes
- Write JSON and CSV manifests for each sample size

Run:
    python script.py
"""

import csv
import json
import random
from dataclasses import dataclass, asdict
from typing import Dict, List, Sequence

import requests

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
NOMAD_API_URL = "https://nomad-lab.eu/prod/v1/api/v1"

# "visible" = what we see in the GUI when logged in
# Use "public" for only published entries
OWNER = "visible"

PROGRAM_NAME = "ORCA"
PAGE_SIZE = 1000            # entries per page
TARGET_SIZES = [500, 2000]  # sample sizes you want
RNG_SEED = 123456           # for reproducible sampling


# ----------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------
@dataclass
class RepoEntry:
    """
    Minimal representation of an entry for sampling.
    """
    entry_id: str
    upload_id: str | None
    mainfile: str | None
    system: str                # classification used for stratification
    structural_type: str | None

    @classmethod
    def from_api_result(cls, d: dict) -> "RepoEntry":
        """
        Build RepoEntry from a single hit of /entries/query.

        Expected structure (since we use required.include):

            {
              "entry_id": "...",
              "upload_id": "...",
              "mainfile": "...",
              "results": {
                "material": {
                  "structural_type": "molecule" | "bulk" | ...
                }
              }
            }
        """
        entry_id = d["entry_id"]

        # flat fields when requested via required.include
        upload_id = d.get("upload_id")
        mainfile = d.get("mainfile")

        results = d.get("results") or {}
        material = results.get("material") or {}
        structural_type = material.get("structural_type")

        # use structural_type as our "system" label; fall back to "unknown"
        system = structural_type if structural_type else "unknown"

        return cls(
            entry_id=entry_id,
            upload_id=upload_id,
            mainfile=mainfile,
            system=system,
            structural_type=structural_type,
        )


# ----------------------------------------------------------------------
# API: fetch full ORCA population via /entries/query
# ----------------------------------------------------------------------
def fetch_all_orca_entries() -> List[RepoEntry]:
    """
    Fetch all ORCA entries using the v1 /entries/query API.

    Uses value-based pagination via `next_page_after_value`.
    """
    print("[info] Fetching full ORCA population from NOMAD (v1 /entries/query)...")

    json_body = {
        "owner": OWNER,
        "query": {
            # v1 filter syntax: field: value
            "results.method.simulation.program_name": PROGRAM_NAME
        },
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

    print(f"[info] Done. Total ORCA entries fetched: {len(all_entries)}")
    return all_entries


# ----------------------------------------------------------------------
# Stratified sampling (over `system`)
# ----------------------------------------------------------------------
def stratified_sample(
    entries: Sequence[RepoEntry],
    target_size: int,
    rng: random.Random,
) -> List[RepoEntry]:
    """
    Stratified random sample over RepoEntry.system.

    Allocation is proportional to bucket size, with a minimum of 1
    per non-empty bucket; then adjusted to exactly target_size if possible.
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

    # Initial proportional allocation
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

    # Now draw the samples
    selected: List[RepoEntry] = []
    for system, bucket in buckets.items():
        k = min(alloc.get(system, 0), len(bucket))
        if k <= 0:
            continue
        selected.extend(rng.sample(bucket, k))

    # Fix small mismatches by global trim / top-up
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

    all_entries = fetch_all_orca_entries()
    if not all_entries:
        print("[error] No ORCA entries fetched, aborting.")
        return

    # Quick global system distribution
    global_dist: Dict[str, int] = {}
    for e in all_entries:
        global_dist[e.system] = global_dist.get(e.system, 0) + 1
    print(f"[info] Global system distribution: {global_dist}")

    for size in TARGET_SIZES:
        if size <= 0:
            continue

        if size > len(all_entries):
            print(
                f"[warn] Requested {size} entries but only {len(all_entries)} "
                f"are available. Using {len(all_entries)} instead."
            )
            size = len(all_entries)

        print(f"[info] Creating stratified sample of size {size}...")
        sample = stratified_sample(all_entries, size, rng)

        # Print sample system distribution
        sample_dist: Dict[str, int] = {}
        for e in sample:
            sample_dist[e.system] = sample_dist.get(e.system, 0) + 1
        print(f"[info] Sample {size} system distribution: {sample_dist}")

        json_name = f"orca_sample_{size}.json"
        csv_name = f"orca_sample_{size}.csv"

        write_json(json_name, sample)
        write_csv(csv_name, sample)
        print()

    print("[done] Sampling finished.")


if __name__ == "__main__":
    main()
