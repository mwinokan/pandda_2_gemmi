import time

import numpy as np
import gemmi

from ..interfaces import *

import os
import inspect

import torch

from .event import Event

from pandda_gemmi.cnn import resnet
from pandda_gemmi.cnn import resnet18


def sample_xmap(xmap, transform, sample_array):
    xmap.interpolate_values(sample_array, transform)
    return sample_array


def get_sample_transform_from_event(centroid,
                                    sample_distance: float,
                                    n: int,
                                    translation: float):
    # Get basic sample grid transform
    initial_transform = gemmi.Transform()
    scale_matrix = np.eye(3) * sample_distance
    initial_transform.mat.fromlist(scale_matrix.tolist())

    # Get sample grid centroid
    sample_grid_centroid = (np.array([n, n, n]) * sample_distance) / 2

    # Get centre grid transform
    centre_grid_transform = gemmi.Transform()
    centre_grid_transform.vec.fromlist([
        -sample_grid_centroid[0],
        -sample_grid_centroid[1],
        -sample_grid_centroid[2],
    ])

    # Event centre transform
    event_centre_transform = gemmi.Transform()
    event_centre_transform.vec.fromlist([x for x in centroid])

    # Apply random translation
    # transform = event_centre_transform.combine(
    #     centre_grid_transform.combine(
    #         initial_transform
    #     )
    # )

    transform = gemmi.Transform()
    transform.vec.fromlist([
        centroid[j] - sample_grid_centroid[j]
        for j
        in [0, 1, 2]
    ])
    transform.mat.fromlist(scale_matrix.tolist())
    corner_0_pos = transform.apply(gemmi.Position(0.0, 0.0, 0.0))
    corner_n_pos = transform.apply(gemmi.Position(
        float(n),
        float(n),
        float(n),
    )
    )
    corner_0 = (corner_0_pos.x, corner_0_pos.y, corner_0_pos.z)
    corner_n = (corner_n_pos.x, corner_n_pos.y, corner_n_pos.z)
    average_pos = [c0 + (cn - c0) / 2 for c0, cn in zip(corner_0, corner_n)]
    event_centroid = centroid
    # logger.debug(f"Centroid: {event_centroid}")
    # logger.debug(f"Corners: {corner_0} : {corner_n} : average: {average_pos}")
    # logger.debug(f"Distance from centroid to average: {gemmi.Position(*average_pos).dist(gemmi.Position(*event_centroid))}")

    return transform


def get_model_map(structure, xmap_event):
    # structure = reference.dataset.structure.structure
    new_xmap = gemmi.FloatGrid(xmap_event.nu, xmap_event.nv, xmap_event.nw)
    new_xmap.spacegroup = xmap_event.spacegroup
    new_xmap.set_unit_cell(xmap_event.unit_cell)
    for model in structure:
        for chain in model:
            for residue in chain.get_polymer():
                for atom in residue:
                    new_xmap.set_points_around(
                        atom.pos,
                        radius=1,
                        value=1.0,
                    )

    return new_xmap


def get_bdc(event, xmap_grid, mean_grid, median):
    xmap_array = np.array(xmap_grid, copy=False)
    mean_array = np.array(mean_grid, copy=False)
    event_indicies = tuple(
        [
            event.point_array[:, 0].flatten(),
            event.point_array[:, 1].flatten(),
            event.point_array[:, 2].flatten(),
        ]
    )
    centroid = np.mean(event.pos_array, axis=0)
    dist = np.linalg.norm(centroid - [6.0,-4.0,25.0])

    xmap_vals = xmap_array[event_indicies]
    mean_map_vals = mean_array[event_indicies]
    diffs = {}
    for bdc in np.linspace(0.0, 0.95, 50):
        # new_median = np.median((xmap_vals - (bdc * mean_map_vals)) / (1 - bdc))
        # new_median = np.quantile(
        #     (xmap_vals - (bdc * mean_map_vals)) / (1 - bdc),
        #     np.linspace(0.05, 0.95, 10)
        # )
        new_median = np.quantile(
            (xmap_vals - (bdc * mean_map_vals)) / (1 - bdc),
            0.05
        )

        diff = np.abs(median - new_median)
        diff_sum = float(np.sum(diff))
        diffs[round(float(bdc), 2)] = diff_sum
        # print(f"\t\t{round(float(bdc), 2)} : {round(float(median), 2)} {round(float(new_median), 2)} {round(diff, 2)}")
        if dist < 5.0:
            print(f"\t\t{round(float(bdc), 2)} : {round(float(np.mean(median)), 2)} {round(float(np.mean(new_median)), 2)} {round(diff_sum, 2)}")
            # print(f"\t\t{diff}")
    return min(diffs, key=lambda _bdc: diffs[_bdc])


