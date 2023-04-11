import numpy as np
from sklearn.decomposition import PCA
from sklearn import mixture

from ..interfaces import *


def get_characterization_sets(
        dtag: str,
        datasets: Dict[str, DatasetInterface],
        dmaps: np.array,
        reference_frame: DFrameInterface,
        characterization_model,
        min_size: int = 25
):
    # Get the array of dataset dtags
    dtag_array = np.array([_dtag for _dtag in datasets])

    # Get the
    classes = characterization_model(dmaps, reference_frame)

    # Get the characterization sets from dmap mask
    characterization_sets = {}

    # Get the clusters and their membership numbers
    unique_classes, counts = np.unique(classes, return_counts=True)
    j = 0
    for unique_class, count in zip(unique_classes, counts):
        if count >= min_size:
            class_dtags = dtag_array[classes == unique_class]
            characterization_sets[j] = [str(_dtag) for _dtag in class_dtags]
            j = j + 1

    return characterization_sets


class CharacterizationGaussianMixture:
    def __init__(self, n_components=20, covariance_type="diag", ):
        self.n_components = n_components
        self.covariance_type = covariance_type

    def __call__(self, dmaps, reference_frame):
        # Get the inner mask of the density
        sparse_dmap_inner_array = dmaps[:, reference_frame.mask.indicies_sparse_inner]

        # Transform the data to a reasonable size for a GMM
        pca = PCA(n_components=min(100, min(sparse_dmap_inner_array.shape)), svd_solver="randomized")
        transformed = pca.fit_transform(sparse_dmap_inner_array)

        # Fit the Dirichlet Process Gaussian Mixture Model and predict component membership
        dpgmm = mixture.BayesianGaussianMixture(n_components=self.n_components, covariance_type=self.covariance_type)
        predicted = dpgmm.fit_predict(transformed)

        return predicted