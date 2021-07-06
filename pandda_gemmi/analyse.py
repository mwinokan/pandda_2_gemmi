from __future__ import annotations

# Base python
import os
import traceback
from pandda_gemmi import constants
from pandda_gemmi.constants import PANDDA_LOG_FILE
from typing import Dict, Optional, List, Tuple, Union
import time
import psutil
import pickle
from shlex import split
from pprint import PrettyPrinter
from pathlib import Path
import pprint
from functools import partial
import multiprocessing as mp

printer = pprint.PrettyPrinter()

# Scientific python libraries
import fire
import numpy as np
import gemmi
import joblib

## Custom Imports
from pandda_gemmi.logs import summarise_grid, summarise_event, summarise_structure, summarise_mtz, summarise_array
from pandda_gemmi.pandda_types import (
    PanDDAFSModel, Dataset, Datasets, Reference, Resolution,
    Grid, Alignments, Shell, Xmap, Xmaps, Zmap,
    XmapArray, Model, Dtag, Zmaps, Clustering, Clusterings,
    Events, SiteTable, EventTable,
    StructureFactors, Xmap,
    DatasetResult, ShellResult,
)
from pandda_gemmi import constants
from pandda_gemmi.pandda_functions import (
    process_local_serial,
    process_local_joblib,
    process_local_multiprocessing,
    process_global_serial,
    get_shells,
    get_comparators_high_res_random,
    get_comparators_closest_cutoff,
    truncate,
    validate_strategy_num_datasets,
    validate,
)


# #########
# debug
# #########


def process_dataset(
        test_dtag,
        shell,
        dataset_truncated_datasets,
        alignments,
        dataset_xmaps,
        pandda_fs_model,
        reference,
        grid,
        contour_level,
        cluster_cutoff_distance_multiplier,
        min_blob_volume,
        min_blob_z_peak,
        structure_factors,
        outer_mask,
        inner_mask_symmetry,
        process_local=process_local_serial,

):
    dataset_log = {}
    dataset_log[constants.LOG_DATASET_TRAIN] = shell.train_dtags[test_dtag]

    masked_xmap_array = XmapArray.from_xmaps(
        dataset_xmaps,
        grid,
    )

    print(f"\t\tProcessing dtag: {test_dtag}: {shell.train_dtags[test_dtag]}")
    masked_train_xmap_array: XmapArray = masked_xmap_array.from_dtags(
        [_dtag for _dtag in shell.train_dtags[test_dtag].union({test_dtag, })])

    ###################################################################
    # # Generate the statistical model of the dataset
    ###################################################################

    # Determine the parameters of the model to find outlying electron density
    print("Fitting model")
    mean_array: np.ndarray = Model.mean_from_xmap_array(masked_train_xmap_array,
                                                        )  # Size of grid.partitioning.total_mask > 0
    dataset_log[constants.LOG_DATASET_MEAN] = summarise_array(mean_array)

    print("fitting sigma i")
    sigma_is: Dict[Dtag, float] = Model.sigma_is_from_xmap_array(masked_train_xmap_array,
                                                                 mean_array,
                                                                 1.5,
                                                                 )  # size of n
    dataset_log[constants.LOG_DATASET_SIGMA_I] = sigma_is

    print("fitting sigma s m")
    sigma_s_m: np.ndarray = Model.sigma_sms_from_xmaps(masked_train_xmap_array,
                                                       mean_array,
                                                       sigma_is,
                                                       )  # size of total_mask > 0
    dataset_log[constants.LOG_DATASET_SIGMA_S] = summarise_array(sigma_s_m)

    model: Model = Model.from_mean_is_sms(
        mean_array,
        sigma_is,
        sigma_s_m,
        grid,
    )

    # Calculate z maps
    print("Getting zmaps")
    zmaps: Dict[Dtag, Zmap] = Zmaps.from_xmaps(
        model=model,
        xmaps={test_dtag: dataset_xmaps[test_dtag], },
    )

    for dtag in zmaps:
        zmap = zmaps[dtag]
        pandda_fs_model.processed_datasets.processed_datasets[dtag].z_map_file.save(zmap)

        xmap = dataset_xmaps[dtag]
        path = pandda_fs_model.processed_datasets.processed_datasets[dtag].path / "xmap.ccp4"
        xmap.save(path)

        std_xmap = Xmap.from_grid_array(grid, sigma_s_m)
        path = pandda_fs_model.processed_datasets.processed_datasets[dtag].path / "std.ccp4"
        std_xmap.save(path)


    ###################################################################
    # # Cluster the outlying density
    ###################################################################
    # Get the clustered electron desnity outliers
    print("clusting")
    cluster_paramaterised = partial(
        Clustering.from_zmap,
        reference=reference,
        grid=grid,
        contour_level=contour_level,
        cluster_cutoff_distance_multiplier=cluster_cutoff_distance_multiplier,
    )

    clusterings = process_local(
        [
            partial(cluster_paramaterised, zmaps[dtag], )
            for dtag
            in zmaps
        ]
    )
    clusterings = Clusterings({dtag: clustering for dtag, clustering in zip(zmaps, clusterings)})
    print("\t\tIntially found clusters: {}".format(
        {
            dtag: (
                len(clustering),
                max([len(cluster.indexes[0]) for cluster in clustering.clustering.values()] + [0, ]),
                max([cluster.size(grid) for cluster in clustering.clustering.values()] + [0, ]),
            )
            for dtag, clustering in zip(clusterings.clusterings, clusterings.clusterings.values())
        }
    )
    )

    # Filter out small clusters
    clusterings_large: Clusterings = clusterings.filter_size(grid,
                                                             min_blob_volume,
                                                             )
    print("\t\tAfter filtering: large: {}".format(
        {dtag: len(cluster) for dtag, cluster in
         zip(clusterings_large.clusterings, clusterings_large.clusterings.values())}))

    # Filter out weak clusters (low peak z score)
    clusterings_peaked: Clusterings = clusterings_large.filter_peak(grid,
                                                                    min_blob_z_peak)
    print("\t\tAfter filtering: peak: {}".format(
        {dtag: len(cluster) for dtag, cluster in
         zip(clusterings_peaked.clusterings, clusterings_peaked.clusterings.values())}))

    clusterings_merged = clusterings_peaked.merge_clusters()
    print("\t\tAfter filtering: merged: {}".format(
        {dtag: len(_cluster) for dtag, _cluster in
         zip(clusterings_merged.clusterings, clusterings_merged.clusterings.values())}))

    ###################################################################
    # # Fund the events
    ###################################################################
    # Calculate the shell events
    print("getting events")
    print(f"\tGot {len(clusterings_merged.clusterings)} clusters")
    events: Events = Events.from_clusters(
        clusterings_merged,
        model,
        dataset_xmaps,
        grid,
        1.732,  # TODO: make this a variable ;')
        process_local,
    )

    ###################################################################
    # # Generate event maps
    ###################################################################
    # Save the event maps!
    print("print events")
    printer.pprint(events)
    events.save_event_maps(dataset_truncated_datasets,
                           alignments,
                           dataset_xmaps,
                           model,
                           pandda_fs_model,
                           grid,
                           structure_factors,
                           outer_mask,
                           inner_mask_symmetry,
                           mapper=None,
                           )

    return DatasetResult(
        dtag=test_dtag,
        events=events,
        log=dataset_log,
    )


