from core.universe import default_limits, get_universe


def test_render_starter_limits_are_progressive():
    assert get_universe("tsx60").snapshot_limit <= get_universe("tsx_composite").snapshot_limit
    assert get_universe("tsx_full").snapshot_limit >= 100
    assert default_limits("tsx_full")[1] <= default_limits("tsx_full")[0]
