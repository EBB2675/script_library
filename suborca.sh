#!/usr/bin/python
#make sure to check what to copy back from scrdir

import os
import argparse
import subprocess

def main():

    parser = argparse.ArgumentParser('Submit ORCA calcs')
    parser.add_argument('--version', '-v', choices=['421', '504'],
                        default='504', help='ORCA version')
    parser.add_argument('files', nargs='*', help='Input files')
    args = parser.parse_args()

    sh_template = """#!/bin/bash
#
#PBS -N %(basename)s
#PBS -j eo
#PBS -r n
#PBS -l nodes=%(nprocs)i

JOBNAME=%(basename)s
module load ORCA.%(version)s
cd $PBS_O_WORKDIR
export RUNID=`echo ${PBS_JOBID} | sed -e "s/.rigi//"`
export SCRATCHDIR=/scratch/${USER}/${RUNID}
mkdir -p ${SCRATCHDIR}
cp ${PBS_O_WORKDIR}/*.gbw ${SCRATCHDIR}
cp ${PBS_O_WORKDIR}/*.qro ${SCRATCHDIR}
cp ${PBS_O_WORKDIR}/*.loc ${SCRATCHDIR}
cp ${PBS_O_WORKDIR}/${JOBNAME}* ${SCRATCHDIR}
cd ${SCRATCHDIR}

${ORCAPATH}/orca ${JOBNAME}.inp > ${PBS_O_WORKDIR}/${JOBNAME}.out 2>&1

rm -rf ${SCRATCHDIR}/*.tmp
rm -rf ${SCRATCHDIR}/*.tmp.*
cp ${SCRATCHDIR}/*.gbw ${PBS_O_WORKDIR}
cp ${SCRATCHDIR}/*.qro ${PBS_O_WORKDIR}
cp ${SCRATCHDIR}/*.uco ${PBS_O_WORKDIR}
cp ${SCRATCHDIR}/*.uno ${PBS_O_WORKDIR}
cp ${SCRATCHDIR}/*.loc ${PBS_O_WORKDIR}
cp ${SCRATCHDIR}/*.hess ${PBS_O_WORKDIR}
cp ${SCRATCHDIR}/*rixs* ${PBS_O_WORKDIR}
cp ${SCRATCHDIR}/*xyz ${PBS_O_WORKDIR}
cp ${SCRATCHDIR}/*cis ${PBS_O_WORKDIR}
cp ${SCRATCHDIR}/*lft* ${PBS_O_WORKDIR}
cp ${SCRATCHDIR}/*nto ${PBS_O_WORKDIR}
rm -rf ${SCRATCHDIR}
cd ${CURRENTDIR}


"""

    for infile in args.files:
        splitext = os.path.splitext(infile)[0]
        basename = os.path.basename(splitext)
        shfile = splitext + '.sh'
        for line in open(infile):
            if 'nprocs' in line.lower():
                nprocs = int(line.split(' ')[1])
                break
        else:
            raise(Exception('Number of processors not defined.'))
        sh = sh_template % {
            'basename': basename,
            'nprocs': nprocs,
            'version': args.version,
            'infile': infile,
        }
        f = open(shfile, 'w')
        f.write(sh)
        f.close()
        print('%s written.' % shfile)
        process = subprocess.Popen(['qsub %s' % shfile], shell=True)
        process.wait()


if __name__ == '__main__':
    main()
