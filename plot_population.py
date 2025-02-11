#!/usr/bin/env python
# coding: utf-8
# plot the orbital compositions casscf
# written by Nico Spiller ( spiller@kofo.mpg.de )

import numpy as np
import matplotlib
import matplotlib.pyplot as plt

import re

##########
## loewdin orbital comp
def get_loewdin_block(output, mode='UHF'):
    '''
    searches for the block with the loewdin orbital compositions
    
    outputfile          outputfile to be processed
    mode
        CASSCF          'LOEWDIN ORBITAL-COMPOSITIONS'
        UHF              'LOEWDIN REDUCED ORBITAL POPULATIONS PER MO'
                        spin up only (bc easier to implement)
        UNO              'LOEWDIN REDUCED ORBITAL POPULATIONS PER UNO'

    return a list of lists containing the block from the file
    '''

    
    if mode == 'CASSCF':
        pattern = 'LOEWDIN ORBITAL-COMPOSITIONS'
    elif mode == 'UHF':
        pattern = 'LOEWDIN REDUCED ORBITAL POPULATIONS PER MO'
    elif mode == 'UNO':
        pattern = 'LOEWDIN REDUCED ORBITAL POPULATIONS PER UNO'

    empty_line = re.compile('^\s*$')
    dashes = re.compile('----------------------------')

    block_loewdin = [] # empty 
    empty_line_counter = 0

    with open(output) as f:
        switch_loewdin = False
        for line in f:
            if pattern in line:
                switch_loewdin = True
                empty_line_counter = 0
                next(f)
                continue
            if empty_line.match(line) and empty_line_counter == 1 or dashes.match(line):
                switch_loewdin = False
                continue
            else:
                empty_line_counter = 0
            if empty_line.match(line):
                empty_line_counter += 1
            if switch_loewdin == True:
                line = line.split()
                block_loewdin.append(line)
    # make structure of block same for UHF
    if mode == 'UHF':
        block_loewdin.pop(0)
        block_loewdin[0] = []
    if mode == 'UNO':
        block_loewdin[0] = []

    return block_loewdin

def get_empty_lists(list_of_lists):
    '''
    takes a list of list as argument
    return a list containing the positions of empty lists ([], i.e. empty lines in the former file)
    '''
    indices = [ i for i, line in enumerate(list_of_lists) if line == [] ]
    return indices

class loew_orb:
    '''
    Store information about the loewdin orbital composition for an MO:
        number
        energy
        occupation
        contribution from AO
    '''
    def __init__(self):
        self.n = None # orbital number
        self.e = None # energy
        self.occ = None # occupation
        self.contr = {} # dictionary of contribution in % per atom: 
                        # {3dz2: 75.3, … } means that atom 3 has 75.3 % contribution from orb dz2 to orbital self.

def get_loewdin(outputfile, sum_aos=['\b*'], mode='UHF'):
    '''
    takes an output file as argument which contains the 'LOEWDIN ORBITAL-COMPOSITIONS' block
    with sum_ao orbitals can be defined for which the contributions are summarized (e.g. ['d', 'p'])

    mode
        CASSCF          CASSCF calculation
        UHF             UHF calculation
        UNO             UNO

    returns a list of molecular orbitals and a set containing the basis for the contributions
    '''
    block_loewdin = get_loewdin_block(outputfile, mode=mode)
    newline_indices = get_empty_lists(block_loewdin)
    newline_indices.pop() # make this work for last block TODO: last index

    orbs = [] # list of loew_orb objects, one for each MO
    ao_basis = set() # set of possible atom-AO combinations, basis for plotting later


    for c in range(len(newline_indices) - 1): # cycle through all block separated by empty lines (= []) TODO: last index
        i = newline_indices[c] # beginning position in block_loewdin
        nexti = newline_indices[c+1] # end position in block_loewdin

        block_contr = [] # write contributions between i and nexti here (excluding headers)
        for line in block_loewdin[i+5:nexti]:
            block_contr.append(line)

        for n, e, occ in zip(block_loewdin[i+1], block_loewdin[i+2], block_loewdin[i+3]): # cycle thgough header
            orb = loew_orb()
            orb.n = int(n)
            orb.e = float(e)
            orb.occ = float(occ)
            for line in block_contr: # cycle through contribution block
                contr_line = line[3:] # strip first three entries: number, atom, orbital
                pos = orb.n % 6 # maximum number of 6 columns
                key = str(line[0]) + str(line[2]) # compose key for orb.contr from number and orbtital
                ao_basis.add(key)
                orb.contr[key] = float(contr_line[pos]) # make entry in dictionary
            orbs.append(orb)

    # sum up contributions in new dicts
    regex_sum = '(?P<summed_key>\d*['
    for n in sum_aos:
        r = str(n) + ','
        regex_sum += r
    regex_sum += '])'
    regex_sum = re.compile(regex_sum)


    ao_basis_summed = set()
    for orb in orbs:
        orbs_summed = {}
        for i in orb.contr:
            if regex_sum.search(i):
                m = regex_sum.search(i)
                sum_key = m.groupdict()['summed_key']
                try:
                    orbs_summed[sum_key] += orb.contr[i]
                except KeyError:
                    orbs_summed[sum_key] = orb.contr[i]
                ao_basis_summed.add(sum_key)
            else:
                orbs_summed[i] = orb.contr[i]
                ao_basis_summed.add(i)
        orb.contr = orbs_summed

    ao_basis = ao_basis_summed

    ao_basis = sorted(ao_basis)
    return orbs, ao_basis


