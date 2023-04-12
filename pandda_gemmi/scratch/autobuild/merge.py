import gemmi

from .. import constants
from ..interfaces import *


def get_pdb(pdb_file: Path):
    structure: gemmi.Structure = gemmi.read_structure(str(pdb_file))
    return structure


def merge_build(dataset, selected_build_path, path):
    receptor = get_pdb(dataset.structure.path)
    ligand = get_pdb(selected_build_path)

    for receptor_model in receptor:
        for receptor_chain in receptor_model:

            seqid_nums = []
            for receptor_res in receptor_chain:
                num = receptor_res.seqid.num
                seqid_nums.append(num)

            if len(seqid_nums) == 0:
                min_ligand_seqid = 1
            else:
                min_ligand_seqid = max(seqid_nums) + 1

            for model in ligand:
                for chain in model:
                    for residue in chain:
                        residue.seqid.num = min_ligand_seqid

                        receptor_chain.add_residue(residue, pos=-1)

            break
        break

    receptor.write_minimal_pdb(str(path))


def merge_autobuilds(datasets, autobuilds, fs: PanDDAFSInterface, build_selection_method):
    all_dtags = list(set([event_id[0] for event_id in autobuilds]))

    for dtag in all_dtags:
        dataset = datasets[dtag]
        dtag_events = [event_id for event_id in autobuilds if event_id[0] == dtag]
        selected_build_path = build_selection_method(dtag_events)
        model_building_dir = fs.output.processed_datasets[dtag] / constants.PANDDA_MODELLED_STRUCTURES_DIR
        merge_build(
            dataset,
            selected_build_path,
            model_building_dir / constants.PANDDA_EVENT_MODEL.format(dtag=dtag),
        )


class MergeHighestRSCC:
    ...
