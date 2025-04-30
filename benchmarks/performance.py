#!/usr/bin/env python
"""
benchmark_atoms_state.py  –  pointer vs. inline element data
────────────────────────────────────────────────────────────
layout A  (pointer)  : AtomsState → AtomDefn(chemical_symbol, atomic_number, mass_number)
layout B  (inline)   : AtomsStateInline stores those three scalars itself

Metrics
  • deep RAM size (pympler)
  • cloudpickle size + time
  • NOMAD-JSON size + time  ← fixed API call
  • object-creation time
"""
from __future__ import annotations
import os, time, json
from typing import Tuple

import numpy as np
from pympler.asizeof import asizeof
import cloudpickle as pickle         # handles dynamic NOMAD classes

os.environ.setdefault("NOMAD_SKIP_PLUGINS", "1")   # avoid plug-in loops

from nomad.metainfo import Quantity, Section
from nomad_simulations.schema_packages.atoms_state import (
    AtomsState, AtomDefn, HubbardInteractions
)

# ───────── parameters you may tweak ──────────────────────────────────────────
N_ATOMS        = 100_000
ELEMENT        = ("C", 6, 12)         # symbol, Z, mass number
HUBBARD_SHAPE  = (5, 5)               # payload size per atom
# ─────────────────────────────────────────────────────────────────────────────


def make_hi() -> HubbardInteractions:
    hi = HubbardInteractions()
    hi.u_matrix = np.random.rand(*HUBBARD_SHAPE) * 1.0e-19
    return hi


# ───────── inline variant definition (layout B) ──────────────────────────────
class AtomsStateInline(AtomsState):
    m_def = Section()
    chemical_symbol = Quantity(type=str)
    atomic_number   = Quantity(type=np.int32)
    mass_number     = Quantity(type=np.int32)


print(f"\nBenchmarking {N_ATOMS:,} atoms   element={ELEMENT[0]}   matrix={HUBBARD_SHAPE}\n")

# ───────── build layout A  (pointer) ─────────────────────────────────────────
shared_def = AtomDefn(
    chemical_symbol=ELEMENT[0],
    atomic_number=ELEMENT[1],
    mass_number=ELEMENT[2],
)

t0 = time.perf_counter()
pointer_atoms = []
for _ in range(N_ATOMS):
    a = AtomsState(atom_definition_ref=shared_def)
    a.hubbard_interactions = make_hi()
    pointer_atoms.append(a)
t_pointer_build = time.perf_counter() - t0

# ───────── build layout B  (inline) ──────────────────────────────────────────
t0 = time.perf_counter()
inline_atoms = []
for _ in range(N_ATOMS):
    a = AtomsStateInline(
        chemical_symbol=ELEMENT[0],
        atomic_number=ELEMENT[1],
        mass_number=ELEMENT[2],
    )
    a.hubbard_interactions = make_hi()
    inline_atoms.append(a)
t_inline_build = time.perf_counter() - t0

# ───────── helper for pickle / JSON serialisation ───────────────────────────
def pickle_size_time(obj) -> Tuple[int, float]:
    t0 = time.perf_counter()
    blob = pickle.dumps(obj, protocol=4)
    return len(blob), time.perf_counter() - t0

def json_size_time(obj) -> Tuple[int, float]:
    t0 = time.perf_counter()
    # FIX: no more 'with_value_types' kwarg in new NOMAD
    s = json.dumps([sec.m_to_dict() for sec in obj])
    return len(s.encode()), time.perf_counter() - t0

# ───────── collect metrics ──────────────────────────────────────────────────
ram_ptr   = asizeof(pointer_atoms)
ram_inl   = asizeof(inline_atoms)

pkl_ptr, tpkl_ptr   = pickle_size_time(pointer_atoms)
pkl_inl, tpkl_inl   = pickle_size_time(inline_atoms)

json_ptr, tjson_ptr = json_size_time(pointer_atoms)
json_inl, tjson_inl = json_size_time(inline_atoms)

# ───────── report ───────────────────────────────────────────────────────────
def row(name, ram, pkl, js, tbuild, tpkl, tjs):
    print(f"{name:<10} {ram/1e6:12.2f} {pkl/1e6:12.2f} {js/1e6:12.2f} "
          f"{tbuild+tpkl+tjs:9.2f}")

print(f"{'layout':<10} {'RAM [MB]':>12} {'pickle [MB]':>12} {'JSON [MB]':>12} {'Σ time [s]':>11}")
print("-"*63)
row("pointer", ram_ptr, pkl_ptr, json_ptr, t_pointer_build, tpkl_ptr, tjson_ptr)
row("inline",  ram_inl, pkl_inl, json_inl, t_inline_build, tpkl_inl, tjson_inl)

print("\nrelative cost  inline / pointer")
print(f"  RAM    : {ram_inl / ram_ptr:6.2f}×")
print(f"  pickle : {pkl_inl / pkl_ptr:6.2f}×")
print(f"  JSON   : {json_inl / json_ptr:6.2f}×")
total_ptr = t_pointer_build + tpkl_ptr + tjson_ptr
total_inl = t_inline_build  + tpkl_inl + tjson_inl
print(f"  time   : {total_inl / total_ptr:6.2f}×\n")