# Define how to process a shell
def process_shell(
        shell: Shell,
        datasets: Dict[Dtag, Dataset],
        alignments,
        grid,
        pandda_fs_model,
        reference,
        process_local,
        structure_factors: StructureFactors,
        sample_rate: float,
        contour_level,
        cluster_cutoff_distance_multiplier,
        min_blob_volume,
        min_blob_z_peak,
        outer_mask,
        inner_mask_symmetry,
):
    shell_log = {}

    if "BAZ2BA-x447" not in [dtag.dtag for dtag in shell.test_dtags]:
        print(f"447 is not in {shell.test_dtags} ")
        return None

    print(f"Working on shell: {shell}")

    # Seperate out test and train datasets
    shell_datasets: Dict[Dtag, Dataset] = {
        dtag: dataset
        for dtag, dataset
        in datasets.items()
        if dtag in shell.all_dtags
    }

    ###################################################################
    # # Homogonise shell datasets by truncation of resolution
    ###################################################################
    print("Truncating datasets")
    shell_truncated_datasets: Datasets = truncate(
        shell_datasets,
        resolution=Resolution(min([datasets[dtag].reflections.resolution().resolution for dtag in shell.all_dtags])),
        structure_factors=structure_factors,
    )

    ###################################################################
    # # Generate aligned Xmaps
    ###################################################################
    print("Loading xmaps")
    start = time.time()

    load_xmap_paramaterised = partial(
        Xmap.from_unaligned_dataset_c,
        grid=grid,
        structure_factors=structure_factors,
        sample_rate=sample_rate,
    )

    results = process_local(
        partial(
            load_xmap_paramaterised,
            shell_truncated_datasets[key],
            alignments[key],
        )
        for key
        in shell_truncated_datasets
    )

    xmaps = {dtag: xmap
             for dtag, xmap
             in zip(shell_truncated_datasets, results)
             }

    finish = time.time()
    print(f"Mapped {len(xmaps)} xmaps in {finish - start}")

    ###################################################################
    # # Process each test dataset
    ###################################################################
    # Now that all the data is loaded, get the comparison set and process each test dtag
    process_dataset_paramaterized = partial(
        process_dataset,
        shell=shell,
        alignments=alignments,
        pandda_fs_model=pandda_fs_model,
        reference=reference,
        grid=grid,
        contour_level=contour_level,
        cluster_cutoff_distance_multiplier=cluster_cutoff_distance_multiplier,
        min_blob_volume=min_blob_volume,
        min_blob_z_peak=min_blob_z_peak,
        structure_factors=structure_factors,
        outer_mask=outer_mask,
        inner_mask_symmetry=inner_mask_symmetry,
        process_local=process_local_serial,
    )

    results = process_local_serial(
        [
            partial(
                process_dataset_paramaterized,
                test_dtag,
                dataset_truncated_datasets={_dtag: shell_truncated_datasets[_dtag] for _dtag in
                                            shell.train_dtags[test_dtag]},
                dataset_xmaps={_dtag: xmaps[_dtag] for _dtag in shell.train_dtags[test_dtag]},
            )
            for test_dtag
            in shell.train_dtags
        ],
    )

    return ShellResult(
        shell=shell,
        dataset_results=results,
        log=shell_log,
    )


