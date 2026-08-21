from pandas.testing import assert_frame_equal

from binance_research.synthetic import generate_synthetic_bars


def test_synthetic_fixture_is_deterministic_and_labeled() -> None:
    first = generate_synthetic_bars(250, seed=11)
    second = generate_synthetic_bars(250, seed=11)
    assert_frame_equal(first, second)
    assert first["data_source"].eq("synthetic_non_evidentiary").all()

