import fire

from typing import Dict, List
import time
from pathlib import Path

from ..interfaces import *
from ..fs import PanDDAFS
from ..dataset import XRayDataset
from ..dmaps import DMap, SparseDMap, SparseDMapStream, TruncateReflections, SmoothReflections
from ..alignment import Alignment, DFrame


def test_sparse_dmap_stream(data_dir, out_dir):
    print(f"Data dir is {data_dir} and output dir is {out_dir}")

    # Parse the FS
    fs: PanDDAFSInterface = PanDDAFS(Path(data_dir), Path(out_dir))

    # Get the datasets
    datasets: Dict[str, DatasetInterface] = {
        dataset_dir.dtag: XRayDataset(
            dataset_dir.input_pdb_file,
            dataset_dir.input_mtz_file,
            dataset_dir.ligand_files,
        )
        for dataset_dir
        in fs.input.dataset_dirs.values()
    }
    print(f"Got {len(datasets)} datasets")

    # Get the test dataset
    dtag = list(datasets.keys())[0]
    dataset = datasets[dtag]
    print(f"Test dataset is {dtag}")

    # Get the alignments
    alignments: Dict[str, Alignment] = {_dtag: Alignment(datasets[_dtag], dataset) for _dtag in datasets}
    print(f"Got {len(alignments)} alignments")

    # Get the reference frame
    reference_frame: DFrame = DFrame(dataset)

    # Get the dmaps
    dmaps: SparseDMapStream = SparseDMapStream(
        datasets,
        reference_frame,
        alignments,
        [
            TruncateReflections(
                datasets,
                dataset.reflections.resolution,
            ),
            SmoothReflections(dataset)
        ],
    )

    # Load
    time_begin = time.time()
    dmaps_sparse: Dict[str, SparseDMap] = {
        dtag: dmap_sparse
        for dtag, dmap_sparse
        in dmaps.parallel_load(processor)
    }
    time_finish = time.time()

if __name__ == "__main__":
    fire.Fire(test_sparse_dmap_stream)