def process_pandda(
        data_dirs: str,
        out_dir: str,
        pdb_regex: str = "*.pdb",
        mtz_regex: str = "*.mtz",
        ligand_cif_regex: str = "*.cif",
        ligand_pdb_regex: str = "*.pdb",
        ground_state_datasets: Optional[List[str]] = None,
        exclude_from_z_map_analysis: Optional[List[str]] = None,
        exclude_from_characterisation: Optional[List[str]] = None,
        only_datasets: Optional[List[str]] = None,
        ignore_datasets: Optional[List[str]] = None,
        dynamic_res_limits: bool = True,
        high_res_upper_limit: float = 1.0,
        high_res_lower_limit: float = 4.0,
        high_res_increment: float = 0.05,
        max_shell_datasets: int = 60,
        min_characterisation_datasets: int = 15,
        structure_factors: Optional[Tuple[str, str]] = None,
        all_data_are_valid_values: bool = True,
        low_resolution_completeness: float = 4.0,
        sample_rate: float = 3.0,
        max_rmsd_to_reference: float = 1.5,
        max_rfree: float = 0.4,
        max_wilson_plot_z_score=1.5,
        same_space_group_only: bool = False,
        similar_models_only: bool = False,
        resolution_factor: float = 0.25,
        grid_spacing: float = 0.5,
        padding: float = 3.0,
        density_scaling: bool = True,
        outer_mask: float = 8.0,
        inner_mask: float = 2.0,
        inner_mask_symmetry: float = 2.0,
        contour_level: float = 2.5,
        negative_values: bool = False,
        min_blob_volume: float = 10.0,
        min_blob_z_peak: float = 3.0,
        clustering_cutoff: float = 1.5,
        cluster_cutoff_distance_multiplier: float = 1.0,
        min_bdc: float = 0.0,
        max_bdc: float = 1.0,
        increment: float = 0.05,
        output_multiplier: float = 2.0,
        local_cpus: int = 12,
        job_params_file: Optional[str] = None,
        comparison_strategy: str = "closest_cutoff",
        comparison_res_cutoff: float = 0.5,
        comparison_min_comparators: int = 30,
        comparison_max_comparators: int = 30,
        local_processing: str = "multiprocessing_forkserver",
        global_processing: str = "serial",
        autobuild: bool = False,
        debug: bool = True,
):
    ###################################################################
    # # Configuration
    ###################################################################
    print("Getting config")

    # Process args
    data_dirs = Path(data_dirs)
    out_dir = Path(out_dir)
    structure_factors = StructureFactors(f=structure_factors[0], phi=structure_factors[1])

    print("Initialising log...")
    pandda_log: Dict = {}

    print("FSmodel building")
    pandda_fs_model: PanDDAFSModel = PanDDAFSModel.from_dir(data_dirs,
                                                            out_dir,
                                                            pdb_regex,
                                                            mtz_regex,
                                                            ligand_cif_regex,
                                                            ligand_pdb_regex,
                                                            )
    pandda_fs_model.build()

    print("Getting multiprocessor")
    try:

        # Get local processor
        if local_processing == "serial":
            raise NotImplementedError()
            process_local = ...
        elif local_processing == "joblib":
            process_local = partial(process_local_joblib, n_jobs=local_cpus, verbose=0)
        elif local_processing == "multiprocessing_forkserver":
            mp.set_start_method("forkserver")
            process_local = partial(process_local_multiprocessing, n_jobs=local_cpus, method="forkserver")
        elif local_processing == "multiprocessing_spawn":
            mp.set_start_method("spawn")
            process_local = partial(process_local_multiprocessing, n_jobs=local_cpus, method="forkserver")
        else:
            raise Exception()

        # Get global processor
        if global_processing == "serial":
            process_global = process_global_serial
        elif global_processing == "cluster":
            raise NotImplementedError()
            process_global = ...
        else:
            raise Exception()

        # Set up autobuilding
        if autobuild:
            if autobuild_strategy == "rhofit":
                autobuild_parametrized = partial(
                    autobuild_rhofit,
                )

            elif autobuild_strategy == "inbuilt":
                autobuild_parametrized = partial(
                    autobuild_inbuilt,
                )

            else:
                raise Exception(f"Autobuild strategy: {autobuild_strategy} is not valid!")

        # Parameterise
        process_shell_paramaterised = partial(
            process_shell,
            process_local=process_local,
            structure_factors=structure_factors,
            sample_rate=sample_rate,
            contour_level=contour_level,
            cluster_cutoff_distance_multiplier=cluster_cutoff_distance_multiplier,
            min_blob_volume=min_blob_volume,
            min_blob_z_peak=min_blob_z_peak,
            outer_mask=outer_mask,
            inner_mask_symmetry=inner_mask_symmetry,
        )

        ###################################################################
        # # Pre-pandda
        ###################################################################

        # Get datasets
        print("Loading datasets")
        datasets_initial: Datasets = Datasets.from_dir(pandda_fs_model)
        print(f"\tThere are initially: {len(datasets_initial)} datasets")

        # Make dataset validator
        validation_strategy = partial(validate_strategy_num_datasets,
                                      min_characterisation_datasets=min_characterisation_datasets,
                                      )
        validate_paramterized = partial(validate, strategy=validation_strategy)

        # Initial filters
        print("Filtering invalid datasaets")
        datasets_invalid: Datasets = datasets_initial.remove_invalid_structure_factor_datasets(
            structure_factors)
        pandda_log[constants.LOG_INVALID] = [dtag.dtag for dtag in datasets_initial if dtag not in datasets_invalid]
        validate_paramterized(datasets_invalid, exception=Exception("Too few datasets after filter: invalid"))

        datasets_low_res: Datasets = datasets_invalid.remove_low_resolution_datasets(
            low_resolution_completeness)
        pandda_log[constants.LOG_LOW_RES] = [dtag.dtag for dtag in datasets_invalid if dtag not in datasets_low_res]
        validate_paramterized(datasets_invalid, exception=Exception("Too few datasets after filter: low res"))

        datasets_rfree: Datasets = datasets_low_res.remove_bad_rfree(max_rfree)
        validate_paramterized(datasets_invalid, exception=Exception("Too few datasets after filter: rfree"))

        datasets_wilson: Datasets = datasets_rfree.remove_bad_wilson(
            max_wilson_plot_z_score)  # TODO
        validate_paramterized(datasets_invalid, exception=Exception("Too few datasets after filter: wilson"))

        # Select refernce
        print("Getting reference")
        reference: Reference = Reference.from_datasets(datasets_wilson)

        # Post-reference filters
        print("smoothing")
        start = time.time()
        datasets_smoother: Datasets = datasets_wilson.smooth_datasets(
            reference,
            structure_factors=structure_factors,
            mapper=process_local,
        )
        finish = time.time()
        print(f"Smoothed in {finish - start}")

        print("Removing dissimilar models")
        datasets_diss_struc: Datasets = datasets_smoother.remove_dissimilar_models(
            reference,
            max_rmsd_to_reference,
        )
        validate_paramterized(datasets_invalid, exception=Exception("Too few datasets after filter: structure"))

        print("Removing models with large gaps")
        datasets_gaps: Datasets = datasets_smoother.remove_models_with_large_gaps(reference, )
        for dtag in datasets_gaps:
            if dtag not in datasets_diss_struc.datasets:
                print(f"WARNING: Removed dataset {dtag} due to a large gap")
        validate_paramterized(datasets_invalid, exception=Exception("Too few datasets after filter: structure gaps"))

        print("Removing dissimilar space groups")
        datasets_diss_space: Datasets = datasets_gaps.remove_dissimilar_space_groups(reference)
        validate_paramterized(datasets_invalid, exception=Exception("Too few datasets after filter: space group"))

        datasets = {dtag: datasets_diss_space[dtag] for dtag in datasets_diss_space}

        # Grid
        print("Getting grid")
        grid: Grid = Grid.from_reference(reference,
                                         outer_mask,
                                         inner_mask_symmetry,
                                         sample_rate=sample_rate,
                                         )

        if debug > 1:
            print("Summarising protein mask")
            summarise_grid(grid.partitioning.protein_mask)
            print("Summarising symmetry mask")
            summarise_grid(grid.partitioning.symmetry_mask)
            print("Summarising total mask")
            summarise_grid(grid.partitioning.total_mask)

        print("Getting alignments")
        alignments: Alignments = Alignments.from_datasets(
            reference,
            datasets,
        )

        ###################################################################
        # # Assign comparison datasets
        ###################################################################

        # Assign comparator set for each dataset
        if comparison_strategy == "closest":
            # Closest datasets after clustering
            raise NotImplementedError()
            comparators: Dict[Dtag, List[Dtag]] = ...

        elif comparison_strategy == "closest_cutoff":
            # Closest datasets after clustering as long as they are not too poor res
            comparators: Dict[Dtag, List[Dtag]] = get_comparators_closest_cutoff(
                datasets,
                alignments,
                grid,
                comparison_min_comparators,
                comparison_max_comparators,
                structure_factors,
                sample_rate,
                comparison_res_cutoff,
                process_local,
            )

        elif comparison_strategy == "high_res":
            # Almost Old PanDDA strategy: highest res datasets
            raise NotImplementedError()
            comparators: Dict[Dtag, List[Dtag]] = ...

        elif comparison_strategy == "high_res_random":
            # Old pandda strategy: random datasets that are higher resolution
            comparators: Dict[Dtag, List[Dtag]] = get_comparators_high_res_random(
                datasets,
                comparison_min_comparators,
                comparison_max_comparators,
            )

        else:
            raise Exception("Unrecognised comparison strategy")

        print("Comparators are:")
        if debug:
            printer.pprint(comparators)

        ###################################################################
        # # Process shells
        ###################################################################

        # Partition the Analysis into shells in which all datasets are being processed at a similar resolution for the
        # sake of computational efficiency
        shells = get_shells(
            datasets,
            comparators,
            min_characterisation_datasets,
            max_shell_datasets,
            high_res_increment,
        )

        print("Shells are:")
        if debug:
            printer.pprint(shells)

        # Process the shells
        shell_results = process_global(
            [
                partial(
                    process_shell_paramaterised,
                    shell,
                    datasets,
                    alignments,
                    grid,
                    pandda_fs_model,
                    reference,
                )
                for res, shell
                in shells.items()
            ],
        )

        ###################################################################
        # # Autobuilding
        ###################################################################

        # Autobuild the results if set to
        if autobuild_results:
            autobuild_results: Dict[EventID, AutobuildResult] = process_global(
                [
                    partial(
                        autobuild_parametrized(event),
                    )
                    for result
                    in shell_results
                ]
            )

        ###################################################################
        # # Assign Sites
        ###################################################################

        #
        all_events_events = Events.from_all_events(all_events, grid, 1.7)

        # Get the sites and output a csv of them
        site_table: SiteTable = SiteTable.from_events(all_events_events, 1.7)

        ###################################################################
        # # Output pandda summary information
        ###################################################################

        # Output a csv of the events
        event_table: EventTable = EventTable.from_events(all_events_events)
        event_table.save(pandda_fs_model.analyses.pandda_analyse_events_file)

        # Output site table
        site_table.save(pandda_fs_model.analyses.pandda_analyse_sites_file)

        # Output json log
        save_json_log(config.output.out_dir / constants.PANDDA_LOG_FILE)

    ###################################################################
    # # Handle Exceptions
    ###################################################################

    except Exception as e:
        traceback.print_exc()

        pandda_log[constants.LOG_TRACE] = traceback.format_exc()
        pandda_log[constants.LOG_EXCEPTION] = str(e)

        save_json_log(out_dir / constants.PANDDA_LOG_FILE)


if __name__ == '__main__':
    fire.Fire(process_pandda)
