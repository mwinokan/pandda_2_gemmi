import re
from pathlib import Path

from .. import constants


def get_input_pdb_file(path, pdb_regex):
    input_pdb_files = [pdb_path for pdb_path in path.glob(pdb_regex)]
    if len(input_pdb_files) == 0:
        input_pdb_file = None
    else:
        input_pdb_file: Path = input_pdb_files[0]
    return input_pdb_file


def get_input_mtz_file(path, mtz_regex):
    input_mtz_files = [mtz_path for mtz_path in path.glob(mtz_regex)]
    if len(input_mtz_files) == 0:
        input_mtz_file = None
    else:
        input_mtz_file: Path = input_mtz_files[0]
    return input_mtz_file


class LigandFiles:
    def __init__(self, ligand_cif, ligand_smiles, ligand_pdb):
        self.ligand_cif = ligand_cif
        self.ligand_smiles = ligand_smiles
        self.ligand_pdb = ligand_pdb


def parse_dir_ligands(path: Path, ligand_cif_regex, ligand_smiles_regex, ligand_pdb_regex, ):
    ligand_keys = {}
    for file_path in path.glob("*"):
        name = file_path.name
        stem = file_path.stem
        if re.match(ligand_cif_regex, name):
            if stem in ligand_keys:
                ligand_keys[stem].ligand_cif = file_path
            else:
                ligand_keys[stem] = LigandFiles(file_path, None, None)

        elif re.match(ligand_smiles_regex, name):
            if stem in ligand_keys:
                ligand_keys[stem].ligand_smiles = file_path
            else:
                ligand_keys[stem] = LigandFiles(None, file_path, None)
        elif re.match(ligand_pdb_regex, name):
            if stem in ligand_keys:
                ligand_keys[stem].ligand_pdb = file_path
            else:
                ligand_keys[stem] = LigandFiles(None, None, file_path)

        else:
            continue

    return ligand_keys


def get_input_ligands(path: Path, ligand_dir_regex, ligand_cif_regex, ligand_smiles_regex, ligand_pdb_regex, ):
    path_ligands = parse_dir_ligands(path, ligand_cif_regex, ligand_smiles_regex, ligand_pdb_regex, )
    for ligand_dir_path in path.glob("*"):
        if re.match(ligand_dir_regex, path.name):
            ligand_dir_ligands = parse_dir_ligands(
                ligand_dir_path,
                ligand_cif_regex,
                ligand_smiles_regex,
                ligand_pdb_regex,
            )
            path_ligands.update(ligand_dir_ligands)

    return path_ligands


class DatasetDir:
    def __init__(
            self,
            path: Path,
            pdb_regex: str = constants.ARGS_PDB_REGEX_DEFAULT,
            mtz_regex: str = constants.ARGS_MTZ_REGEX_DEFAULT,
            ligand_dir_regex: str = constants.ARGS_LIGAND_DIR_REGEX_DEFAULT,
            ligand_cif_regex: str = constants.ARGS_LIGAND_CIF_REGEX_DEFAULT,
            ligand_smiles_regex: str = constants.ARGS_LIGAND_SMILES_REGEX_DEFAULT,
            ligand_pdb_regex: str = constants.ARGS_LIGAND_PDB_REGEX_DEFAULT,
    ):
        # Get the dtag
        self.dtag = path.name

        # Get pdb
        self.input_pdb_file = get_input_pdb_file(path, pdb_regex)

        # Get mtz
        self.input_mtz_file = get_input_mtz_file(path, mtz_regex)

        # Get the ligands
        self.input_ligands = get_input_ligands(
            path,
            ligand_dir_regex,
            ligand_cif_regex,
            ligand_smiles_regex,
            ligand_pdb_regex,
        )


class PanDDAInput:
    def __init__(
            self,
            input_dir: Path,
            pdb_regex: str = constants.ARGS_PDB_REGEX_DEFAULT,
            mtz_regex: str = constants.ARGS_MTZ_REGEX_DEFAULT,
            ligand_dir_regex: str = constants.ARGS_LIGAND_DIR_REGEX_DEFAULT,
            ligand_cif_regex: str = constants.ARGS_LIGAND_CIF_REGEX_DEFAULT,
            ligand_smiles_regex: str = constants.ARGS_LIGAND_SMILES_REGEX_DEFAULT,
            ligand_pdb_regex: str = constants.ARGS_LIGAND_PDB_REGEX_DEFAULT,
    ):
        self.input_dir = input_dir
        self.dataset_dirs = {
            dataset_dir.dtag: dataset_dir
            for dataset_dir
            in [
                DatasetDir(
                    path,
                    pdb_regex,
                    mtz_regex,
                    ligand_dir_regex,
                    ligand_cif_regex,
                    ligand_smiles_regex,
                    ligand_pdb_regex,
                )
                for path in input_dir.glob("*")
            ]
            if (dataset_dir.input_pdb_file and dataset_dir.input_mtz_file)
        }

    def apply(self):
        ...

    def load_datasets(self):
        ...