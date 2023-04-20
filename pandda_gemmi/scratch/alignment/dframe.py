import itertools
import time

import gemmi
import scipy
import numpy as np

from ..interfaces import *
from ..dataset import ResidueID, StructureArray, contains
from ..dmaps import SparseDMap
from ..processor import Partial
from ..dataset import Structure


def transform_structure_to_unit_cell(
        structure,
        unit_cell,
        offset
):
    st = structure.structure.clone()
    # structure_poss = []
    # for model in st:
    #     for chain in model:
    #         for residue in chain:
    #             for atom in residue:
    #                 pos = atom.pos
    #                 structure_poss.append([pos.x, pos.y, pos.z])
    #
    # pos_array = np.array(structure_poss)

    transform = gemmi.Transform()
    transform.vec.fromlist(offset.tolist())

    for model in st:
        for chain in model:
            for residue in chain:
                for atom in residue:
                    pos = atom.pos
                    new_pos_vec = transform.apply(pos)
                    new_pos = gemmi.Position(new_pos_vec.x, new_pos_vec.y, new_pos_vec.z)
                    atom.pos = new_pos

    st.spacegroup_hm = gemmi.find_spacegroup_by_name("P 1").hm
    st.cell = unit_cell

    return Structure(structure.path, st)


class PointPositionArray(PointPositionArrayInterface):
    def __init__(self, points, positions):
        self.points = points
        self.positions = positions

    @staticmethod
    def fractionalize_grid_point_array(grid_point_array, grid):
        return grid_point_array / np.array([grid.nu, grid.nv, grid.nw])

    @staticmethod
    def orthogonalize_fractional_array(fractional_array, grid):
        orthogonalization_matrix = np.array(grid.unit_cell.orthogonalization_matrix.tolist())
        orthogonal_array = np.matmul(orthogonalization_matrix, fractional_array.T).T

        return orthogonal_array

    @staticmethod
    def fractionalize_orthogonal_array(fractional_array, grid):
        fractionalization_matrix = np.array(grid.unit_cell.fractionalization_matrix.tolist())
        fractional_array = np.matmul(fractionalization_matrix, fractional_array.T).T

        return fractional_array

    @staticmethod
    def fractionalize_grid_point_array_mat(grid_point_array, spacing):
        return grid_point_array / np.array(spacing)

    @staticmethod
    def orthogonalize_fractional_array_mat(fractional_array, orthogonalization_matrix):
        orthogonal_array = np.matmul(orthogonalization_matrix, fractional_array.T).T

        return orthogonal_array

    @staticmethod
    def fractionalize_orthogonal_array_mat(orthogonal_array, fractionalization_matrix):
        fractional_array = np.matmul(fractionalization_matrix, orthogonal_array.T).T

        return fractional_array

    @staticmethod
    def get_nearby_grid_points(grid, position, radius):
        # Get the fractional position
        # print(f"##########")

        x, y, z = position.x, position.y, position.z

        corners = []
        for dx, dy, dz in itertools.product([-radius, + radius], [-radius, + radius], [-radius, + radius]):
            corner = gemmi.Position(x + dx, y + dy, z + dz)
            corner_fractional = grid.unit_cell.fractionalize(corner)
            # corner_fractional_2 = PointPositionArray.fractionalize_orthogonal_array(
            #     np.array([corner.x, corner.y, corner.z]).reshape((1,3)),
            #     np.array(grid.unit_cell.fractionalization_matrix.tolist())
            # )
            # print(f"{(corner_fractional.x, corner_fractional.y, corner_fractional.z)} {corner_fractional_2}")
            corners.append([corner_fractional.x, corner_fractional.y, corner_fractional.z])

        fractional_corner_array = np.array(corners)
        fractional_min = np.min(fractional_corner_array, axis=0)
        fractional_max = np.max(fractional_corner_array, axis=0)

        # print(f"Fractional min: {fractional_min}")
        # print(f"Fractional max: {fractional_max}")

        # Find the fractional bounding box
        # x, y, z = fractional.x, fractional.y, fractional.z
        # dx = radius / grid.nu
        # dy = radius / grid.nv
        # dz = radius / grid.nw
        #
        # # Find the grid bounding box
        # u0 = np.floor((x - dx) * grid.nu)
        # u1 = np.ceil((x + dx) * grid.nu)
        # v0 = np.floor((y - dy) * grid.nv)
        # v1 = np.ceil((y + dy) * grid.nv)
        # w0 = np.floor((z - dz) * grid.nw)
        # w1 = np.ceil((z + dz) * grid.nw)
        u0 = np.floor(fractional_min[0] * grid.nu)
        u1 = np.ceil(fractional_max[0] * grid.nu)
        v0 = np.floor(fractional_min[1] * grid.nv)
        v1 = np.ceil(fractional_max[1] * grid.nv)
        w0 = np.floor(fractional_min[2] * grid.nw)
        w1 = np.ceil(fractional_max[2] * grid.nw)

        # print(f"Fractional bounds are: u: {u0} {u1} : v: {v0} {v1} : w: {w0} {w1}")

        # Get the grid points
        grid_point_array = np.array(
            [
                xyz_tuple
                for xyz_tuple
                in itertools.product(
                np.arange(u0, u1 + 1),
                np.arange(v0, v1 + 1),
                np.arange(w0, w1 + 1),
            )
            ]
        )
        # print(f"Grid point array shape: {grid_point_array.shape}")
        # print(f"Grid point first element: {grid_point_array[0, :]}")

        # Get the point positions
        position_array = PointPositionArray.orthogonalize_fractional_array(
            PointPositionArray.fractionalize_grid_point_array(
                grid_point_array,
                # [grid.nu, grid.nv, grid.nw],
                grid
            ),
            # np.array(grid.unit_cell.orthogonalization_matrix.tolist()),
            grid
        )
        # print(f"Grid position array shape: {position_array.shape}")
        # print(f"Grid position first element: {position_array[0, :]}")

        # Get the distances to the position
        distance_array = np.linalg.norm(
            position_array - np.array([position.x, position.y, position.z]),
            axis=1,
        )
        # print(f"Distance array shape: {distance_array.shape}")
        # print(f"Distance array first element: {distance_array[0]}")

        # Mask the points on distances
        points_within_radius = grid_point_array[distance_array < radius]
        positions_within_radius = position_array[distance_array < radius]
        # print(f"Had {grid_point_array.shape} points, of which {points_within_radius.shape} within radius")

        # Bounding box orth
        # orth_bounds_min = np.min(positions_within_radius, axis=0)
        # orth_bounds_max = np.max(positions_within_radius, axis=0)
        # point_bounds_min = np.min(points_within_radius, axis=0)
        # point_bounds_max = np.max(points_within_radius, axis=0)
        #
        # print(f"Original position was: {position.x} {position.y} {position.z}")
        # print(f"Orth bounding box min: {orth_bounds_min}")
        # print(f"Orth bounding box max: {orth_bounds_max}")
        # print(f"Point bounding box min: {point_bounds_min}")
        # print(f"Point bounding box max: {point_bounds_max}")
        # print(f"First point pos pair: {points_within_radius[0, :]} {positions_within_radius[0, :]}")
        # print(f"Last point pos pair: {points_within_radius[-1, :]} {positions_within_radius[-1, :]}")

        return points_within_radius.astype(int), positions_within_radius

    # @staticmethod
    # def get_nearby_grid_points_parallel(
    #         spacing,
    #         fractionalization_matrix,
    #         orthogonalization_matrix,
    #         position,
    #         radius,
    # ):
    #     # Get the fractional position
    #     # print(f"##########")
    #     time_begin = time.time()
    #     x, y, z = position[0], position[1], position[2]
    #
    #     corners = []
    #     for dx, dy, dz in itertools.product([-radius, + radius], [-radius, + radius], [-radius, + radius]):
    #         # corner = gemmi.Position(x + dx, y + dy, z + dz)
    #         corner_fractional = PointPositionArray.fractionalize_orthogonal_array_mat(
    #             np.array([x + dx, y + dy, z + dz]).reshape((1, 3)),
    #             fractionalization_matrix,
    #         )
    #         # print(corner_fractional.shape)
    #         corners.append([corner_fractional[0, 0], corner_fractional[0, 1], corner_fractional[0, 2]])
    #
    #     fractional_corner_array = np.array(corners)
    #     # print(fractional_corner_array.shape)
    #
    #     fractional_min = np.min(fractional_corner_array, axis=0)
    #     fractional_max = np.max(fractional_corner_array, axis=0)
    #
    #     # print(f"Fractional min: {fractional_min}")
    #     # print(f"Fractional max: {fractional_max}")
    #
    #     # Find the fractional bounding box
    #     # x, y, z = fractional.x, fractional.y, fractional.z
    #     # dx = radius / grid.nu
    #     # dy = radius / grid.nv
    #     # dz = radius / grid.nw
    #     #
    #     # # Find the grid bounding box
    #     # u0 = np.floor((x - dx) * grid.nu)
    #     # u1 = np.ceil((x + dx) * grid.nu)
    #     # v0 = np.floor((y - dy) * grid.nv)
    #     # v1 = np.ceil((y + dy) * grid.nv)
    #     # w0 = np.floor((z - dz) * grid.nw)
    #     # w1 = np.ceil((z + dz) * grid.nw)
    #     u0 = np.floor(fractional_min[0] * spacing[0])
    #     u1 = np.ceil(fractional_max[0] * spacing[0])
    #     v0 = np.floor(fractional_min[1] * spacing[1])
    #     v1 = np.ceil(fractional_max[1] * spacing[1])
    #     w0 = np.floor(fractional_min[2] * spacing[2])
    #     w1 = np.ceil(fractional_max[2] * spacing[2])
    #
    #     # print(f"Fractional bounds are: u: {u0} {u1} : v: {v0} {v1} : w: {w0} {w1}")
    #
    #     # Get the grid points
    #     time_begin_itertools = time.time()
    #     # grid_point_array = np.array(
    #     #     [
    #     #         xyz_tuple
    #     #         for xyz_tuple
    #     #         in itertools.product(
    #     #         np.arange(u0, u1 + 1),
    #     #         np.arange(v0, v1 + 1),
    #     #         np.arange(w0, w1 + 1),
    #     #     )
    #     #     ]
    #     # )
    #     grid = np.mgrid[u0:u1 + 1, v0: v1 + 1, w0:w1 + 1]
    #     grid_point_array = np.hstack([grid[_j].reshape((-1,1)) for _j in (0,1,2)])
    #     time_finish_itertools = time.time()
    #     print(f"\t\t\t\t\t\tGot grid array in {round(time_finish_itertools-time_begin_itertools, 1)}")
    #
    #     # print(f"Grid point array shape: {grid_point_array.shape}")
    #     # print(f"Grid point first element: {grid_point_array[0, :]}")
    #
    #     # Get the point positions
    #     time_begin_pointpos = time.time()
    #     position_array = PointPositionArray.orthogonalize_fractional_array_mat(
    #         PointPositionArray.fractionalize_grid_point_array_mat(
    #             grid_point_array,
    #             spacing,
    #         ),
    #         orthogonalization_matrix,
    #     )
    #     time_finish_pointpos = time.time()
    #     print(f"\t\t\t\t\t\tTransformed points to pos in {round(time_finish_pointpos - time_begin_pointpos, 1)}")
    #     # print(f"")
    #     # print(f"Grid position array shape: {position_array.shape}")
    #     # print(f"Grid position first element: {position_array[0, :]}")
    #
    #     # Get the distances to the position
    #     distance_array = np.linalg.norm(
    #         position_array - np.array(position),
    #         axis=1,
    #     )
    #     # print(f"Distance array shape: {distance_array.shape}")
    #     # print(f"Distance array first element: {distance_array[0]}")
    #
    #     # Mask the points on distances
    #     points_within_radius = grid_point_array[distance_array < radius]
    #     positions_within_radius = position_array[distance_array < radius]
    #     # print(f"Had {grid_point_array.shape} points, of which {points_within_radius.shape} within radius")
    #
    #     # Bounding box orth
    #     # orth_bounds_min = np.min(positions_within_radius, axis=0)
    #     # orth_bounds_max = np.max(positions_within_radius, axis=0)
    #     # point_bounds_min = np.min(points_within_radius, axis=0)
    #     # point_bounds_max = np.max(points_within_radius, axis=0)
    #     #
    #     # print(f"Original position was: {position.x} {position.y} {position.z}")
    #     # print(f"Orth bounding box min: {orth_bounds_min}")
    #     # print(f"Orth bounding box max: {orth_bounds_max}")
    #     # print(f"Point bounding box min: {point_bounds_min}")
    #     # print(f"Point bounding box max: {point_bounds_max}")
    #     # print(f"First point pos pair: {points_within_radius[0, :]} {positions_within_radius[0, :]}")
    #     # print(f"Last point pos pair: {points_within_radius[-1, :]} {positions_within_radius[-1, :]}")
    #
    #     time_finish = time.time()
    #     print(f"\t\t\t\t\tGot pos array of shape {positions_within_radius.shape} in {round(time_finish-time_begin, 1)}")
    #
    #     return points_within_radius.astype(int), positions_within_radius

    @staticmethod
    def get_nearby_grid_points_parallel(
            spacing,
            fractionalization_matrix,
            orthogonalization_matrix,
            pos_array,
            position,
            radius,
    ):
        # Get the fractional position
        # print(f"##########")
        time_begin = time.time()
        x, y, z = position[0], position[1], position[2]

        corners = []
        for dx, dy, dz in itertools.product([-radius, + radius], [-radius, + radius], [-radius, + radius]):
            # corner = gemmi.Position(x + dx, y + dy, z + dz)
            corner_fractional = PointPositionArray.fractionalize_orthogonal_array_mat(
                np.array([x + dx, y + dy, z + dz]).reshape((1, 3)),
                fractionalization_matrix,
            )
            # print(corner_fractional.shape)
            corners.append([corner_fractional[0, 0], corner_fractional[0, 1], corner_fractional[0, 2]])

        fractional_corner_array = np.array(corners)
        # print(fractional_corner_array.shape)

        fractional_min = np.min(fractional_corner_array, axis=0)
        fractional_max = np.max(fractional_corner_array, axis=0)

        # print(f"Fractional min: {fractional_min}")
        # print(f"Fractional max: {fractional_max}")

        # Find the fractional bounding box
        # x, y, z = fractional.x, fractional.y, fractional.z
        # dx = radius / grid.nu
        # dy = radius / grid.nv
        # dz = radius / grid.nw
        #
        # # Find the grid bounding box
        # u0 = np.floor((x - dx) * grid.nu)
        # u1 = np.ceil((x + dx) * grid.nu)
        # v0 = np.floor((y - dy) * grid.nv)
        # v1 = np.ceil((y + dy) * grid.nv)
        # w0 = np.floor((z - dz) * grid.nw)
        # w1 = np.ceil((z + dz) * grid.nw)
        u0 = np.floor(fractional_min[0] * spacing[0])
        u1 = np.ceil(fractional_max[0] * spacing[0])
        v0 = np.floor(fractional_min[1] * spacing[1])
        v1 = np.ceil(fractional_max[1] * spacing[1])
        w0 = np.floor(fractional_min[2] * spacing[2])
        w1 = np.ceil(fractional_max[2] * spacing[2])

        # print(f"Fractional bounds are: u: {u0} {u1} : v: {v0} {v1} : w: {w0} {w1}")

        # Get the grid points
        time_begin_itertools = time.time()
        # grid_point_array = np.array(
        #     [
        #         xyz_tuple
        #         for xyz_tuple
        #         in itertools.product(
        #         np.arange(u0, u1 + 1),
        #         np.arange(v0, v1 + 1),
        #         np.arange(w0, w1 + 1),
        #     )
        #     ]
        # )
        grid = np.mgrid[u0:u1 + 1, v0: v1 + 1, w0:w1 + 1].astype(int)
        grid_point_array = np.hstack([grid[_j].reshape((-1, 1)) for _j in (0, 1, 2)])
        time_finish_itertools = time.time()
        print(
            f"\t\t\t\t\t\tGot grid array in {round(time_finish_itertools - time_begin_itertools, 1)} of shape {grid_point_array.shape}")

        # print(f"Grid point array shape: {grid_point_array.shape}")
        # print(f"Grid point first element: {grid_point_array[0, :]}")

        # Get the point positions
        time_begin_pointpos = time.time()
        mod_point_array = np.mod(grid_point_array, spacing)
        mod_point_indexes = (
            mod_point_array[:, 0].flatten(), mod_point_array[:, 1].flatten(), mod_point_array[:, 2].flatten())
        position_array = np.zeros(grid_point_array.shape)
        print(f"\t\t\t\t\t\tInitial position array shape: {position_array.shape}")

        position_array[:, 0] = pos_array[0][mod_point_indexes]
        position_array[:, 1] = pos_array[1][mod_point_indexes]
        position_array[:, 2] = pos_array[2][mod_point_indexes]

        # position_array = pos_array[:, , ].T

        time_finish_pointpos = time.time()
        print(
            f"\t\t\t\t\t\tTransformed points to pos in {round(time_finish_pointpos - time_begin_pointpos, 1)} to shape {position_array.shape}")
        # print(f"")
        # print(f"Grid position array shape: {position_array.shape}")
        # print(f"Grid position first element: {position_array[0, :]}")

        # Get the distances to the position
        distance_array = np.linalg.norm(
            position_array - np.array(position),
            axis=1,
        )
        # print(f"Distance array shape: {distance_array.shape}")
        # print(f"Distance array first element: {distance_array[0]}")

        # Mask the points on distances
        points_within_radius = grid_point_array[distance_array < radius]
        positions_within_radius = position_array[distance_array < radius]
        # print(f"Had {grid_point_array.shape} points, of which {points_within_radius.shape} within radius")

        # Bounding box orth
        # orth_bounds_min = np.min(positions_within_radius, axis=0)
        # orth_bounds_max = np.max(positions_within_radius, axis=0)
        # point_bounds_min = np.min(points_within_radius, axis=0)
        # point_bounds_max = np.max(points_within_radius, axis=0)
        #
        # print(f"Original position was: {position.x} {position.y} {position.z}")
        # print(f"Orth bounding box min: {orth_bounds_min}")
        # print(f"Orth bounding box max: {orth_bounds_max}")
        # print(f"Point bounding box min: {point_bounds_min}")
        # print(f"Point bounding box max: {point_bounds_max}")
        # print(f"First point pos pair: {points_within_radius[0, :]} {positions_within_radius[0, :]}")
        # print(f"Last point pos pair: {points_within_radius[-1, :]} {positions_within_radius[-1, :]}")

        time_finish = time.time()
        print(
            f"\t\t\t\t\tGot pos array of shape {positions_within_radius.shape} in {round(time_finish - time_begin, 1)}")

        return points_within_radius.astype(int), positions_within_radius

    @staticmethod
    def get_nearby_grid_points_vectorized(grid, position_array, radius):
        # Get the fractional position
        # print(f"##########")

        # x, y, z = position.x, position.y, position.z

        corners = []
        for dx, dy, dz in itertools.product([-radius, + radius], [-radius, + radius], [-radius, + radius]):
            corner = position_array + np.array([dx, dy, dz])
            corner_fractional = PointPositionArray.fractionalize_orthogonal_array(corner, grid)
            corners.append(corner_fractional)

        # Axis: Atom, coord, corner
        fractional_corner_array = np.stack([corner for corner in corners], axis=-1)
        # print(f"\t\t\t\t\tFRACTIONAL corner array shape: {fractional_corner_array.shape}")

        # print(f"Fractional min: {fractional_min}")

        fractional_min = np.min(fractional_corner_array, axis=-1)
        fractional_max = np.max(fractional_corner_array, axis=-1)
        # print(f"\t\t\t\t\tFRACTIONAL min array shape: {fractional_min.shape}")

        # print(f"Fractional min: {fractional_min}")
        # print(f"Fractional max: {fractional_max}")

        # Find the fractional bounding box
        # x, y, z = fractional.x, fractional.y, fractional.z
        # dx = radius / grid.nu
        # dy = radius / grid.nv
        # dz = radius / grid.nw
        #
        # # Find the grid bounding box
        # u0 = np.floor((x - dx) * grid.nu)
        # u1 = np.ceil((x + dx) * grid.nu)
        # v0 = np.floor((y - dy) * grid.nv)
        # v1 = np.ceil((y + dy) * grid.nv)
        # w0 = np.floor((z - dz) * grid.nw)
        # w1 = np.ceil((z + dz) * grid.nw)
        u0 = np.floor(fractional_min[:, 0] * grid.nu)
        u1 = np.ceil(fractional_max[:, 0] * grid.nu)
        v0 = np.floor(fractional_min[:, 1] * grid.nv)
        v1 = np.ceil(fractional_max[:, 1] * grid.nv)
        w0 = np.floor(fractional_min[:, 2] * grid.nw)
        w1 = np.ceil(fractional_max[:, 2] * grid.nw)

        # print(f"Fractional bounds are: u: {u0} {u1} : v: {v0} {v1} : w: {w0} {w1}")

        # Get the grid points
        point_arrays = []
        position_arrays = []
        for j in range(position_array.shape[0]):
            mesh_grid = np.mgrid[u0[j]: u1[j] + 1, v0[j]: v1[j] + 1, w0[j]: w1[j] + 1]
            grid_point_array = np.hstack([
                mesh_grid[0, :, :].reshape((-1, 1)),
                mesh_grid[1, :, :].reshape((-1, 1)),
                mesh_grid[2, :, :].reshape((-1, 1)),
            ]
            )
            #     np.array(
            #     [
            #         xyz_tuple
            #         for xyz_tuple
            #         in itertools.product(
            #             np.arange(u0, u1 + 1),
            #             np.arange(v0, v1 + 1),
            #             np.arange(w0, w1 + 1),
            #     )
            #     ]
            # )
            # print(f"Grid point array shape: {grid_point_array.shape}")
            # print(f"Grid point first element: {grid_point_array[0, :]}")

            # Get the point positions
            points_position_array = PointPositionArray.orthogonalize_fractional_array(
                PointPositionArray.fractionalize_grid_point_array(
                    grid_point_array,
                    grid,
                ),
                grid,
            )
            # print(f"\t\t\t\t\t\tPoint position array shape: {fractional_min.shape}")

            # print(f"Grid position array shape: {position_array.shape}")
            # print(f"Grid position first element: {position_array[0, :]}")

            # Get the distances to the position
            distance_array = np.linalg.norm(
                points_position_array - position_array[j, :],
                axis=1,
            )
            # print(f"Distance array shape: {distance_array.shape}")
            # print(f"Distance array first element: {distance_array[0]}")

            # Mask the points on distances
            points_within_radius = grid_point_array[distance_array < radius]
            positions_within_radius = points_position_array[distance_array < radius]
            point_arrays.append(points_within_radius.astype(int))
            position_arrays.append(positions_within_radius)
        # print(f"Had {grid_point_array.shape} points, of which {points_within_radius.shape} within radius")

        # Bounding box orth
        # orth_bounds_min = np.min(positions_within_radius, axis=0)
        # orth_bounds_max = np.max(positions_within_radius, axis=0)
        # point_bounds_min = np.min(points_within_radius, axis=0)
        # point_bounds_max = np.max(points_within_radius, axis=0)
        #
        # print(f"Original position was: {position.x} {position.y} {position.z}")
        # print(f"Orth bounding box min: {orth_bounds_min}")
        # print(f"Orth bounding box max: {orth_bounds_max}")
        # print(f"Point bounding box min: {point_bounds_min}")
        # print(f"Point bounding box max: {point_bounds_max}")
        # print(f"First point pos pair: {points_within_radius[0, :]} {positions_within_radius[0, :]}")
        # print(f"Last point pos pair: {points_within_radius[-1, :]} {positions_within_radius[-1, :]}")

        return point_arrays, position_arrays

    # @staticmethod
    # def get_grid_points_around_protein(st: StructureInterface, grid, indicies, radius, processor: ProcessorInterface):
    #     # point_arrays = []
    #     # position_arrays = []
    #     #
    #     # time_begin_orth = time.time()
    #     # pos_array_3d = np.zeros((3, grid.nu, grid.nv, grid.nw))
    #     # print(np.max(pos_array_3d))
    #     #
    #     # # np.array(grid.unit_cell.orthogonalization_matrix.tolist()),
    #     # point_orthogonalization_matrix = np.matmul(
    #     #     np.array(grid.unit_cell.orthogonalization_matrix.tolist()),
    #     #     np.diag((1 / grid.nu, 1 / grid.nv, 1 / grid.nw,))
    #     # )
    #     # indicies_point_array = np.vstack(indicies)
    #     # print(f"\t\t\t\t\tindicies_point_array shape: {indicies_point_array.shape}")
    #     #
    #     # pos_array = np.matmul(point_orthogonalization_matrix, indicies_point_array)
    #     # print(f"\t\t\t\t\tPos array shape: {pos_array.shape}")
    #     # print(pos_array_3d[0][indicies].shape)
    #     # pos_array_3d[0][indicies] = pos_array[0, :]
    #     # pos_array_3d[1][indicies] = pos_array[1, :]
    #     # pos_array_3d[2][indicies] = pos_array[2, :]
    #     # print(np.max(pos_array_3d))
    #     # #
    #     # pos_array_3d_ref = processor.put(pos_array_3d)
    #     # time_finish_orth = time.time()
    #     # print(
    #     #     f"\t\t\t\tOrthogonalized mask positions in {round(time_finish_orth - time_begin_orth, 1)} to shape {pos_array.shape}")
    #
    #     begin = time.time()
    #     positions = []
    #
    #     for atom in st.protein_atoms():
    #         pos = atom.pos
    #         positions.append([pos.x, pos.y, pos.z])
    #         # point_array, position_array = PointPositionArray.get_nearby_grid_points(
    #         #     grid,
    #         #     atom.pos,
    #         #     radius
    #         # )
    #         # point_arrays.append(point_array)
    #         # position_arrays.append(position_array)
    #
    #     pos_array = np.array(positions)
    #
    #     spacing = np.array([grid.nu, grid.nv, grid.nw])
    #     fractionalization_matrix = np.array(grid.unit_cell.fractionalization_matrix.tolist())
    #
    #     time_begin_make_array = time.time()
    #     pos_max = np.max(pos_array, axis=0) + radius
    #     pos_min = np.min(pos_array, axis=0) - radius
    #
    #     corners = []
    #     for x, y, z in itertools.product(
    #             [pos_min[0], pos_max[0]],
    #             [pos_min[1], pos_max[1]],
    #             [pos_min[2], pos_max[2]],
    #
    #     ):
    #         corner = PointPositionArray.fractionalize_orthogonal_array_mat(
    #             np.array([x, y, z]).reshape((1, 3)),
    #             fractionalization_matrix,
    #         )
    #         corners.append(corner)
    #
    #     corner_array = np.vstack(corners)
    #     print(f"Corner shape is: {corner_array.shape}")
    #     print(f"Spacing shape is: {spacing}"
    #           )
    #
    #
    #     fractional_min = np.min(corner_array, axis=0)
    #     fractional_max = np.max(corner_array, axis=0)
    #
    #     u0 = np.floor(fractional_min[0] * spacing[0])
    #     u1 = np.ceil(fractional_max[0] * spacing[0])
    #     v0 = np.floor(fractional_min[1] * spacing[1])
    #     v1 = np.ceil(fractional_max[1] * spacing[1])
    #     w0 = np.floor(fractional_min[2] * spacing[2])
    #     w1 = np.ceil(fractional_max[2] * spacing[2])
    #
    #     # print(f"Fractional bounds are: u: {u0} {u1} : v: {v0} {v1} : w: {w0} {w1}")
    #
    #     # Get the grid points
    #     time_begin_itertools = time.time()
    #     # grid_point_array = np.array(
    #     #     [
    #     #         xyz_tuple
    #     #         for xyz_tuple
    #     #         in itertools.product(
    #     #         np.arange(u0, u1 + 1),
    #     #         np.arange(v0, v1 + 1),
    #     #         np.arange(w0, w1 + 1),
    #     #     )
    #     #     ]
    #     # )
    #     mgrid = np.mgrid[u0:u1 + 1, v0: v1 + 1, w0:w1 + 1].astype(int)
    #
    #     # grid_point_array = np.hstack([grid[_j].reshape((-1, 1)) for _j in (0, 1, 2)])
    #     grid_point_indicies = [mgrid[_j].reshape((-1, 1)) for _j in (0, 1, 2)]
    #
    #     time_finish_itertools = time.time()
    #     print(
    #         f"\t\t\t\t\t\tGot grid array in {round(time_finish_itertools - time_begin_itertools, 1)} of shape {mgrid.shape}")
    #
    #     # print(f"Grid point array shape: {grid_point_array.shape}")
    #     # print(f"Grid point first element: {grid_point_array[0, :]}")
    #
    #     # Get the grid points in the mask
    #     shifted_grid_point_indicies = tuple(np.mod(grid_point_indicies[_j], spacing[_j]) for _j in (0,1,2))
    #     mask_array = np.zeros(spacing, dtype=np.bool)
    #     mask_array[indicies] = True
    #     indicies_mask = mask_array[shifted_grid_point_indicies]
    #
    #     grid_point_array = np.vstack([grid_point_indicies[_j][indicies_mask] for _j in (0,1,2)]).astype(np.int)
    #
    #     point_orthogonalization_matrix = np.matmul(
    #         np.array(grid.unit_cell.orthogonalization_matrix.tolist()),
    #         np.diag((1 / grid.nu, 1 / grid.nv, 1 / grid.nw,))
    #     )
    #     # indicies_point_array = np.vstack(indicies)
    #
    #     unique_points = np.hstack(
    #         [shifted_grid_point_indicies[_j][indicies_mask].reshape((-1, 1))
    #          for _j
    #          in (0,1,2)]
    #     ).astype(np.int)
    #
    #     time_begin_mult = time.time()
    #     unique_positions = np.matmul(point_orthogonalization_matrix, grid_point_array).T
    #     time_finish_mult = time.time()
    #     print(f"\t\t\t\t\t\t Points to positions in : {round(time_finish_mult-time_begin_mult, 1)}")
    #
    #     time_finish_make_array = time.time()
    #
    #     print(f"\t\t\t\t\t Got point and pos array in {np.round(time_finish_make_array-time_begin_make_array,1)}")
    #     print(f"\t\t\t\t\t With shapes {unique_points.shape} {unique_positions.shape}")
    #     print(f"\t\t\t\t\t Vs mask size {indicies[0].shape}")
    #     print(unique_points)
    #     print(unique_positions)
    #
    #     return unique_points, unique_positions

    # all_point_array = grid

    @staticmethod
    def get_grid_points_around_protein(st: StructureInterface, grid, radius, processor: ProcessorInterface):

        begin = time.time()
        positions = []

        point_orthogonalization_matrix = np.matmul(
            np.array(grid.unit_cell.orthogonalization_matrix.tolist()),
            np.diag((1 / grid.nu, 1 / grid.nv, 1 / grid.nw,))
        )

        for atom in st.protein_atoms():
            pos = atom.pos
            positions.append([pos.x, pos.y, pos.z])
            # point_array, position_array = PointPositionArray.get_nearby_grid_points(
            #     grid,
            #     atom.pos,
            #     radius
            # )
            # point_arrays.append(point_array)
            # position_arrays.append(position_array)

        pos_array = np.array(positions)

        spacing = np.array([grid.nu, grid.nv, grid.nw])
        fractionalization_matrix = np.array(grid.unit_cell.fractionalization_matrix.tolist())

        time_begin_make_array = time.time()
        pos_max = np.max(pos_array, axis=0) + radius
        pos_min = np.min(pos_array, axis=0) - radius

        corners = []
        for x, y, z in itertools.product(
                [pos_min[0], pos_max[0]],
                [pos_min[1], pos_max[1]],
                [pos_min[2], pos_max[2]],

        ):
            corner = PointPositionArray.fractionalize_orthogonal_array_mat(
                np.array([x, y, z]).reshape((1, 3)),
                fractionalization_matrix,
            )
            corners.append(corner)

        corner_array = np.vstack(corners)
        print(f"Corner shape is: {corner_array.shape}")
        print(f"Spacing shape is: {spacing}"
              )

        fractional_min = np.min(corner_array, axis=0)
        fractional_max = np.max(corner_array, axis=0)

        u0 = int(np.floor(fractional_min[0] * spacing[0]))
        u1 = int(np.ceil(fractional_max[0] * spacing[0]))
        v0 = int(np.floor(fractional_min[1] * spacing[1]))
        v1 = int(np.ceil(fractional_max[1] * spacing[1]))
        w0 = int(np.floor(fractional_min[2] * spacing[2]))
        w1 = int(np.ceil(fractional_max[2] * spacing[2]))

        # print(f"Fractional bounds are: u: {u0} {u1} : v: {v0} {v1} : w: {w0} {w1}")

        # Get the grid points
        time_begin_itertools = time.time()

        mgrid = np.mgrid[u0:u1 + 1, v0: v1 + 1, w0:w1 + 1].astype(int)

        # grid_point_array = np.hstack([grid[_j].reshape((-1, 1)) for _j in (0, 1, 2)])
        grid_point_indicies = [mgrid[_j].reshape((-1, 1)) for _j in (0, 1, 2)]

        time_finish_itertools = time.time()
        print(
            f"\t\t\t\t\t\tGot grid array in {round(time_finish_itertools - time_begin_itertools, 1)} of shape {mgrid.shape}")

        # print(f"Grid point array shape: {grid_point_array.shape}")
        # print(f"Grid point first element: {grid_point_array[0, :]}")

        # Get and mask a transformed structure
        offset_cart = -np.matmul(point_orthogonalization_matrix, np.array([u0, v0, w0]).reshape((3, 1))).flatten()
        print(f"\t\t\t\t\t\tOffset is: {offset_cart}")
        shape = mgrid[0].shape
        # new_grid = gemmi.FloatGrid(*shape)

        new_unit_cell = gemmi.UnitCell(
            shape[0] * (grid.unit_cell.a / grid.nu),
            shape[1] * (grid.unit_cell.b / grid.nv),
            shape[2] * (grid.unit_cell.c / grid.nw),
            grid.unit_cell.alpha,
            grid.unit_cell.beta,
            grid.unit_cell.gamma,
        )

        new_structure = transform_structure_to_unit_cell(
            st,
            new_unit_cell,
            offset_cart
        )

        # Outer mask
        outer_mask = gemmi.Int8Grid(*shape)
        outer_mask.spacegroup = gemmi.find_spacegroup_by_name("P 1")
        outer_mask.set_unit_cell(
            new_unit_cell
        )

        outer_mask.set_unit_cell(grid.unit_cell)
        for atom in new_structure.protein_atoms():
            pos = atom.pos
            outer_mask.set_points_around(
                pos,
                radius=radius,
                value=1,
            )
        outer_mask_array = np.array(outer_mask, copy=False, dtype=np.int8)
        outer_indicies = np.nonzero(outer_mask_array)
        outer_indicies_native = (
            np.mod(outer_indicies[0] + u0, grid.nu),
            np.mod(outer_indicies[1] + v0, grid.nv),
            np.mod(outer_indicies[2] + w0, grid.nw),
        )
        indicies_min = [
            np.min(outer_indicies_native[0]),
            np.min(outer_indicies_native[1]),
            np.min(outer_indicies_native[2]),
        ]
        indicies_max = [
            np.max(outer_indicies_native[0]),
            np.max(outer_indicies_native[1]),
            np.max(outer_indicies_native[2]),
        ]
        print(f"\t\t\t\t\t\tOuter indicies native from {indicies_min} to {indicies_max}")

        inner_mask = gemmi.Int8Grid(*shape)
        inner_mask.spacegroup = gemmi.find_spacegroup_by_name("P 1")
        inner_mask.set_unit_cell(grid.unit_cell)
        for atom in new_structure.protein_atoms():
            pos = atom.pos
            inner_mask.set_points_around(
                pos,
                radius=radius,
                value=1,
            )
        inner_mask_array = np.array(outer_mask, copy=False, dtype=np.int8)
        inner_indicies = np.nonzero(inner_mask_array)
        inner_indicies_native = (
            np.mod(inner_indicies[0] + u0, grid.nu),
            np.mod(inner_indicies[1] + v0, grid.nv),
            np.mod(inner_indicies[2] + w0, grid.nw),
        )
        indicies_min = [
            np.min(inner_indicies_native[0]),
            np.min(inner_indicies_native[1]),
            np.min(inner_indicies_native[2]),
        ]
        indicies_max = [
            np.max(inner_indicies_native[0]),
            np.max(inner_indicies_native[1]),
            np.max(inner_indicies_native[2]),
        ]
        print(f"\t\t\t\t\t\tInner indicies native from {indicies_min} to {indicies_max}")

        sparse_inner_indicies = inner_mask_array[outer_indicies] == 1

        inner_atomic_mask = gemmi.Int8Grid(*shape)
        inner_atomic_mask.spacegroup = gemmi.find_spacegroup_by_name("P 1")
        inner_atomic_mask.set_unit_cell(grid.unit_cell)
        for atom in new_structure.protein_atoms():
            pos = atom.pos
            inner_atomic_mask.set_points_around(
                pos,
                radius=radius,
                value=1,
            )
        inner_atomic_mask_array = np.array(outer_mask, copy=False, dtype=np.int8)
        inner_atomic_indicies = np.nonzero(inner_atomic_mask_array)
        inner_atomic_indicies_native = (
            np.mod(inner_atomic_indicies[0] + u0, grid.nu),
            np.mod(inner_atomic_indicies[1] + v0, grid.nv),
            np.mod(inner_atomic_indicies[2] + w0, grid.nw),
        )
        indicies_min = [
            np.min(inner_atomic_indicies_native[0]),
            np.min(inner_atomic_indicies_native[1]),
            np.min(inner_atomic_indicies_native[2]),
        ]
        indicies_max = [
            np.max(inner_atomic_indicies_native[0]),
            np.max(inner_atomic_indicies_native[1]),
            np.max(inner_atomic_indicies_native[2]),
        ]
        print(f"\t\t\t\t\t\tInner atomic indicies native from {indicies_min} to {indicies_max}")

        sparse_inner_atomic_indicies = inner_atomic_mask_array[outer_indicies] == 1
        # indicies = np.nonzero(mask_array)

        all_indicies = {
            "outer": outer_indicies_native,
            "inner": inner_indicies_native,
            "inner_sparse": sparse_inner_indicies,
            "atomic": inner_atomic_indicies_native,
            "atomic_sparse": sparse_inner_atomic_indicies
        }

        # Get the grid points in the mask
        # shifted_grid_point_indicies = tuple(np.mod(grid_point_indicies[_j], spacing[_j]) for _j in (0, 1, 2))
        shifted_grid_point_indicies = tuple(
            (grid_point_indicies[_j] - np.array([u0, v0, w0]).astype(np.int)[_j]).flatten()
            for _j
            in (0, 1, 2)
        )

        print(f"\t\t\t\t\t\tMask array shape: {outer_mask_array.shape}")
        print(f"\t\t\t\t\t\tRange: {[u0, v0, w0]} : {[u1, v1, w1]}")

        # mask_array = np.zeros(shape, dtype=np.bool)
        # mask_array[indicies] = True
        grid_point_indicies_mask = outer_mask_array[shifted_grid_point_indicies] == 1
        print(f"\t\t\t\t\t\tGrid point Indicies mask shape: {grid_point_indicies_mask.shape}")

        grid_point_array = np.vstack(
            [
                grid_point_indicies[_j][grid_point_indicies_mask].flatten()
                for _j
                in (0, 1, 2)
            ]
        ).astype(np.int)
        print(f"\t\t\t\t\t\tGrid point array shape: {grid_point_array.shape}")

        # indicies_point_array = np.vstack(indicies)

        # unique_points = np.hstack(
        #     [grid_point_indicies[_j][grid_point_indicies_mask].reshape((-1, 1))
        #      for _j
        #      in (0, 1, 2)]
        # ).astype(np.int)
        unique_points = grid_point_array.T

        time_begin_mult = time.time()
        unique_positions = np.matmul(point_orthogonalization_matrix, grid_point_array).T
        time_finish_mult = time.time()
        print(f"\t\t\t\t\t\t Points to positions in : {round(time_finish_mult - time_begin_mult, 1)}")

        time_finish_make_array = time.time()

        print(f"\t\t\t\t\t Got point and pos array in {np.round(time_finish_make_array - time_begin_make_array, 1)}")
        print(f"\t\t\t\t\t With shapes {unique_points.shape} {unique_positions.shape}")
        print(f"\t\t\t\t\t Vs mask size {outer_indicies[0].shape}")
        print(unique_points)
        print(unique_positions)

        return unique_points, unique_positions, all_indicies

        # # Get the point positions
        # time_begin_pointpos = time.time()
        # mod_point_array = np.mod(grid_point_array, spacing)
        # mod_point_indexes = (mod_point_array[:, 0].flatten(), mod_point_array[:, 1].flatten(), mod_point_array[:, 2].flatten())
        # position_array = np.zeros(grid_point_array.shape)
        # print(f"\t\t\t\t\t\tInitial position array shape: {position_array.shape}")
        #
        # position_array[:, 0] = pos_array[0][mod_point_indexes]
        # position_array[:, 1] = pos_array[1][mod_point_indexes]
        # position_array[:, 2] = pos_array[2][mod_point_indexes]
        #
        # # position_array = pos_array[:, , ].T
        #
        # time_finish_pointpos = time.time()
        # print(
        #     f"\t\t\t\t\t\tTransformed points to pos in {round(time_finish_pointpos - time_begin_pointpos, 1)} to shape {position_array.shape}")
        #
        # time_finish = time.time()
        # print(
        #     f"\t\t\t\t\tGot pos array of shape {positions_within_radius.shape} in {round(time_finish - time_begin, 1)}")
        #
        # # point_position_arrays = processor(
        # #     [
        # #         Partial(PointPositionArray.get_nearby_grid_points_parallel).paramaterise(
        # #             [grid.nu, grid.nv, grid.nw],
        # #             np.array(grid.unit_cell.fractionalization_matrix.tolist()),
        # #             np.array(grid.unit_cell.orthogonalization_matrix.tolist()),
        # #             pos_array_3d_ref,
        # #             atom_positions[j, :],
        # #             radius,
        # #         )
        # #         for j
        # #         in range(atom_positions.shape[0])
        # #     ]
        # # )
        #
        #
        #
        # # point_arrays, position_arrays = PointPositionArray.get_nearby_grid_points_vectorized(grid, atom_positions, radius)
        # # for j in range(atom_positions.shape[0]):
        # #     point_array, position_array = PointPositionArray.get_nearby_grid_points_parallel(
        # #         [grid.nu, grid.nv, grid.nw],
        # #         np.array(grid.unit_cell.fractionalization_matrix.tolist()),
        # #         np.array(grid.unit_cell.orthogonalization_matrix.tolist()),
        # #         atom_positions[j, :],
        # #         radius
        # #     )
        # for point_position_array in point_position_arrays:
        #     point_arrays.append(point_position_array[0])
        #     position_arrays.append(point_position_array[1])
        #
        # finish = time.time()
        # print(f"\t\t\t\tGot nearby grid point position arrays in: {finish - begin}")
        #
        # _all_points_array = np.concatenate(point_arrays, axis=0)
        # all_points_array = _all_points_array - np.min(_all_points_array, axis=0).reshape((1, 3))
        # all_positions_array = np.concatenate(position_arrays, axis=0)
        #
        # # print(f"All points shape: {all_points_array.shape}")
        # # print(f"All positions shape: {all_positions_array.shape}")
        #
        # begin = time.time()
        # # unique_points, indexes = np.unique(all_points_array, axis=0, return_index=True)
        # all_point_indexes = (all_points_array[:, 0], all_points_array[:, 1], all_points_array[:, 2],)
        # shape = (np.max(all_points_array, axis=0) - np.min(all_points_array, axis=0)) + 1
        # point_3d_array = np.zeros((shape[0], shape[1], shape[2]), dtype=bool)
        # point_3d_array[all_point_indexes] = True
        # initial_unique_points = np.argwhere(point_3d_array)
        # unique_points = initial_unique_points + np.min(_all_points_array, axis=0).reshape((1, 3))
        # unique_points_indexes = (initial_unique_points[:, 0], initial_unique_points[:, 1], initial_unique_points[:, 2],)
        # pos_3d_arr_x = np.zeros((shape[0], shape[1], shape[2]))
        # pos_3d_arr_y = np.zeros((shape[0], shape[1], shape[2]))
        # pos_3d_arr_z = np.zeros((shape[0], shape[1], shape[2]))
        #
        # pos_3d_arr_x[all_point_indexes] = all_positions_array[:, 0]
        # pos_3d_arr_y[all_point_indexes] = all_positions_array[:, 1]
        # pos_3d_arr_z[all_point_indexes] = all_positions_array[:, 2]
        # unique_positions = np.hstack(
        #     [
        #         pos_3d_arr_x[unique_points_indexes].reshape((-1, 1)),
        #         pos_3d_arr_y[unique_points_indexes].reshape((-1, 1)),
        #         pos_3d_arr_z[unique_points_indexes].reshape((-1, 1)),
        #     ]
        # )
        #
        # finish = time.time()
        # print(
        #     f"\t\t\t\tGot unique points in: {finish - begin} with point shape {unique_points.shape} and pos shape {unique_positions.shape}")
        #
        # # unique_positions = all_positions_array[indexes, :]
        # # print(f"Unique points shape: {unique_points.shape}")
        # # print(f"Unique positions shape: {unique_positions.shape}")
        #
        # return unique_points, unique_positions

    # @staticmethod
    # def get_grid_points_around_protein(st: StructureInterface, grid, indicies, radius, processor: ProcessorInterface):
    #     point_arrays = []
    #     position_arrays = []
    #
    #     time_begin_orth = time.time()
    #     pos_array_3d = np.zeros((3, grid.nu, grid.nv, grid.nw))
    #     print(np.max(pos_array_3d))
    #
    #     # np.array(grid.unit_cell.orthogonalization_matrix.tolist()),
    #     point_orthogonalization_matrix = np.matmul(
    #         np.array(grid.unit_cell.orthogonalization_matrix.tolist()),
    #         np.diag((1 / grid.nu, 1 / grid.nv, 1 / grid.nw,))
    #     )
    #     indicies_point_array = np.vstack(indicies)
    #     print(f"\t\t\t\t\tindicies_point_array shape: {indicies_point_array.shape}")
    #
    #     pos_array = np.matmul(point_orthogonalization_matrix, indicies_point_array)
    #     print(f"\t\t\t\t\tPos array shape: {pos_array.shape}")
    #     print(pos_array_3d[0][indicies].shape)
    #     pos_array_3d[0][indicies] = pos_array[0, :]
    #     pos_array_3d[1][indicies] = pos_array[1, :]
    #     pos_array_3d[2][indicies] = pos_array[2, :]
    #     print(np.max(pos_array_3d))
    #     #
    #     pos_array_3d_ref = processor.put(pos_array_3d)
    #     time_finish_orth = time.time()
    #     print(f"\t\t\t\tOrthogonalized mask positions in {round(time_finish_orth-time_begin_orth, 1)} to shape {pos_array.shape}")
    #
    #     begin = time.time()
    #     positions = []
    #
    #     for atom in st.protein_atoms():
    #         pos = atom.pos
    #         positions.append([pos.x, pos.y, pos.z])
    #         # point_array, position_array = PointPositionArray.get_nearby_grid_points(
    #         #     grid,
    #         #     atom.pos,
    #         #     radius
    #         # )
    #         # point_arrays.append(point_array)
    #         # position_arrays.append(position_array)
    #
    #     atom_positions = np.array(positions)
    #
    #     point_position_arrays = processor(
    #         [
    #             Partial(PointPositionArray.get_nearby_grid_points_parallel).paramaterise(
    #                 [grid.nu, grid.nv, grid.nw],
    #                 np.array(grid.unit_cell.fractionalization_matrix.tolist()),
    #                 np.array(grid.unit_cell.orthogonalization_matrix.tolist()),
    #                 pos_array_3d_ref,
    #                 atom_positions[j, :],
    #                 radius,
    #             )
    #             for j
    #             in range(atom_positions.shape[0])
    #         ]
    #     )
    #
    #     # point_arrays, position_arrays = PointPositionArray.get_nearby_grid_points_vectorized(grid, atom_positions, radius)
    #     # for j in range(atom_positions.shape[0]):
    #     #     point_array, position_array = PointPositionArray.get_nearby_grid_points_parallel(
    #     #         [grid.nu, grid.nv, grid.nw],
    #     #         np.array(grid.unit_cell.fractionalization_matrix.tolist()),
    #     #         np.array(grid.unit_cell.orthogonalization_matrix.tolist()),
    #     #         atom_positions[j, :],
    #     #         radius
    #     #     )
    #     for point_position_array in point_position_arrays:
    #         point_arrays.append(point_position_array[0])
    #         position_arrays.append(point_position_array[1])
    #
    #     finish = time.time()
    #     print(f"\t\t\t\tGot nearby grid point position arrays in: {finish - begin}")
    #
    #     _all_points_array = np.concatenate(point_arrays, axis=0)
    #     all_points_array = _all_points_array - np.min(_all_points_array, axis=0).reshape((1, 3))
    #     all_positions_array = np.concatenate(position_arrays, axis=0)
    #
    #     # print(f"All points shape: {all_points_array.shape}")
    #     # print(f"All positions shape: {all_positions_array.shape}")
    #
    #     begin = time.time()
    #     # unique_points, indexes = np.unique(all_points_array, axis=0, return_index=True)
    #     all_point_indexes = (all_points_array[:, 0], all_points_array[:, 1], all_points_array[:, 2],)
    #     shape = (np.max(all_points_array, axis=0) - np.min(all_points_array, axis=0)) + 1
    #     point_3d_array = np.zeros((shape[0], shape[1], shape[2]), dtype=bool)
    #     point_3d_array[all_point_indexes] = True
    #     initial_unique_points = np.argwhere(point_3d_array)
    #     unique_points = initial_unique_points + np.min(_all_points_array, axis=0).reshape((1, 3))
    #     unique_points_indexes = (initial_unique_points[:, 0], initial_unique_points[:, 1], initial_unique_points[:, 2],)
    #     pos_3d_arr_x = np.zeros((shape[0], shape[1], shape[2]))
    #     pos_3d_arr_y = np.zeros((shape[0], shape[1], shape[2]))
    #     pos_3d_arr_z = np.zeros((shape[0], shape[1], shape[2]))
    #
    #     pos_3d_arr_x[all_point_indexes] = all_positions_array[:, 0]
    #     pos_3d_arr_y[all_point_indexes] = all_positions_array[:, 1]
    #     pos_3d_arr_z[all_point_indexes] = all_positions_array[:, 2]
    #     unique_positions = np.hstack(
    #         [
    #             pos_3d_arr_x[unique_points_indexes].reshape((-1, 1)),
    #             pos_3d_arr_y[unique_points_indexes].reshape((-1, 1)),
    #             pos_3d_arr_z[unique_points_indexes].reshape((-1, 1)),
    #         ]
    #     )
    #
    #     finish = time.time()
    #     print(
    #         f"\t\t\t\tGot unique points in: {finish - begin} with point shape {unique_points.shape} and pos shape {unique_positions.shape}")
    #
    #     # unique_positions = all_positions_array[indexes, :]
    #     # print(f"Unique points shape: {unique_points.shape}")
    #     # print(f"Unique positions shape: {unique_positions.shape}")
    #
    #     return unique_points, unique_positions

    @classmethod
    def from_structure(cls, st: StructureInterface, grid, processor, radius: float = 6.0):
        point_array, position_array, all_indicies = PointPositionArray.get_grid_points_around_protein(st, grid, radius,
                                                                                                      processor)
        return PointPositionArray(point_array, position_array), all_indicies


