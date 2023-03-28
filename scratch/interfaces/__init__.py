from typing import *
from typing_extensions import ParamSpec, Concatenate, Self
from pathlib import Path

class LigandFilesInterface(Protocol):
    ligand_cif: Path
    ligand_smiles : Path
    ligand_pdb : Path


class DatasetDirInterface(Protocol):
    dtag: str
    input_pdb_file: Path
    input_mtz_file: Path
    ligand_files: Dict[str, LigandFilesInterface]


class PanDDAInputInterface(Protocol):
    dataset_dirs: Dict[str, DatasetDirInterface]


class PanDDAFSInterface(Protocol):
    input: PanDDAInputInterface


class StructureFactorsInterface(Protocol):
    f: str
    phi: str


class StructureInterface(Protocol):
    def protein_atoms(self):
        ...

    def protein_residue_ids(self):
        ...

    def __getitem__(self, item):
        ...


class ResolutionInterface(Protocol):
    ...


class ReflectionsInterface(Protocol):
    path: Path
    reflections: Any

    def get_resolution(self) -> float:
        ...

    def transform_f_phi_to_map(self, f: str, phi: str, sample_rate: float) -> CrystallographicGridInterface:
        ...


class DatasetInterface(Protocol):
    structure: StructureInterface
    reflections: ReflectionsInterface
    smoothing_factor: float
