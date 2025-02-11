"""
Read transitions from ORCA output file and analyze their composition in terms of AO composition (e.g. Co s, Co px, py, pz, ...) of the contributing MO
"""

import os
import re
import sys
import numpy as np
import matplotlib.pyplot as plt
import scipy.special

file_mos = r'/huge/ebbo/CoVT/DATA_Jul26/VtC/better_analysis/ref_acac/ref_acac_Co3_read.out' 
file_transitions = r'/huge/ebbo/CoVT/DATA_Jul26/VtC/better_analysis/ref_acac/acac_Co3.out'

bx_plot, by_plot = np.loadtxt('acac_Co3.out.xessoc.dat', usecols=(0,1), unpack=True)

def filter_spectra(
x,
y_arr,
digits = 0
):
    """
    Take an energy axis *x* and an n-dimensional array *y_arr* and group entries which are close in energy along *x*. The energy axis has to align with the first dimension of *y_arr*.

    *digits* controls the binning. E.g.

    digits = 0    # All sticks which are within 1 eV are grouped
    digits = 1    # All sticks which are within 0.1 eV are grouped
    ...
    """

    x = np.round(x, digits)
    arr = np.array(y_arr)

    # Sort the arrays according to x
    sort_idx = np.argsort(x)
    sorted_a = arr[sort_idx]
    x = x[sort_idx]

    values, indices, counts = np.unique(x, return_index = True, return_counts = True)

    x_filtered = np.empty(values.shape)
    filtered_array = np.empty((values.shape[0],) + sorted_a.shape[1:])
    for idx, (v, i, c) in enumerate(zip(values, indices, counts)):
        x_filtered[idx] = v
        filtered_array[idx] = np.sum(sorted_a[i:(i+c)], axis = 0)

    return x_filtered, filtered_array


def broaden(
x,
y,
sigma,
gamma,
e_min,
e_max,
steps = 2000
):
    """ Broaden an array of transitions with a voigt function """

    new_x = np.linspace(e_min, e_max, steps)
    new_y = np.zeros(new_x.shape)
    for xs, ys in zip(x, y):
        new_y += scipy.special.voigt_profile(new_x-xs, sigma, gamma) * ys
    return new_x, new_y

buffer_size = 1500 # Anticipate up to *buffer_size* MOs
atoms = ['Co', 'O', 'N', 'C', 'H']
orbitals = ['s', 'px', 'py', 'pz', 'dxz', 'dxy', 'dyz', 'dz2', 'dx2y2']
orbitals_simple = ['s', 'p', 'd']
states = ['a', 'b']
mos = np.zeros((buffer_size, len(states), len(atoms), len(orbitals)))

pattern = r'^\s*\d+\s([CNOHo]{1,2})\s+([spdxyz2]{1,5})\s+(\d+\.\d)\s*(\d+\.\d)?\s*(\d+\.\d)?\s*(\d+\.\d)?\s*(\d+\.\d)?\s*(\d+\.\d)?$|^\s{12,}(\d{1,4}\s)(\s+\d{1,4})?(\s+\d{1,4})?(\s+\d{1,4})?(\s+\d{1,4})?(\s+\d{1,4})?\s*$'

####################################################################################################
#                   Populate MO array
####################################################################################################

# Populate the *mos* array
with open(file_mos, 'r') as f:
    for l in f.readlines():

        if "SPIN UP" in l:
            state = 0
        elif "SPIN DOWN" in l:
            state = 1

        m = re.match(pattern, l)

        if m:

            try:

                no = [int(g) for g in m.groups()[8:] if g != None]

                if len(no) == 0:
                    raise Exception("No orbital numbers found")

                orbno = no
                continue

            except Exception as e:
                pass

            atom, orb, *contr = m.groups()[:8]
            contr = [float(v) for v in contr if v != None]

            for c, orb_number in zip(contr, orbno):
                mos[orb_number-1, state, atoms.index(atom), orbitals.index(orb)] += c


# Group orbitals by shell (e.g. px, py, pz -> p)
mos = np.array([mos[:, :, :, s].sum(axis = 3) for s in [slice(0,1), slice(1,4), slice(4,9)] ])
mos = np.moveaxis(mos, 0, -1)

pattern = r'^\s+(\d+)\s+(\d+)([a,b]{1})(?=\s->\s{4}0)\s->\s+\d+[a,b]{1}\s+(\d+\.\d+)\s+(\d+\.\d+).*\d+\.\d+.*\d+\.\d+.*\d+\.\d+$'


####################################################################################################
#                   Populate transition array
####################################################################################################

buffer_size = 2000 # Anticipate up to *buffer_size* transitions
transitions = np.zeros((buffer_size, mos.shape[2], mos.shape[3]))
energies = np.zeros(buffer_size)

with open(file_transitions, 'r') as f:
    for l in f.readlines():
        m = re.match(pattern, l)
        if m:
            transition_no, orb, state, energy, intensity = m.groups()
            if state == 'a':
                state = 0
            elif state == 'b':
                state = 1

            total_int = float(intensity)
            energies[int(transition_no)-1] = float(energy)
            intensites = [[orbital*total_int for orbital in atom] for atom in mos[int(orb), state]]
            transitions[int(transition_no)-1] = intensites


energies, transitions = filter_spectra(energies, transitions)
bx, by = broaden(energies, transitions.sum(axis = (1,2)), 0, 2.00, 7620, 7665)

####################################################################################################
#                   PLOTTING
####################################################################################################

fig, axs = plt.subplots()
plt.xlim([7632, 7665])
axs.plot(bx_plot, by_plot/115, 'k')

y_offset = np.zeros(energies.shape)

colorlist = ['orangered', 'black', 'mediumblue', 'grey', 'springgreen']
colorcounter = 0

for atom in ['Co', 'O', 'N', 'C']:
    for orbital in orbitals_simple:
        if atom == 'Co' and orbital == 's':
            continue
        elif atom == 'Co' and orbital == 'p':
            continue
        elif atom == 'O' and orbital == 'd':
            continue
        elif atom == 'N':
            continue
        elif atom == 'C' and orbital == 'd':
            continue
        else: 
            axs.bar(energies, transitions[:, atoms.index(atom), orbitals_simple.index(orbital)],
                    bottom=y_offset, alpha = 1, label = '{}_{}'.format(atom, orbital), color = colorlist[colorcounter])
            y_offset += transitions[:, atoms.index(atom), orbitals_simple.index(orbital)]
            colorcounter += 1
axs.set_ylim([0, 0.4])
axs.legend(loc='upper left')
fig.tight_layout()
plt.subplots_adjust(wspace=0, hspace=0)
plt.show()
