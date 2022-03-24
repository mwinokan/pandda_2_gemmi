from __future__ import annotations

import dataclasses

import numpy as np
import scipy

from pandda_gemmi.analyse_interface import *
from pandda_gemmi.dataset import Reference, Datasets
from pandda_gemmi.edalignment import Alignment


@dataclasses.dataclass()
class RMSD:
    rmsd: float

    @staticmethod
    def from_reference(reference: Reference, dataset: DatasetInterface):
        return RMSD.from_structures(
            reference.dataset.structure,
            dataset.structure,

        )

    @staticmethod
    def from_structures(structure_1: StructureInterface, structure_2: StructureInterface, ) -> RMSD:

        distances = []

        positions_1 = []
        positions_2 = []

        # for residues_id in structure_1.protein_residue_ids():
        for residues_id in structure_1.protein_residue_ids():

            res_1 = structure_1[residues_id][0]
            try:
                res_2 = structure_2[residues_id][0]
            except:
                continue

            # print(f"Residue 1 is: {res_1}")
            # print(f"Residue 2 is: {res_2}")
            try:
                res_1_ca = res_1["CA"][0]
            except Exception as e:
                continue

            try:
                res_2_ca = res_2["CA"][0]
            except Exception as e:
                continue

            res_1_ca_pos = res_1_ca.pos
            res_2_ca_pos = res_2_ca.pos

            positions_1.append(res_1_ca_pos)
            positions_2.append(res_2_ca_pos)

            distances.append(res_1_ca_pos.dist(res_2_ca_pos))

        positions_1_array = np.array([[x[0], x[1], x[2]] for x in positions_1])
        positions_2_array = np.array([[x[0], x[1], x[2]] for x in positions_2])

        if positions_1_array.size < 3:
            return RMSD(100.0)
        if positions_2_array.size < 3:
            return RMSD(100.0)

        return RMSD.from_arrays(positions_1_array, positions_2_array)

    @staticmethod
    def from_arrays(array_1, array_2):

        array_1_mean = np.mean(array_1, axis=0).reshape((1, 3))
        array_2_mean = np.mean(array_2, axis=0).reshape((1, 3))

        array_1_demeaned = array_1 - array_1_mean
        array_2_demeaned = array_2 - array_2_mean
        #

        rotation, rmsd = scipy.spatial.transform.Rotation.align_vectors(array_1_demeaned, array_2_demeaned)
        rotated_vecs = rotation.apply(array_2_demeaned)

        #
        true_rmsd = np.sqrt(
            np.sum(np.square(np.linalg.norm(array_1_demeaned - rotated_vecs, axis=1)), axis=0) / array_1.shape[0])

        return RMSD(true_rmsd)

    def to_float(self):
        return self.rmsd


class FilterNoStructureFactors(FilterNoStructureFactorsInterface):
    def __init__(self):
        ...

    def __call__(self,
                 datasets: DatasetsInterface,
                 structure_factors: StructureFactorsInterface,
                 ) -> Datasets:
        new_dtags = filter(
            lambda dtag: (structure_factors.f in datasets[dtag].reflections.columns()) and (
                    structure_factors.phi in datasets[dtag].reflections.columns()),
            datasets,
        )

        new_datasets = {dtag: datasets[dtag] for dtag in new_dtags}

        return Datasets(new_datasets)


class FilterResolutionDatasets(FilterResolutionDatasetsInterface):
    def __init__(self, resolution_cutoff: float):
        self.resolution_cutoff = resolution_cutoff

    def __call__(self, datasets: DatasetsInterface, ):
        high_resolution_dtags = filter(
            lambda dtag: datasets[dtag].reflections.resolution().to_float() < self.resolution_cutoff,
            datasets,
        )

        new_datasets = {dtag: datasets[dtag] for dtag in high_resolution_dtags}

        return Datasets(new_datasets)


class FilterRFree(FilterRFreeInterface):
    def __init__(self, max_rfree: float):
        self.max_rfree = max_rfree

    def __call__(self, datasets: DatasetsInterface, ):
        good_rfree_dtags = filter(
            lambda dtag: datasets[dtag].structure.rfree().to_float() < self.max_rfree,
            datasets,
        )

        new_datasets = {dtag: datasets[dtag] for dtag in good_rfree_dtags}

        return Datasets(new_datasets)


class FilterDataQuality(FilterDataQualityInterface):
    def __init__(self, filters: List[FilterDataQualityInterface]):
        self.filters = filters


    def __call__(self, datasets: DatasetsInterface) -> DatasetsInterface:
        for filter in self.filters:
            new_datasets = filter(datasets,)




class FilterDissimilarModels(FilterDissimilarModelsInterface):
    def __init__(self, max_rmsd_to_reference: float):
        self.max_rmsd_to_reference = max_rmsd_to_reference

    def __call__(self, datasets: DatasetsInterface, reference: Reference, ) -> Datasets:
        new_dtags = filter(lambda dtag: (RMSD.from_reference(
            reference,
            datasets[dtag],
        )).to_float() < self.max_rmsd_to_reference,
                           datasets,
                           )

        new_datasets = {dtag: datasets[dtag] for dtag in new_dtags}

        return Datasets(new_datasets)


class FilterIncompleteModels(FilterIncompleteModelsInterface):
    def __call__(self, datasets: DatasetsInterface, reference: Reference):
        new_dtags = filter(lambda dtag: Alignment.has_large_gap(reference, datasets.datasets[dtag]),
                           datasets.datasets,
                           )

        new_datasets = {dtag: datasets.datasets[dtag] for dtag in new_dtags}

        return Datasets(new_datasets)


class FilterDifferentSpacegroups(FilterDifferentSpacegroupsInterface):
    def __call__(self,
                 datasets: DatasetsInterface,
                 reference: Reference):
        same_spacegroup_datasets = filter(
            lambda dtag: datasets[dtag].reflections.spacegroup() == reference.dataset.reflections.spacegroup(),
            datasets,
        )

        new_datasets = {dtag: datasets[dtag] for dtag in same_spacegroup_datasets}

        return Datasets(new_datasets)


class FilterReferenceCompatibility(FilterReferenceCompatibilityInterface):
    def __init__(self):
        ...

    def __call__(self, datasets: DatasetsInterface, reference: ReferenceInterface) -> DatasetsInterface:
        ...
