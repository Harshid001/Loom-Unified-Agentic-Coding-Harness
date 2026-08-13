from scripts.load_slo_gate import percentile


def test_percentile_empty_returns_zero():
    assert percentile([], 0.95) == 0.0


def test_percentile_uses_sorted_values():
    values = [0.5, 0.1, 0.2, 0.9, 0.3]
    assert percentile(values, 0.50) == 0.3
    assert percentile(values, 0.95) == 0.9