def loewdin_heatmap(ax, outputfile, firstMO, lastMO, atomlist=['\d*'], AOlist=['\w*'], sumAOlist=['\b*'], mode='UHF', colorbar=True, annotations=True):
    '''
    plot the LOEWDIN ORBITAL-COMPOSITION from an outputfile (requires ! normalprint) as a heatmap
    arguments:
        ax            axis to be modified in a matplotlib figure
        outputfile    output file of the orca calculation
        firstMO       first molecular orbital to be plotted
        lastMO        last molecular orbital to be plotted
        atomlist      include list of atom indices as used by the calculation, starts with 0
                      e.g. [0,3,4] for plotting contributions from atom number 0, 3 and 4
        AOlist        list of strings to be matched against the atomic orbital (used as regex)
                      e.g. ['d', 'pz'] to plot contributions from all d orbitals and the pz orbital
        sumAOlist     sum contribution from the manifold
                      e.g. ['p', 'd'] summarizes px, py and pz in p and dx2y2, dz2, dxy, dxz, dyz in d
        mode          regard different printing patterns in output file
            CASSCF    CASSCF calculation
            UHF       UHF calculation 
            UNO       UNO
        colorbar      True or False, display the colorbar (legend)
        annotations   True or False, plot number (as integer) as well
    '''

    # compile regex from list of atoms
    regex_atom = r'^('
    for n in atomlist:
        r = str(n) + r'|'
        regex_atom += r
    regex_atom = regex_atom.rstrip(r'|')
    regex_atom += r')[a-z]'
    # and for orbitals
    regex_aos = r'^[0-9]+['
    for n in AOlist:
        r = str(n) + r','
        regex_aos += r
    regex_aos += r']'

    # get list of mo classes and basis
    orbs, aos = get_loewdin(outputfile, sum_aos=sumAOlist, mode=mode)

    # reduce according to limits
    aos = [ i for i in aos if re.match(regex_atom, i) and re.match(regex_aos, i)]
    orbs = orbs[firstMO:lastMO+1]

    contr = []
    for mo in orbs:
        c = []
        for ao in aos:
            try:
                c.append(mo.contr[ao])
            except KeyError:
                c.append(0)
        contr.append(c)

    contr = np.array(contr)
    contr = contr.T


    im = ax.imshow(contr, cmap="cool")

    # We want to show all ticks...
    ax.set_xticks(np.arange(len(orbs)))
    ax.set_yticks(np.arange(len(aos)))
    # ... and label them with the respective list entries
    ax.set_xticklabels([ orb.n for orb in orbs ])
    ax.set_yticklabels(aos)

    # Rotate the tick labels and set their alignment.
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right",
             rotation_mode="anchor")

    # Create colorbar
    if colorbar == True:
        cbar = ax.figure.colorbar(im, ax=ax)
        cbar.ax.set_ylabel('composition %', rotation=-90, va="bottom")
    
    # write number in field as well
    if annotations == True:
        x, y = contr.shape
        for i in range(x):
            for j in range(y):
                n = np.round(contr[i, j], decimals=0)
                n = int(n)
                text = ax.text(j, i, n, ha='center', va='center', color='k')

    ax.set_title("Loewdin Orbital-Compositions")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'CASSCF_output', 
        help='outputfile from a CASSCF calculation (requires normalprint keyword)', )
    parser.add_argument(
        'plot_file',
        help='name of the file for the plot (e.g. test.pdf)')
    parser.add_argument('first_MO', 
        help='specify first molecular orbital',
        type=int)
    parser.add_argument('last_MO',
        help='specify last molecular orbital',
        type=int)
    parser.add_argument('-a', '--atom-list',
        default='\d+',
        help='index (starts with 0) for atom to be included (default: all); e.g.: 0,1,6',
        )
    parser.add_argument('-o', '--orbital-list',
        default='\w*',
        help='atomic orbitals to be plotted (default: all); e.g.: s,p,d',
        )
    parser.add_argument('-s', '--sum-orbitals',
        default='\b*',
        help='shells to be summed up for each atom before plotting (default: none); e.g.: s,p,d',
        )
    parser.add_argument('-d', '--dpi',
        default=100,
        help='quality of the plot in dpi (default: 100)',
        type=int)
    args = parser.parse_args()
    

    output = args.CASSCF_output
    plot = args.plot_file
    firstMO = args.first_MO
    lastMO = args.last_MO
    atomlist = args.atom_list
    orbitals = args.orbital_list
    sumorbs = args.sum_orbitals
    dpi = args.dpi

    fig, ax = plt.subplots(figsize=(20,20))
    loewdin_heatmap(
        ax, 
        output, 
        firstMO=firstMO, 
        lastMO=lastMO, 
        atomlist=atomlist.split(',') ,
        AOlist=orbitals.split(','),
        sumAOlist=sumorbs,
        colorbar=False)
    
    fig.savefig(plot, dpi=dpi)
