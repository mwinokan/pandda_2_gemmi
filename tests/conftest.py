import shutil
from pathlib import Path

import pytest

from pandda_gemmi import constants

@pytest.fixture()
def test_data():
    test_data_path = Path(constants.TEST_DATA_DIR)
    if test_data_path.exists():
        return test_data_path
    else:
        # TODO: Get
        ...

@pytest.fixture()
def integration_test_out_dir():
    path = Path('test')
    if path.exists():
        shutil.rmtree(path)

    return path
