from core.universe import UNIVERSES, get_universe, normalise_tmx_symbol, seed_constituents


def test_universes_exist():
    assert {"tsx60", "tsx_composite", "tsx_full"}.issubset(UNIVERSES)
    assert get_universe("tsx60").snapshot_limit < get_universe("tsx_full").snapshot_limit


def test_symbol_normalisation():
    assert normalise_tmx_symbol("RY.TO") == "RY"
    assert normalise_tmx_symbol("TECK-B:TSX") == "TECK.B"


def test_seed_constituents():
    frame = seed_constituents("tsx_full")
    assert not frame.empty
    assert {"Ticker", "YahooTicker", "Secteur", "PoidsIndice"}.issubset(frame.columns)
