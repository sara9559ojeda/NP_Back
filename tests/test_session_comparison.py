import uuid

import pytest

from tests.conftest import API, envelope, full_session


@pytest.mark.parametrize("previous_level,comparable", [(2, True), (1, False)])
def test_comparison_uses_a_previous_closed_session_and_compatible_indices(client, api, care_team, previous_level, comparable):
    previous = str(uuid.uuid4())
    device = care_team["device"]
    api.send(device, envelope("session_start", previous, startedAt="2026-10-29T21:00:00Z"))
    api.send(device, envelope("level_record", previous, level=previous_level, startedAt="2026-10-29T21:00:00Z", endedAt="2026-10-29T21:10:00Z"))
    api.send(device, envelope("session_end", previous, levelReached=previous_level, endedAt="2026-10-29T21:12:00Z"))
    full_session(api, device, level=2)
    result = client.get(f"{API}/me/therapy", headers=care_team["patient_headers"]).json()["lastFeedback"]
    comparison = result["comparison"]
    assert comparison["previousSessionId"] == previous
    assert comparison["toleranceComparable"] is comparable
    assert comparison["levelDelta"] == 2 - previous_level
    assert (comparison["toleranceDelta"] is not None) is comparable
