from core.economic_events import _parse_bls_html


def test_bls_html_fallback_parser():
    html = """
    <table>
      <tr>
        <th>Date</th><th>Time</th><th>Release</th>
      </tr>
      <tr>
        <td>Tuesday, June 16, 2026</td>
        <td>08:30 AM</td>
        <td>U.S. Import and Export Price Indexes for May 2026</td>
      </tr>
      <tr>
        <td>Wednesday, June 17, 2026</td>
        <td>11:00 AM</td>
        <td>Minor Regional Survey</td>
      </tr>
    </table>
    """
    frame = _parse_bls_html(html, 2026)

    assert len(frame) == 1
    assert frame.iloc[0]["Source"] == "BLS"
    assert frame.iloc[0]["Heure"] == "08:30"
    assert "Prix américains" in frame.iloc[0]["Événement"]
