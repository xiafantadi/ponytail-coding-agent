from app import display_label


def test_target_title_cases_words():
    assert display_label(" ada lovelace ") == "Ada Lovelace"


def test_regression_single_word():
    assert display_label("Grace") == "Grace"


def test_regression_trimmed_name():
    assert display_label("  Alan  ") == "Alan"
