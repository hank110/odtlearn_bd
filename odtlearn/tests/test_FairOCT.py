import numpy as np
import pytest
from numpy.testing import assert_allclose

from odtlearn.fair_oct import FairOCT
from odtlearn.flow_oct import FlowOCT


# fmt: off
@pytest.fixture
def synthetic_data_1():
    """
    This is the data we generate in this function
       X2                    |
       |                     |
       1    5W: 4(-) 1(+)    |     2W: 1(-) 1(+)
       |    2B: 2(-)         |     5B: 3(-) 2(+)
       |                     |
       |                     |
       |---------------------|------------------------
       |                     |
       0    4W: 3(-) 1(+)    |         3W: 1(-) 2(+)
       |    1B:      1(+)    |         6B: 1(-) 5(+)
       |                     |
       |___________0_________|__________1_____________X1
    """
    X = np.array(
        [
            [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [1, 0],
            [1, 0], [1, 0], [1, 0], [1, 0], [1, 0], [1, 0],
            [1, 0], [1, 0], [1, 1], [1, 1], [1, 1], [1, 1],
            [1, 1], [1, 1], [1, 1], [0, 1], [0, 1], [0, 1],
            [0, 1], [0, 1], [0, 1], [0, 1]
        ]
    )
    protect_feat = np.array(
        [
            0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0,
            0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 1,
        ]
    )
    y = np.array(
        [
            0, 0, 0, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1, 0,
            1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0,
        ]
    )

    protect_feat = protect_feat.reshape(-1, 1)
    # X = np.concatenate((X, P), axis=1)
    legit_factor = X[:, 1]

    return X, y, protect_feat, legit_factor


# fmt: on
def test_FairOCT_same_predictions(synthetic_data_1):
    X, y, protect_feat, legit_factor = synthetic_data_1
    fcl = FairOCT(
        positive_class=1,
        depth=2,
        _lambda=0,
        time_limit=100,
        fairness_type=None,
        fairness_bound=1,
        num_threads=None,
        obj_mode="acc",
    )

    stcl = FlowOCT(
        depth=2,
        time_limit=100,
        _lambda=0,
        num_threads=None,
        obj_mode="acc",
    )

    stcl.fit(X, y)
    stcl_pred = stcl.predict(X)

    fcl.fit(X, y, protect_feat, legit_factor)
    fcl_pred = fcl.predict(X)

    assert_allclose(fcl_pred, stcl_pred)


@pytest.mark.parametrize(
    "f, b, g0_value",
    [("SP", 1, 0.214), ("SP", 0.2, 0.5), ("PE", 1, 0.111), ("PE", 0.04, 0)],
)
def test_FairOCT_metrics(synthetic_data_1, f, b, g0_value):
    X, y, protect_feat, legit_factor = synthetic_data_1
    fcl = FairOCT(
        positive_class=1,
        depth=2,
        _lambda=0,
        time_limit=100,
        fairness_type=f,
        fairness_bound=b,
        num_threads=None,
        obj_mode="acc",
    )

    fcl.fit(X, y, protect_feat, legit_factor)
    if f == "SP":
        sp_val = fcl.get_SP(protect_feat, fcl.predict(X))
        assert_allclose(np.round(sp_val[(0, 1)], 3), g0_value)
    elif f == "PE":
        eq_val = fcl.get_EqOdds(protect_feat, y, fcl.predict(X))
        assert_allclose(np.round(eq_val[(0, 0, 1)], 3), g0_value)
