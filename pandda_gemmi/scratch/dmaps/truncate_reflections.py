from ..interfaces import *
from ..dataset import Reflections

import gemmi
import numpy as np
import pandas as pd


def truncate_reflections(reflections: Reflections, index=None) -> Reflections:
    new_reflections = gemmi.Mtz(with_base=False)

    # Set dataset properties
    new_reflections.spacegroup = reflections.spacegroup
    new_reflections.set_cell_for_all(reflections.cell)

    # Add dataset
    new_reflections.add_dataset("truncated")

    # Add columns
    for column in reflections.columns:
        new_reflections.add_column(column.label, column.type)

    # Get data
    data_array = np.array(reflections, copy=True)
    data = pd.DataFrame(data_array,
                        columns=reflections.column_labels(),
                        )
    data.set_index(["H", "K", "L"], inplace=True)
    # print(data)
    # print(self.reflections.make_miller_array().shape)

    # Truncate by index
    data_indexed = data.loc[index]

    # To numpy
    data_dropped_array = data_indexed.to_numpy()

    # new data
    new_data = np.hstack([data_indexed.index.to_frame().to_numpy(),
                          data_dropped_array,
                          ]
                         )
    # print(new_data)

    # Update
    new_reflections.set_data(new_data)

    # Update resolution
    new_reflections.update_reso()
    # print(new_reflections.make_miller_array().shape)

    return Reflections(reflections.path, new_reflections)


def truncate_resolution(reflections: ReflectionsInterface, resolution: float) -> ReflectionsInterface:
    new_reflections = gemmi.Mtz(with_base=False)

    # Set dataset properties
    new_reflections.spacegroup = reflections.spacegroup
    new_reflections.set_cell_for_all(reflections.cell)

    # Add dataset
    new_reflections.add_dataset("truncated")

    # Add columns
    for column in reflections.columns:
        new_reflections.add_column(column.label, column.type)

    # Get data
    data_array = np.array(reflections, copy=True)
    data = pd.DataFrame(data_array,
                        columns=reflections.column_labels(),
                        )
    data.set_index(["H", "K", "L"], inplace=True)

    # add resolutions
    data["res"] = reflections.make_d_array()

    # Truncate by resolution
    data_truncated = data[data["res"] >= resolution]

    # Rem,ove res colum
    data_dropped = data_truncated.drop("res", "columns")

    # To numpy
    data_dropped_array = data_dropped.to_numpy()

    # new data
    new_data = np.hstack([data_dropped.index.to_frame().to_numpy(),
                          data_dropped_array,
                          ]
                         )

    # Update
    new_reflections.set_data(new_data)

    # Update resolution
    new_reflections.update_reso()

    return Reflections(reflections.path, new_reflections)


def common_reflections(reflections: Reflections,
                       reference_ref: Reflections,
                       ):
    # Get own reflections
    dtag_reflections = self.reflections.reflections
    dtag_reflections_array = np.array(dtag_reflections, copy=True)
    dtag_reflections_table = pd.DataFrame(dtag_reflections_array,
                                          columns=dtag_reflections.column_labels(),
                                          )
    dtag_reflections_table.set_index(["H", "K", "L"], inplace=True)
    dtag_flattened_index = dtag_reflections_table[
        ~dtag_reflections_table[structure_factors.f].isna()].index.to_flat_index()

    # Get reference
    reference_reflections = reference_ref.reflections
    reference_reflections_array = np.array(reference_reflections, copy=True)
    reference_reflections_table = pd.DataFrame(reference_reflections_array,
                                               columns=reference_reflections.column_labels(),
                                               )
    reference_reflections_table.set_index(["H", "K", "L"], inplace=True)
    reference_flattened_index = reference_reflections_table[
        ~reference_reflections_table[structure_factors.f].isna()].index.to_flat_index()

    running_index = dtag_flattened_index.intersection(reference_flattened_index)

    return running_index.to_list()


def common_reflections(datasets: Dict[str, DatasetInterface], tol=0.000001):
    running_index: Optional[pd.Index] = None

    for dtag in datasets:
        dataset = datasets[dtag]
        reflections = dataset.reflections.reflections
        reflections_array = np.array(reflections, copy=True)
        reflections_table = pd.DataFrame(reflections_array,
                                         columns=reflections.column_labels(),
                                         )
        reflections_table.set_index(["H", "K", "L"], inplace=True)

        is_na = reflections_table[structure_factors.f].isna()
        is_zero = reflections_table[structure_factors.f].abs() < tol
        mask = ~(is_na | is_zero)

        flattened_index = reflections_table[mask].index.to_flat_index()
        if running_index is None:
            running_index = flattened_index
        if running_index is not None:
            running_index = running_index.intersection(flattened_index)

    if running_index is not None:
        return running_index.to_list()

    else:
        raise Exception(
            "Somehow a running index has not been calculated. This should be impossible. Contact mantainer.")


class TruncateReflections:
    def __init__(self,
                 datasets: Dict[str, DatasetInterface],
                 resolution: float,
                 ):
        new_datasets_resolution = {}

        # Truncate by common resolution
        for dtag in datasets:
            truncated_dataset = truncate_resolution(
                datasets[dtag],
                resolution,
            )

            new_datasets_resolution[dtag] = truncated_dataset

        dataset_resolution_truncated = new_datasets_resolution

        # Get common set of reflections
        common_reflections = common_reflections(dataset_resolution_truncated)

        # truncate on reflections
        new_datasets_reflections = {}
        for dtag in dataset_resolution_truncated:
            reflections = dataset_resolution_truncated[dtag].reflections.reflections
            reflections_array = np.array(reflections)

            print(f"Truncated reflections: {dtag}")
            truncated_dataset = dataset_resolution_truncated[dtag].truncate_reflections(common_reflections,
                                                                                        )
            reflections = truncated_dataset.reflections.reflections
            reflections_array = np.array(reflections)

            new_datasets_reflections[dtag] = truncated_dataset

        return new_datasets_reflections