class ScoreCNN:
    def __init__(self, n=30):
        # Get model
        if torch.cuda.is_available():
            self.dev = "cuda:0"
        else:
            self.dev = "cpu"

        # Load the model
        cnn = resnet18(num_classes=2, num_input=4)
        cnn_path = Path(os.path.dirname(inspect.getfile(resnet))) / "model.pt"
        cnn.load_state_dict(torch.load(cnn_path, map_location=self.dev))

        # Add model to device
        cnn.to(self.dev)
        cnn.eval()
        self.cnn = cnn.float()

        self.n = n

    def __call__(self, events, xmap_grid, mean_grid, z_grid, model_grid):

        scored_events = {}
        time_begin_get_images = time.time()
        images = {}
        for event_id, event in events.items():
            centroid = np.mean(event.pos_array, axis=0)

            sample_transform = get_sample_transform_from_event(
                centroid,
                0.5,
                self.n,
                3.5
            )

            sample_array = np.zeros((self.n, self.n, self.n), dtype=np.float32)

            bdcs = np.linspace(0.0, 0.95, 20).reshape((20, 1, 1, 1))

            xmap_sample = sample_xmap(xmap_grid, sample_transform, np.copy(sample_array))

            mean_map_sample = sample_xmap(mean_grid, sample_transform, np.copy(sample_array))

            image_events = (xmap_sample[np.newaxis, :] - (bdcs * mean_map_sample[np.newaxis, :])) / (1 - bdcs)

            image_raw = np.stack([xmap_sample for _j in range(20)])

            sample_array_zmap = np.copy(sample_array)
            zmap_sample = sample_xmap(z_grid, sample_transform, sample_array_zmap)
            image_zmap = np.stack([zmap_sample for _j in range(20)])

            sample_array_model = np.copy(sample_array)

            model_sample = sample_xmap(model_grid, sample_transform, sample_array_model)
            image_model = np.stack([model_sample for _j in range(20)])

            image = np.stack([image_events, image_raw, image_zmap, image_model], axis=1)
            images[event_id] = image

        time_finish_get_images = time.time()
        print(f"\t\t\t\tGot images in: {round(time_finish_get_images-time_begin_get_images, 2)}")

        for event_id, event in events.items():
            image = images[event_id]

            # Transfer to tensor
            image_t = torch.from_numpy(image)

            # Move tensors to device
            image_c = image_t.to(self.dev)

            # Run model
            model_annotation = self.cnn(image_c.float())

            # Track score
            model_annotations = model_annotation.to(torch.device("cpu")).detach().numpy()

            flat_bdcs = bdcs.flatten()
            max_score_index = np.argmax([annotation for annotation in model_annotations[:, 1]])
            bdc = float(flat_bdcs[max_score_index])
            score = float(model_annotations[max_score_index, 1])

            centroid = np.mean(event.pos_array, axis=0)
            dist = np.linalg.norm(centroid - [6.0, -4.0, 25.0])
            if dist < 5.0:
                print(f"##### {event_id} #####")
                for bdc, score in zip([x for x in flat_bdcs], [x for x in model_annotations[:, 1]]):
                    print(f"\t\t\t{round(float(bdc), 2)} : {round(float(score), 2)}")

            scored_event = Event(
                event.pos_array,
                event.point_array,
                score,
                bdc
            )
            scored_events[event_id] = scored_event


        return scored_events

    # def __call__(self, events, xmap_grid, mean_grid, z_grid, model_grid, median):
    #
    #     scored_events = {}
    #     time_begin_get_images = time.time()
    #     images = {}
    #     bdcs = {}
    #     for event_id, event in events.items():
    #         centroid = np.mean(event.pos_array, axis=0)
    #         dist = np.linalg.norm(centroid - [6.0, -4.0, 25.0])
    #         if dist < 5.0:
    #             print(f"##### {event_id} #####")
    #             print(f"Centroid: {centroid}")
    #             print(f"Distance: {dist}")
    #         sample_transform = get_sample_transform_from_event(
    #             centroid,
    #             0.5,
    #             self.n,
    #             3.5
    #         )
    #
    #         bdc = get_bdc(event, xmap_grid, mean_grid, median)
    #         bdcs[event_id] = bdc
    #         # print(f"BDC: {bdc}")
    #
    #         sample_array = np.zeros((self.n, self.n, self.n), dtype=np.float32)
    #
    #         # bdcs = np.linspace(0.0, 0.95, 20).reshape((20, 1, 1, 1))
    #
    #         xmap_sample = sample_xmap(xmap_grid, sample_transform, np.copy(sample_array))
    #
    #         mean_map_sample = sample_xmap(mean_grid, sample_transform, np.copy(sample_array))
    #
    #         sample_event = (xmap_sample - (bdc * mean_map_sample)) / (1 - bdc)
    #         image_event = sample_event[np.newaxis, :]
    #         image_raw = xmap_sample[np.newaxis, :]
    #
    #         # image_raw = np.stack([xmap_sample for _j in range(20)])
    #
    #         sample_array_zmap = np.copy(sample_array)
    #         zmap_sample = sample_xmap(z_grid, sample_transform, sample_array_zmap)
    #         image_zmap = zmap_sample[np.newaxis, :]
    #         # image_zmap = np.stack([zmap_sample for _j in range(20)])
    #
    #         sample_array_model = np.copy(sample_array)
    #
    #         model_sample = sample_xmap(model_grid, sample_transform, sample_array_model)
    #         image_model = model_sample[np.newaxis, :]
    #         # image_model = np.stack([model_sample for _j in range(20)])
    #
    #         image = np.stack([image_event, image_raw, image_zmap, image_model], axis=1)
    #         images[event_id] = image
    #
    #     time_finish_get_images = time.time()
    #     # print(f"\t\t\t\tGot images in: {round(time_finish_get_images - time_begin_get_images, 2)}")
    #
    #     for event_id, event in events.items():
    #         image = images[event_id]
    #
    #         # Transfer to tensor
    #         image_t = torch.from_numpy(image)
    #
    #         # Move tensors to device
    #         image_c = image_t.to(self.dev)
    #
    #         # Run model
    #         model_annotation = self.cnn(image_c.float())
    #
    #         # Track score
    #         model_annotations = model_annotation.to(torch.device("cpu")).detach().numpy()
    #
    #         # flat_bdcs = bdcs.flatten()
    #         max_score_index = np.argmax([annotation for annotation in model_annotations[:, 1]])
    #         # bdc = float(flat_bdcs[max_score_index])
    #         score = float(model_annotations[max_score_index, 1])
    #
    #         scored_event = Event(
    #             event.pos_array,
    #             event.point_array,
    #             score,
    #             bdcs[event_id]
    #         )
    #         scored_events[event_id] = scored_event
    #
    #     return scored_events