class GridPartitioning(GridPartitioningInterface):
    def __init__(self, partitions):
        self.partitions = partitions
        # for resid, point_pos_array in self.partitions.items():
        #     print(f"{resid} : {point_pos_array.points.shape}")
        # exit()

    @classmethod
    def from_dataset(cls, dataset, grid, processor):
        # Get the structure array
        st_array = StructureArray.from_structure(dataset.structure)
        print(f"Structure array shape: {st_array.positions.shape}")

        # CA point_position_array
        used_insertions = []
        ca_mask = []
        for j, atom_id in enumerate(st_array.atom_ids):
            key = (st_array.chains[j], st_array.seq_ids[j])
            if (key not in used_insertions) and contains(str(atom_id).upper(), "CA"):
                ca_mask.append(True)
                used_insertions.append(key)
            else:
                ca_mask.append(False)

        begin = time.time()
        ca_point_position_array = st_array.mask(np.array(ca_mask))
        finish = time.time()
        print(f"\t\t\tGot position array in : {finish - begin}")
        print(f"\t\t\tCA array shape: {ca_point_position_array.positions.shape}")

        # Get the tree
        begin = time.time()
        kdtree = scipy.spatial.KDTree(ca_point_position_array.positions)
        finish = time.time()
        print(f"\t\t\tBuilt tree in : {finish - begin}")

        # Get the point array
        begin = time.time()
        point_position_array, all_indicies = PointPositionArray.from_structure(dataset.structure, grid, processor)
        finish = time.time()
        print(f"\t\t\tGot point position array : {finish - begin}")

        # Get the NN indexes
        begin = time.time()
        distances, indexes = kdtree.query(point_position_array.positions, workers=12)
        finish = time.time()

        partitions = {
            ResidueID(
                ca_point_position_array.models[index],
                ca_point_position_array.chains[index],
                ca_point_position_array.seq_ids[index],
            ): PointPositionArray(
                point_position_array.points[indexes == index],
                point_position_array.positions[indexes == index]
            )
            for index
            in np.unique(indexes)
        }

        return cls(partitions, ), all_indicies
        # print(f"\t\t\tQueryed points in : {finish - begin}")
        # distance_mask = distances < 7.0
        # print(f"\t\t\tDistance masked points: {np.sum(distance_mask)} vs {distance_mask.size}")

        # uniques, inv, counts = np.unique(point_position_array.points[distance_mask], axis=0,return_inverse=True, return_counts=True)
        # multiple_point_unique_array_indicies = np.nonzero(counts > 1)
        # discarded_multiple_mask = np.zeros(indexes[distance_mask].shape, dtype=np.bool)
        # # print(f"Got {multiple_point_unique_array_indicies[0].size} multiple occupied points!")
        # masked_distances = distances[distance_mask]
        # for uniques_index in multiple_point_unique_array_indicies[0]:  # For each index of a point with a count > 1
        #     # print(uniques_index)
        #     # unique = uniques[uniques_index]
        #     inv_mask = inv == uniques_index  # Mask the points based on whether they are assigned to that unique
        #     # print(np.sum(inv_mask))
        #     inv_mask_indicies = np.nonzero(inv_mask)  # Get the array of indexes where
        #     # print(inv_mask_indicies[0].size)
        #     unique_distances = masked_distances[inv_mask_indicies]  # Select the distances associated with that point
        #     # print(f"{unique_distances}")
        #     min_dist_index = inv_mask_indicies[0][np.argmin(unique_distances) ] # Get index in the selection the minimum
        #     inv_mask[min_dist_index] = False  # Remove the closest point from the mask
        #     discarded_multiple_mask[inv_mask] = True
        #
        # included_points_mask = ~discarded_multiple_mask
        #
        # uniques, counts = np.unique(point_position_array.points[distance_mask][included_points_mask], axis=0,  return_counts=True)
        # assert np.all(counts == 1)

        # uniques, counts = np.unique(point_position_array.points[ distance_mask], axis=0, return_counts=True)
        #
        # assert np.all(counts == 1)

        # for index in np.unique(indexes):
        #     print([ca_point_position_array.models[index],
        #     ca_point_position_array.chains[index],
        #     ca_point_position_array.seq_ids[index]])
        #     print(point_position_array.points[(indexes == index) & distance_mask].size)
        #     print(point_position_array.positions[(indexes == index) & distance_mask].size)

        # Get partions
        # self.partitions = {
        #     ResidueID(
        #         ca_point_position_array.models[index],
        #         ca_point_position_array.chains[index],
        #         ca_point_position_array.seq_ids[index],
        #     ): PointPositionArray(
        #         point_position_array.points[distance_mask][(indexes[distance_mask] == index)  & included_points_mask],
        #         point_position_array.positions[distance_mask][(indexes[distance_mask] == index) & included_points_mask]
        #     )
        #     for index
        #     in np.unique(indexes)
        # }


