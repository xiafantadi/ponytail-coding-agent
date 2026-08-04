from app import progress


def test_target_caps_overflow():
    assert progress(12, 10) == 100


def test_regression_half_complete():
    assert progress(5, 10) == 50


def test_regression_empty_progress():
    assert progress(0, 10) == 0
