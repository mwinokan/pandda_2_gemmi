import gemmi

from ..interfaces import *


class FilterCompatibleStructures:
    def __init__(self, dataset, similarity=100.0):
        self.dataset = dataset
        self.similarity = similarity

    def get_compatible(self, dataset):
        ref_ents = self.dataset.structure.structure.entities
        # ref_mod_sequence = ref_mod.full_sequence

        mov_ents = dataset.structure.structre.entities
        mov_ent_names = [ent.name for ent in mov_ents]

        for ref_ent in ref_ents:
            if ref_ent.name not in mov_ent_names:
                return False
            else:
                ref_seq = [gemmi.Entity.first_mon(item) for item in ref_ent.full_sequence]
                mov_seq = [gemmi.Entity.first_mon(item) for item in dataset.structure.structre.get_entity(ref_ent.name).full_sequence]
                result = gemmi.gemmi.align_string_sequences(
                    ref_seq,
                    mov_seq,
                    [], gemmi.blosum62,
                )

                if not result.calculate_identity() >= self.similarity:
                    return False

        return True

    def __call__(self, datasets: Dict[str, DatasetInterface]):
        new_datasets = {}
        for _dtag in datasets:
            dataset = datasets[_dtag]
            if self.get_compatible(dataset):
                new_datasets[_dtag] = dataset

        return new_datasets