class GridMask(GridMaskInterface):
    def __init__(self, indicies, indicies_inner, indicies_sparse_inner, indicies_inner_atomic,
                 indicies_sparse_inner_atomic):
        self.indicies = indicies
        self.indicies_inner = indicies_inner
        self.indicies_sparse_inner = indicies_sparse_inner
        self.indicies_inner_atomic = indicies_inner_atomic
        self.indicies_sparse_inner_atomic = indicies_sparse_inner_atomic

    @classmethod
    def from_dataset(cls, dataset: DatasetInterface, grid, mask_radius=6.0, mask_radius_inner=2.0):
        mask = gemmi.Int8Grid(*[grid.nu, grid.nv, grid.nw])
        mask.spacegroup = gemmi.find_spacegroup_by_name("P 1")
        mask.set_unit_cell(grid.unit_cell)
        for atom in dataset.structure.protein_atoms():
            pos = atom.pos
            mask.set_points_around(
                pos,
                radius=mask_radius,
                value=1,
            )
        mask_array = np.array(mask, copy=False, dtype=np.int8)
        indicies = np.nonzero(mask_array)

        mask = gemmi.Int8Grid(*[grid.nu, grid.nv, grid.nw])
        mask.spacegroup = gemmi.find_spacegroup_by_name("P 1")
        mask.set_unit_cell(grid.unit_cell)
        for atom in dataset.structure.protein_atoms():
            pos = atom.pos
            mask.set_points_around(
                pos,
                radius=mask_radius_inner,
                value=1,
            )
        mask_array = np.array(mask, copy=False, dtype=np.int8)
        indicies_inner = np.nonzero(mask_array)
        indicies_sparse_inner = mask_array[indicies] == 1.0

        mask = gemmi.Int8Grid(*[grid.nu, grid.nv, grid.nw])
        mask.spacegroup = gemmi.find_spacegroup_by_name("P 1")
        mask.set_unit_cell(grid.unit_cell)
        for atom in dataset.structure.protein_atoms():
            pos = atom.pos
            mask.set_points_around(
                pos,
                radius=0.5,
                value=1,
            )
        mask_array = np.array(mask, copy=False, dtype=np.int8)
        indicies_inner_atomic = np.nonzero(mask_array)
        indicies_sparse_inner_atomic = mask_array[indicies] == 1.0

        return cls(indicies, indicies_inner, indicies_sparse_inner, indicies_inner_atomic, indicies_sparse_inner_atomic)

    @classmethod
    def from_indicies(cls, all_indicies):
        return cls(
            all_indicies["outer"],
            all_indicies["inner"],
            all_indicies["inner_sparse"],
            all_indicies["atomic"],
            all_indicies["atomic_sparse"]
        )


