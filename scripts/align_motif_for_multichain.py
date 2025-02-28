#!/software/conda/envs/pyrosetta/bin/python
# 
# Aligns hallucination models to the template structure so it can be used in
# downstream multichain hallucination.
#
# Usage:
#
#     ./align_motif_for_multichain.py FOLDER
#
# Updated 2021-9-1

import pandas as pd
import numpy as np
import sys, os, argparse, glob
from collections import OrderedDict

import pyrosetta
pyrosetta.init('-mute all')

p = argparse.ArgumentParser()
p.add_argument('data_dir', help='Folder of TrDesign outputs to process')
p.add_argument('-r','--receptor', required=True, help='Receptor (natural binding target) structure (.pdb)')
p.add_argument('-t','--template', help='Template (natural binder) structure (.pdb)')
p.add_argument('-o','--out_dir', default='aligned_to_rec/', help='Output folder for aligned binder.')
p.add_argument('--complex_out_dir', default='raw_complex/', help='Output folder for complex.')
p.add_argument('--trb_dir', help='Folder containing .trb files (if not same as pdb folder)')
p.add_argument('--out_suffix', default='', help='Suffix for output files')
args = p.parse_args()

def main():

    atoms = ['N', 'CA', 'C']

    if args.template is not None:
        pose_ref_clean = pyrosetta.pose_from_file(args.template)

    if args.trb_dir is not None: trb_dir = args.trb_dir
    else: trb_dir = args.data_dir

    os.makedirs(args.out_dir,exist_ok=True)
    if args.receptor is not None:
        os.makedirs(args.complex_out_dir,exist_ok=True)

    records = []
    last_template = None
    for fn in glob.glob(os.path.join(args.data_dir,'*.pdb')):
        name = os.path.basename(fn).replace('.pdb','')
        print(name)

        outname = os.path.join(args.out_dir, name + args.out_suffix+'.pdb')
        if os.path.exists(outname):
            sys.exit(f'ERROR: Output file {outname} already exists. Choose a different '\
                       'out_dir or out_suffix, or delete existing files.')

        trbname = os.path.join(trb_dir, os.path.basename(fn.replace(args.out_suffix+'.pdb','.trb')))
        if not os.path.exists(trbname): 
            sys.exit(f'ERROR: {trbname} does not exist. Set the --trb_dir argument if your .trb files '\
                      'are in a different folder from the .pdb files.')
        trb = np.load(trbname,allow_pickle=True)

        if args.template is None and 'settings' in trb and trb['settings']['pdb'] != last_template:
            pose_ref_clean = pyrosetta.pose_from_file(trb['settings']['pdb'])
            last_template = trb['settings']['pdb']

        pose_ref = pose_ref_clean.clone()
        pose_hal = pyrosetta.pose_from_file(fn)

        ref_to_hal = dict(zip(trb['con_ref_pdb_idx'], trb['con_hal_pdb_idx']))

        # Make alignment maps
        align_map = pyrosetta.rosetta.std.map_core_id_AtomID_core_id_AtomID()
        for idx_ref in trb['con_ref_pdb_idx']:
            idx_hal = ref_to_hal[idx_ref]

            # Find equivalent residues in both structures
            pose_idx_ref = pose_ref.pdb_info().pdb2pose(*idx_ref)
            pose_idx_hal = pose_hal.pdb_info().pdb2pose(*idx_hal)

            res_hal = pose_hal.residue(pose_idx_hal)
            res_ref = pose_ref.residue(pose_idx_ref)

            # fill out alignment map
            for atom in atoms:
                atom_index = res_hal.atom_index(atom)  # this is the same number for either residue
                atom_id_ref = pyrosetta.rosetta.core.id.AtomID(atom_index, pose_idx_ref)
                atom_id_hal = pyrosetta.rosetta.core.id.AtomID(atom_index, pose_idx_hal)
                align_map[atom_id_hal] = atom_id_ref

        # Align and update metrics
        rmsd = pyrosetta.rosetta.core.scoring.superimpose_pose(pose_hal, pose_ref, align_map)
        pose_hal.dump_pdb(outname)

        pose_rec = pyrosetta.pose_from_file(args.receptor)
        for i in range(1, pose_rec.total_residue()+1):
            pose_rec.pdb_info().chain(i, 'B')
            pose_rec.pdb_info().number(i, i)
        pose_hal.append_pose_by_jump(pose_rec, 1 )

        outname_rec = os.path.join(args.complex_out_dir, name + args.out_suffix+'.pdb')
        # reset conf info (maybe necessary to deal with disulfides)
        conf = pose_hal.conformation()
        pose_hal.set_new_conformation(conf)
        pose_hal.dump_pdb(outname_rec)

if __name__ == "__main__":
    main()
