import pandas as pd

from core.data import _statement_value, _statement_display


def test_statement_value_uses_latest_period():
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): [1200.0, 100.0],
            pd.Timestamp("2024-12-31"): [1000.0, 80.0],
        },
        index=["Total Revenue", "Net Income"],
    )
    value, period = _statement_value(frame, ("Total Revenue",))
    assert value == 1200.0
    assert period == "2025-12-31"


def test_statement_display_builds_financial_table():
    frame = pd.DataFrame(
        {pd.Timestamp("2025-12-31"): [1200.0]},
        index=["Total Revenue"],
    )
    result = _statement_display(
        frame,
        (("Chiffre d'affaires", ("Total Revenue",), False),),
    )
    assert not result.empty
    assert result.iloc[0]["Indicateur"] == "Chiffre d'affaires"