def get_grid_from_dataset(dataset: DatasetInterface):
    return dataset.reflections.transform_f_phi_to_map()


class DFrame:
    def __init__(self, dataset: DatasetInterface, processor):
        # Get the grid
        grid = get_grid_from_dataset(dataset)

        # Get the grid parameters
        uc = grid.unit_cell
        self.unit_cell = (uc.a, uc.b, uc.c, uc.alpha, uc.beta, uc.gamma)
        self.spacegroup = gemmi.find_spacegroup_by_name("P 1").number
        self.spacing = (grid.nu, grid.nv, grid.nw)

        # Get the grid partitioning
        begin_partition = time.time()
        self.partitioning, all_indicies = GridPartitioning.from_dataset(dataset, grid, processor)
        finish_partition = time.time()
        print(f"\tGot Partitions in {finish_partition - begin_partition}")

        # Get the mask
        begin_mask = time.time()
        self.mask = GridMask.from_indicies(all_indicies)
        finish_mask = time.time()
        print(f"\tGot mask in {finish_mask - begin_mask}")

    def get_grid(self):
        grid = gemmi.FloatGrid(*self.spacing)
        grid.set_unit_cell(gemmi.UnitCell(*self.unit_cell))
        grid.spacegroup = gemmi.find_spacegroup_by_number(self.spacegroup)
        grid_array = np.array(grid, copy=False)
        grid_array[:, :, :] = 0.0
        return grid

    def unmask(self, sparse_dmap, ):
        grid = self.get_grid()
        grid_array = np.array(grid, copy=False)
        grid_array[self.mask.indicies] = sparse_dmap.data
        return grid

    def unmask_inner(self, sparse_dmap, ):
        grid = self.get_grid()
        grid_array = np.array(grid, copy=False)
        grid_array[self.mask.indicies_inner] = sparse_dmap.data
        return grid

    def mask_grid(self, grid):
        grid_array = np.array(grid, copy=False)
        data = grid_array[self.mask.indicies]
        return SparseDMap(data)

    def mask_inner(self, grid):
        grid_array = np.array(grid, copy=False)
        data = grid_array[self.mask.indicies_inner]
        return SparseDMap(data)
