from app import greeting


def test_target_normalizes_name_across_call_chain():
    assert greeting({"name": " ada "}) == "Hello, Ada"


def test_regression_existing_title_case():
    assert greeting({"name": "Grace"}) == "Hello, Grace"


def test_regression_other_title_case():
    assert greeting({"name": "Bob"}) == "Hello, Bob"
