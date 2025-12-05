# ORCA Entry Sampler for NOMAD v1

This utility builds **reproducible, representative samples** of ORCA calculations from the NOMAD archive using the v1 `/entries/query` API.

It focuses on a **main-author–diverse stratified sampler**:

- Queries all *visible* ORCA entries via `POST /entries/query`.
- Groups entries by `results.material.structural_type` (e.g. `molecule / cluster`, `bulk`, `atom`, …) and samples proportionally from each group.
- Within each group, prefers entries from **as many different `main_author` values as possible**, then fills remaining slots at random if needed.
- Uses a fixed random seed so the same configuration always produces the same samples.

## What the script does

1. **Fetch population**

   - Calls `https://nomad-lab.eu/prod/v1/api/v1/entries/query`.
   - `owner` is set to `"visible"` (can be changed to `"public"`).
   - Filters by `results.method.simulation.program_name = "ORCA"` (configurable).
   - Paginates until all matching entries are collected.

2. **Build in-memory representation**

   For each entry, the script stores:

   - `entry_id`
   - `upload_id`
   - `mainfile`
   - `main_author` (normalized to a string)
   - `results.material.structural_type` → used as a `system` label

3. **Sample**

   For each requested sample size (e.g. `500`, `2000`):

   - Compute how many entries to take from each `system` so that the sample mirrors the global distribution.
   - Inside each `system`:
     - First select entries whose `main_author` has not been used yet (global uniqueness).
     - Then, if more entries are needed for that `system`, fill up at random from the remaining entries.
   - Adjust slightly to hit the exact target size.

4. **Write outputs**

   For each size `N`, the script writes:

   - `sample_mainauthor_N.json` – list of sampled entries with their fields.
   - `sample_mainauthor_N.csv` – same data as a flat table.

All randomness is controlled by a single `RNG_SEED` constant at the top of the script, making the sampling **fully reproducible** for a given NOMAD snapshot and script version.

## Configuration

At the top of the script:

```python
NOMAD_API_URL = "https://nomad-lab.eu/prod/v1/api/v1"
OWNER = "visible"            # or "public"
PROGRAM_NAME = "ORCA"        # set to None to drop the code filter
PAGE_SIZE = 1000
TARGET_SIZES = [500, 2000]   # sample sizes
RNG_SEED = 123456            # controls reproducibility
```

You can change:

- `OWNER` to restrict to public entries.
- `PROGRAM_NAME` to target another code or the whole archive.
- `TARGET_SIZES` to any list of desired sample sizes.
- `RNG_SEED` if you want a different (but still reproducible) draw.

## Usage

From the directory containing `script.py`:

```bash
python script_distinct_authors.py
```

The script will:

1. Fetch all matching entries from NOMAD.
2. Print basic statistics (system distribution, number of distinct `main_author`s).
3. Produce JSON and CSV files for each requested sample size.

You can then use these files as manifest lists, feed them into downstream workflows, or turn them into NOMAD datasets for long-term reference.
