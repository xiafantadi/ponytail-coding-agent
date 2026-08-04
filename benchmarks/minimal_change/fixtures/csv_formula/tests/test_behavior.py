from app import export_value


def test_target_escapes_formula_prefix():
    assert export_value("=SUM(A1:A2)") == "'=SUM(A1:A2)"


def test_regression_keeps_plain_text():
    assert export_value("Ada") == "Ada"


def test_regression_keeps_numeric_text():
    assert export_value("42") == "42"
