# Comparing “Pointer” vs “In-line” Element Data in NOMAD

## The problem

When a simulation contains **many atoms** you must decide where to store the three
immutable element fields

* `chemical_symbol`
* `atomic_number`
* `mass_number`

Two options:

| layout | description |
| ------ | ----------- |
| **Pointer** | Store the fields **once** in an `AtomDefn` section and let every `AtomsState` reference it via `atom_definition_ref`. |
| **In-line** | Copy the same three values into **every** `AtomsState`. |

Which one uses less memory / disk and is faster?

---

## How we tested

1. **Created 100 000 carbon atoms** in both layouts inside the real NOMAD runtime  
   (plug-ins disabled with `NOMAD_SKIP_PLUGINS=1`).
2. Each atom also carried a **5 × 5 Hubbard-U matrix** to imitate realistic payload.
3. Measured  
   * deep RAM size (`pympler.asizeof`)  
   * pickle size + time (`cloudpickle`)  
   * NOMAD-JSON size + time (`section.m_to_dict()` → `json.dumps`)  
   * pure object-creation time

---

## Results (100 000 atoms, U-matrix 5 × 5)

| layout   | RAM | pickle | JSON | total time\* |
| -------- | ---:| ------:| ----:| ------------:|
| **Pointer** | **103.6 MB** | **37.6 MB** | **65.9 MB** | **40 s** |
| In-line     | 110.9 MB | 43.1 MB | 69.4 MB | 49 s |
| **Overhead (inline / pointer)** | **+7 %** | **+15 %** | **+5 %** | **+22 %** |

\* *build + pickle + JSON serialisation*

---

## Take-aways

* With just three scalars duplicated, the **in-line layout costs 5–15 % more
  RAM/disk** and **≈ 20 % more CPU** at this scale.
* A single shared `AtomDefn` keeps archives smaller and **guarantees one source
  of truth**.  
* It doesn't matter so much. **But a pointer is never more expensive than repetition.**
