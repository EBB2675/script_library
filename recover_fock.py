#!/usr/bin/env python3


import argparse
import json
import sys

import numpy as np
import scipy as sp


def reconstruct_fock(S, C, energies):
    # See Szabo Ostlund p. 142 and p. 143
    s, U = np.linalg.eigh(S)
    Xinv = U @ np.diag(np.sqrt(s)) @ U.T

    C_ = Xinv @ C
    F_ = C_ @ np.diag(energies) @ C_.T
    F = Xinv @ F_ @ Xinv.T
    return F


def read_mos(mol):
    mos = mol["MolecularOrbitals"]["MOs"]
    nmos = len(mos)
    C = np.empty((nmos, nmos))
    energies = np.empty(nmos)
    for i in range(nmos):
        mo = mos[i]
        C[:, i] = mo["MOCoefficients"]
        energies[i] = mo["OrbitalEnergy"]
    return energies, C


def parse_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("json", help="Path to ORCA JSON file.")
    return parser.parse_args(args)


def run():
    args = parse_args(sys.argv[1:])

    with open(args.json) as handle:
        data = json.load(handle)
    mol = data["Molecule"]

    # Overlap matrix
    S = np.array(mol["S-Matrix"])

    # MO eigenvalues and -eigenvectors
    energies, C = read_mos(mol)

    # Reconstructed Fock matrix
    F = reconstruct_fock(S, C, energies)

    # Check correctness of reconstructed F by diagonalization
    energies_rec, C_rec = sp.linalg.eigh(F, S)
    np.testing.assert_allclose(energies_rec, energies)
    print("Reconstructed eigenvalues match!")
    # Signs of eigenvalues may differ, so we can't compare them directly
    # Assert that C^T @ S @ C is the unit matrix
    I_rec = np.abs(C_rec.T @ S @ C)
    # Matching is not ideal, max. abs. error is 8e-10
    np.testing.assert_allclose(I_rec, np.eye(len(I_rec)), atol=1e-9)
    print("Reconstructed eigenvectors match!")

    np.save("S.npy", S)
    np.save("F.npy", F)


if __name__ == "__main__":
    run()
