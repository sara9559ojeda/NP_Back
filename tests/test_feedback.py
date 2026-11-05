"""Professional sequence diagram: review progress, consult feedback and annotate comments (v1.1.0)."""

import uuid

from tests.conftest import API, example, full_session


def test_professional_consults_feedback_per_session(client, api, care_team):
    pid, headers, device = care_team["patient"]["id"], care_team["pro_headers"], care_team["device"]
    first = full_session(api, device)
    second = full_session(api, device)
    full_session(api, device, test_session=True)  # test sessions have no feedback
    client.post(f"{API}/patients/{pid}/notes", json={"text": "Buen avance", "sessionId": first}, headers=headers)

    page = client.get(f"{API}/patients/{pid}/feedback", headers=headers).json()
    assert {item["sessionId"] for item in page["items"]} == {first, second}
    item = next(i for i in page["items"] if i["sessionId"] == first)
    assert item["notesCount"] == 1 and item["phobiaGrade"] == 3 and item["levelReached"] == 2
    assert item["analysis"]["recommendation"] in ("advance", "repeat", "step_back")
    assert {b["feature"] for b in item["analysis"]["basis"]} >= {"sudsDrop", "avoidanceCount"}


def test_feedback_is_paginated(client, api, care_team):
    pid, headers = care_team["patient"]["id"], care_team["pro_headers"]
    for _ in range(2):
        full_session(api, care_team["device"])
    first = client.get(f"{API}/patients/{pid}/feedback", params={"limit": 1}, headers=headers).json()
    assert len(first["items"]) == 1 and first["nextCursor"]
    rest = client.get(
        f"{API}/patients/{pid}/feedback", params={"limit": 1, "cursor": first["nextCursor"]}, headers=headers
    ).json()
    assert len(rest["items"]) == 1 and rest["nextCursor"] is None
    assert first["items"][0]["sessionId"] != rest["items"][0]["sessionId"]


def test_note_is_validated_before_saving(client, api, care_team):
    pid, headers = care_team["patient"]["id"], care_team["pro_headers"]
    assert client.post(f"{API}/patients/{pid}/notes", json={"text": "  "}, headers=headers).status_code == 422
    bad = client.post(f"{API}/patients/{pid}/notes", json={"text": "x", "sessionId": str(uuid.uuid4())}, headers=headers)
    assert bad.status_code == 422 and bad.json()["errors"] == [{"field": "sessionId", "code": "not_found"}]
    assert client.get(f"{API}/patients/{pid}/notes", headers=headers).json()["items"] == []


def test_saved_note_is_returned_as_confirmation(client, api, care_team):
    pid, headers = care_team["patient"]["id"], care_team["pro_headers"]
    session_id = full_session(api, care_team["device"])
    r = client.post(f"{API}/patients/{pid}/notes", json={"text": "Tolera el nivel 2", "sessionId": session_id}, headers=headers)
    assert r.status_code == 201
    note = r.json()
    assert set(note) == set(example("note.response.201.json"))
    assert note["text"] == "Tolera el nivel 2" and note["sessionId"] == session_id
    assert note["authorId"] == care_team["professional"]["id"]
    assert note["authorName"] == care_team["professional"]["fullName"]
    assert note["editedAt"] is None


def test_notes_can_be_filtered_by_session(client, api, care_team):
    pid, headers = care_team["patient"]["id"], care_team["pro_headers"]
    session_id = full_session(api, care_team["device"])
    note_id = client.post(
        f"{API}/patients/{pid}/notes", json={"text": "De la sesión", "sessionId": session_id}, headers=headers
    ).json()["noteId"]
    client.post(f"{API}/patients/{pid}/notes", json={"text": "General"}, headers=headers)

    filtered = client.get(f"{API}/patients/{pid}/notes", params={"sessionId": session_id}, headers=headers).json()
    assert [n["noteId"] for n in filtered["items"]] == [note_id]
    assert len(client.get(f"{API}/patients/{pid}/notes", headers=headers).json()["items"]) == 2
