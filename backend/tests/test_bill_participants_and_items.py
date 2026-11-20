"""Decisions of 2026-11-20, end to end through the API:

  - per-bill participants (who was at the meal) scope predictions, tax/tip
    and settlement, and can be removed from just one bill;
  - shared items via PUT .../items/{id}/assignees;
  - the group creator is auto-added as a claimed member;
  - items are editable while a bill is in needs_review;
plus the small endpoints the web app needs around them (switch to manual
entry, receipt image URL, bill-scoped payer suggestion, delete bill,
taxonomy scores)."""

import uuid
from decimal import Decimal

import httpx
import pytest

from app.core.config import settings
from app.models.person_taxonomy_score import PersonTaxonomyScore
from app.models.prediction_feedback import PredictionFeedback
from app.models.taxonomy import TaxonomySource, TaxonomyValue
from app.models.user import User
from tests.auth_helpers import auth_headers


@pytest.fixture()
def ctx(client, db_session_factory):
    """A group (creator + Alice, Bob, Cara) and the creator's auth headers."""
    db = db_session_factory()
    creator = User(id=uuid.uuid4(), email="nan@example.com", display_name="Nan")
    db.add(creator)
    db.commit()
    creator_id = creator.id
    db.close()

    headers = auth_headers(creator_id)
    group = client.post("/api/v1/groups", json={"name": "Lunch"}, headers=headers).json()
    people = {}
    for name in ("Alice", "Bob", "Cara"):
        people[name] = client.post(
            f"/api/v1/groups/{group['id']}/people", json={"display_name": name}, headers=headers
        ).json()["id"]
    detail = client.get(f"/api/v1/groups/{group['id']}", headers=headers).json()
    me = next(p for p in detail["people"] if p["supabase_user_id"] == str(creator_id))
    return {
        "headers": headers,
        "creator_id": creator_id,
        "group_id": group["id"],
        "me": me["id"],
        **people,
    }


def _seed_score(db_session_factory, person_id: str, value: TaxonomyValue, score: float):
    db = db_session_factory()
    db.add(
        PersonTaxonomyScore(
            person_id=uuid.UUID(person_id),
            taxonomy_value=value,
            score=score,
            is_hard_restriction=False,
            source=TaxonomySource.QUESTIONNAIRE,
        )
    )
    db.commit()
    db.close()


def _manual_bill(client, ctx, participants=None, items=(("Burger", "10.00", "entree"),), tax=None):
    body = {"merchant_name": "Diner"}
    if participants is not None:
        body["participant_person_ids"] = participants
    bill = client.post(
        f"/api/v1/groups/{ctx['group_id']}/bills", json=body, headers=ctx["headers"]
    ).json()
    for name, price, base_type in items:
        payload = {"parsed_name": name, "price": price}
        if base_type:
            payload["base_type"] = base_type
        client.post(f"/api/v1/bills/{bill['id']}/items", json=payload, headers=ctx["headers"])
    if tax is not None:
        client.patch(f"/api/v1/bills/{bill['id']}", json={"tax_total": tax}, headers=ctx["headers"])
    client.post(f"/api/v1/bills/{bill['id']}/finalize-manual-entry", headers=ctx["headers"])
    return client.get(f"/api/v1/bills/{bill['id']}", headers=ctx["headers"]).json()


# --- creator auto-add --------------------------------------------------------


def test_creator_added_as_claimed_member_named_from_profile(client, ctx):
    detail = client.get(f"/api/v1/groups/{ctx['group_id']}", headers=ctx["headers"]).json()
    me = next(p for p in detail["people"] if p["id"] == ctx["me"])
    assert me["display_name"] == "Nan"
    assert me["supabase_user_id"] == str(ctx["creator_id"])


def test_creator_without_display_name_falls_back_to_email_prefix(client, db_session_factory):
    db = db_session_factory()
    user = User(id=uuid.uuid4(), email="ravi.k@example.com")
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()
    headers = auth_headers(user_id)
    group_id = client.post("/api/v1/groups", json={"name": "G"}, headers=headers).json()["id"]
    people = client.get(f"/api/v1/groups/{group_id}", headers=headers).json()["people"]
    assert [p["display_name"] for p in people] == ["ravi.k"]


# --- participants ------------------------------------------------------------


def test_bill_defaults_to_whole_group_as_participants(client, ctx):
    bill = _manual_bill(client, ctx)
    assert set(bill["participant_person_ids"]) == {ctx["me"], ctx["Alice"], ctx["Bob"], ctx["Cara"]}


def test_bill_with_explicit_participants(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"], ctx["Bob"]])
    assert set(bill["participant_person_ids"]) == {ctx["Alice"], ctx["Bob"]}


def test_create_bill_rejects_participant_from_another_group(client, ctx):
    resp = client.post(
        f"/api/v1/groups/{ctx['group_id']}/bills",
        json={"participant_person_ids": [str(uuid.uuid4())]},
        headers=ctx["headers"],
    )
    assert resp.status_code == 422


def test_create_bill_rejects_empty_participant_list(client, ctx):
    resp = client.post(
        f"/api/v1/groups/{ctx['group_id']}/bills",
        json={"participant_person_ids": []},
        headers=ctx["headers"],
    )
    assert resp.status_code == 422


def test_create_bill_rejects_image_outside_own_folder(client, ctx):
    resp = client.post(
        f"/api/v1/groups/{ctx['group_id']}/bills",
        json={"image_storage_path": f"{uuid.uuid4()}/someone-elses-receipt.jpg"},
        headers=ctx["headers"],
    )
    assert resp.status_code == 422


def test_tax_split_only_across_participants(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"], ctx["Bob"]], tax="3.01")
    splits = client.get(f"/api/v1/bills/{bill['id']}/splits", headers=ctx["headers"]).json()
    assert {s["person_id"] for s in splits} == {ctx["Alice"], ctx["Bob"]}
    assert sorted(Decimal(s["tax_share"]) for s in splits) == [Decimal("1.50"), Decimal("1.51")]


def test_predictions_only_consider_participants(client, ctx, db_session_factory):
    # Cara loves entrees most, but she wasn't at this meal.
    _seed_score(db_session_factory, ctx["Cara"], TaxonomyValue.ENTREE, 1.0)
    _seed_score(db_session_factory, ctx["Bob"], TaxonomyValue.ENTREE, 0.4)
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"], ctx["Bob"]])
    [item] = bill["items"]
    assert [a["person_id"] for a in item["assignments"]] == [ctx["Bob"]]


def test_assign_rejects_non_participant(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"], ctx["Bob"]])
    item_id = bill["items"][0]["id"]
    resp = client.put(
        f"/api/v1/bills/{bill['id']}/items/{item_id}/assign",
        json={"person_id": ctx["Cara"]},
        headers=ctx["headers"],
    )
    assert resp.status_code == 422


def test_add_participant(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"]])
    resp = client.post(
        f"/api/v1/bills/{bill['id']}/participants",
        json={"person_id": ctx["Bob"]},
        headers=ctx["headers"],
    )
    assert resp.status_code == 200
    assert set(resp.json()["participant_person_ids"]) == {ctx["Alice"], ctx["Bob"]}
    # idempotent
    again = client.post(
        f"/api/v1/bills/{bill['id']}/participants",
        json={"person_id": ctx["Bob"]},
        headers=ctx["headers"],
    )
    assert len(again.json()["participant_person_ids"]) == 2


def test_remove_participant_rescores_their_items_among_remaining(client, ctx, db_session_factory):
    _seed_score(db_session_factory, ctx["Alice"], TaxonomyValue.ENTREE, 1.0)
    _seed_score(db_session_factory, ctx["Bob"], TaxonomyValue.ENTREE, 0.5)
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"], ctx["Bob"], ctx["Cara"]])
    item = bill["items"][0]
    assert item["assignments"][0]["person_id"] == ctx["Alice"]

    resp = client.delete(
        f"/api/v1/bills/{bill['id']}/participants/{ctx['Alice']}", headers=ctx["headers"]
    )
    assert resp.status_code == 200
    assert set(resp.json()["participant_person_ids"]) == {ctx["Bob"], ctx["Cara"]}

    bill = client.get(f"/api/v1/bills/{bill['id']}", headers=ctx["headers"]).json()
    assert [a["person_id"] for a in bill["items"][0]["assignments"]] == [ctx["Bob"]]
    # Alice is still in the group - only off this bill.
    group = client.get(f"/api/v1/groups/{ctx['group_id']}", headers=ctx["headers"]).json()
    assert ctx["Alice"] in {p["id"] for p in group["people"]}


def test_remove_participant_from_open_bill_resplits_settlement(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"], ctx["Bob"]], tax="2.00")
    item_id = bill["items"][0]["id"]
    client.put(
        f"/api/v1/bills/{bill['id']}/items/{item_id}/assign",
        json={"person_id": ctx["Alice"]},
        headers=ctx["headers"],
    )
    client.post(f"/api/v1/bills/{bill['id']}/confirm", headers=ctx["headers"])
    before = client.get(f"/api/v1/bills/{bill['id']}/settlement", headers=ctx["headers"]).json()
    assert len(before) == 2

    client.delete(f"/api/v1/bills/{bill['id']}/participants/{ctx['Bob']}", headers=ctx["headers"])
    after = client.get(f"/api/v1/bills/{bill['id']}/settlement", headers=ctx["headers"]).json()
    assert [(s["person_id"], s["total_owed"]) for s in after] == [(ctx["Alice"], "12.00")]


def test_cannot_remove_last_participant(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"]])
    resp = client.delete(
        f"/api/v1/bills/{bill['id']}/participants/{ctx['Alice']}", headers=ctx["headers"]
    )
    assert resp.status_code == 422


def test_removed_participant_can_stay_payer(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"], ctx["Bob"]])
    client.put(
        f"/api/v1/bills/{bill['id']}/payer", json={"person_id": ctx["Bob"]}, headers=ctx["headers"]
    )
    resp = client.delete(
        f"/api/v1/bills/{bill['id']}/participants/{ctx['Bob']}", headers=ctx["headers"]
    )
    assert resp.status_code == 200
    assert resp.json()["payer_person_id"] == ctx["Bob"]


def test_bill_payer_suggestion_limited_to_participants(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Bob"], ctx["Cara"]])
    resp = client.get(f"/api/v1/bills/{bill['id']}/payer-suggestion", headers=ctx["headers"])
    assert resp.status_code == 200
    # Nobody has paid yet -> alphabetical among participants only.
    assert resp.json()["person_id"] == ctx["Bob"]


def test_removing_group_member_clears_them_as_payer_on_open_bills(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"], ctx["Bob"]])
    client.put(
        f"/api/v1/bills/{bill['id']}/payer", json={"person_id": ctx["Bob"]}, headers=ctx["headers"]
    )
    resp = client.delete(
        f"/api/v1/groups/{ctx['group_id']}/people/{ctx['Bob']}", headers=ctx["headers"]
    )
    assert resp.status_code == 204
    bill = client.get(f"/api/v1/bills/{bill['id']}", headers=ctx["headers"]).json()
    assert bill["payer_person_id"] is None
    assert bill["participant_person_ids"] == [ctx["Alice"]]


# --- shared items ------------------------------------------------------------


def test_shared_item_splits_cost_evenly_to_the_cent(client, ctx):
    bill = _manual_bill(
        client,
        ctx,
        participants=[ctx["Alice"], ctx["Bob"], ctx["Cara"]],
        items=(("Nachos Platter", "10.00", "shared-platter"),),
    )
    item_id = bill["items"][0]["id"]
    resp = client.put(
        f"/api/v1/bills/{bill['id']}/items/{item_id}/assignees",
        json={"person_ids": [ctx["Alice"], ctx["Bob"], ctx["Cara"]]},
        headers=ctx["headers"],
    )
    assert resp.status_code == 200
    assignments = resp.json()["assignments"]
    assert len(assignments) == 3
    assert all(a["share_fraction"] == pytest.approx(1 / 3) for a in assignments)
    assert all(a["is_predicted"] is False for a in assignments)

    splits = client.get(f"/api/v1/bills/{bill['id']}/splits", headers=ctx["headers"]).json()
    shares = sorted(Decimal(s["item_subtotal_share"]) for s in splits)
    assert shares == [Decimal("3.33"), Decimal("3.33"), Decimal("3.34")]
    assert sum(shares) == Decimal("10.00")


def test_shared_assignees_learning_signal(client, ctx, db_session_factory):
    """Scorer predicted Alice; the user says Bob and Cara shared it. Bob
    and Cara each get a +1 nudge and a feedback row; Alice gets one -1."""
    _seed_score(db_session_factory, ctx["Alice"], TaxonomyValue.ENTREE, 0.5)
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"], ctx["Bob"], ctx["Cara"]])
    item = bill["items"][0]
    assert item["assignments"][0]["person_id"] == ctx["Alice"]

    client.put(
        f"/api/v1/bills/{bill['id']}/items/{item['id']}/assignees",
        json={"person_ids": [ctx["Bob"], ctx["Cara"]]},
        headers=ctx["headers"],
    )

    db = db_session_factory()
    scores = {
        (str(row.person_id), row.taxonomy_value): row.score
        for row in db.query(PersonTaxonomyScore).all()
    }
    feedback = db.query(PredictionFeedback).all()
    db.close()
    assert scores[(ctx["Bob"], TaxonomyValue.ENTREE)] == pytest.approx(0.3)
    assert scores[(ctx["Cara"], TaxonomyValue.ENTREE)] == pytest.approx(0.3)
    assert scores[(ctx["Alice"], TaxonomyValue.ENTREE)] == pytest.approx(0.2)
    assert {str(f.corrected_person_id) for f in feedback} == {ctx["Bob"], ctx["Cara"]}
    assert {str(f.original_predicted_person_id) for f in feedback} == {ctx["Alice"]}


def test_resaving_same_shared_set_adds_no_learning_noise(client, ctx, db_session_factory):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"], ctx["Bob"]])
    item_id = bill["items"][0]["id"]
    body = {"person_ids": [ctx["Alice"], ctx["Bob"]]}
    url = f"/api/v1/bills/{bill['id']}/items/{item_id}/assignees"
    client.put(url, json=body, headers=ctx["headers"])
    db = db_session_factory()
    count = db.query(PredictionFeedback).count()
    db.close()
    client.put(url, json={"person_ids": [ctx["Bob"], ctx["Alice"]]}, headers=ctx["headers"])
    db = db_session_factory()
    assert db.query(PredictionFeedback).count() == count
    db.close()


def test_single_person_assignees_behaves_like_assign(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"], ctx["Bob"]])
    item_id = bill["items"][0]["id"]
    resp = client.put(
        f"/api/v1/bills/{bill['id']}/items/{item_id}/assignees",
        json={"person_ids": [ctx["Bob"]]},
        headers=ctx["headers"],
    )
    assert [(a["person_id"], a["share_fraction"]) for a in resp.json()["assignments"]] == [
        (ctx["Bob"], 1.0)
    ]


def test_assignees_rejects_empty_list_and_non_participants(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"], ctx["Bob"]])
    url = f"/api/v1/bills/{bill['id']}/items/{bill['items'][0]['id']}/assignees"
    assert client.put(url, json={"person_ids": []}, headers=ctx["headers"]).status_code == 422
    resp = client.put(url, json={"person_ids": [ctx["Alice"], ctx["Cara"]]}, headers=ctx["headers"])
    assert resp.status_code == 422


def test_shared_item_change_on_open_bill_updates_settlement(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"], ctx["Bob"]])
    item_id = bill["items"][0]["id"]
    url = f"/api/v1/bills/{bill['id']}/items/{item_id}/assignees"
    client.put(url, json={"person_ids": [ctx["Alice"]]}, headers=ctx["headers"])
    client.post(f"/api/v1/bills/{bill['id']}/confirm", headers=ctx["headers"])
    client.put(url, json={"person_ids": [ctx["Alice"], ctx["Bob"]]}, headers=ctx["headers"])
    settlement = client.get(f"/api/v1/bills/{bill['id']}/settlement", headers=ctx["headers"]).json()
    assert {s["person_id"]: s["total_owed"] for s in settlement} == {
        ctx["Alice"]: "5.00",
        ctx["Bob"]: "5.00",
    }


# --- item edits in review ----------------------------------------------------


def test_patch_item_fixes_ocr_misread_and_recomputes_totals(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"]])
    item = bill["items"][0]
    resp = client.patch(
        f"/api/v1/bills/{bill['id']}/items/{item['id']}",
        json={
            "parsed_name": "Veg Burger",
            "price": "12.50",
            "quantity": 2,
            "flavor_tags": ["spicy", "spicy"],
            "dietary_flags": ["vegetarian"],
        },
        headers=ctx["headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["parsed_name"], body["price"], body["quantity"]) == ("Veg Burger", "12.50", 2)
    assert body["flavor_tags"] == ["spicy"]
    assert body["dietary_flags"] == ["vegetarian"]
    assert body["base_type"] == "entree"  # untouched field stays
    assert len(body["assignments"]) == 1  # editing doesn't touch who it's assigned to

    bill = client.get(f"/api/v1/bills/{bill['id']}", headers=ctx["headers"]).json()
    assert bill["subtotal"] == "25.00"


def test_patch_item_can_clear_base_type(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"]])
    item = bill["items"][0]
    resp = client.patch(
        f"/api/v1/bills/{bill['id']}/items/{item['id']}",
        json={"base_type": None},
        headers=ctx["headers"],
    )
    assert resp.json()["base_type"] is None


def test_delete_junk_line_in_review(client, ctx):
    bill = _manual_bill(
        client,
        ctx,
        participants=[ctx["Alice"]],
        items=(("Burger", "10.00", "entree"), ("TOTAL", "10.00", None)),
    )
    junk = next(i for i in bill["items"] if i["parsed_name"] == "TOTAL")
    resp = client.delete(f"/api/v1/bills/{bill['id']}/items/{junk['id']}", headers=ctx["headers"])
    assert resp.status_code == 204
    bill = client.get(f"/api/v1/bills/{bill['id']}", headers=ctx["headers"]).json()
    assert bill["subtotal"] == "10.00"


def test_items_locked_once_open(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"]])
    item = bill["items"][0]
    client.post(f"/api/v1/bills/{bill['id']}/confirm", headers=ctx["headers"])
    url = f"/api/v1/bills/{bill['id']}/items/{item['id']}"
    assert client.patch(url, json={"price": "1.00"}, headers=ctx["headers"]).status_code == 409
    assert client.delete(url, headers=ctx["headers"]).status_code == 409


# --- small endpoints ---------------------------------------------------------


def test_switch_processing_bill_to_manual_entry(client, ctx, monkeypatch):
    import app.api.v1.routes.bill as bill_routes

    monkeypatch.setattr(bill_routes, "run_bill_processing_job", lambda bill_id: None)
    bill = client.post(
        f"/api/v1/groups/{ctx['group_id']}/bills",
        json={"image_storage_path": f"{ctx['creator_id']}/r.jpg"},
        headers=ctx["headers"],
    ).json()
    assert bill["status"] == "processing"
    url = f"/api/v1/bills/{bill['id']}/switch-to-manual-entry"
    resp = client.post(url, headers=ctx["headers"])
    assert resp.json()["status"] == "needs_manual_entry"
    assert client.post(url, headers=ctx["headers"]).status_code == 409


def test_image_url_is_signed_by_backend(client, ctx, monkeypatch):
    import app.api.v1.routes.bill as bill_routes
    import app.services.storage as storage

    monkeypatch.setattr(bill_routes, "run_bill_processing_job", lambda bill_id: None)
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "service-key")
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, json))
        request = httpx.Request("POST", url)
        return httpx.Response(
            200, json={"signedURL": "/object/sign/bill-images/x.jpg?token=abc"}, request=request
        )

    monkeypatch.setattr(storage.httpx, "post", fake_post)
    path = f"{ctx['creator_id']}/x.jpg"
    bill = client.post(
        f"/api/v1/groups/{ctx['group_id']}/bills",
        json={"image_storage_path": path},
        headers=ctx["headers"],
    ).json()

    resp = client.get(f"/api/v1/bills/{bill['id']}/image-url", headers=ctx["headers"])
    assert resp.status_code == 200
    assert resp.json()["url"] == (
        "https://proj.supabase.co/storage/v1/object/sign/bill-images/x.jpg?token=abc"
    )
    assert calls == [
        (f"https://proj.supabase.co/storage/v1/object/sign/bill-images/{path}", {"expiresIn": 600})
    ]


def test_image_url_404_for_manual_bill(client, ctx):
    bill = _manual_bill(client, ctx)
    resp = client.get(f"/api/v1/bills/{bill['id']}/image-url", headers=ctx["headers"])
    assert resp.status_code == 404


def test_delete_bill_unless_closed(client, ctx):
    bill = _manual_bill(client, ctx, participants=[ctx["Alice"]])
    assert client.delete(f"/api/v1/bills/{bill['id']}", headers=ctx["headers"]).status_code == 204
    assert client.get(f"/api/v1/bills/{bill['id']}", headers=ctx["headers"]).status_code == 404


def test_taxonomy_scores_endpoint(client, ctx):
    client.post(
        f"/api/v1/people/{ctx['Alice']}/questionnaire",
        json={
            "vegetarian_or_vegan": "vegetarian",
            "avoids_gluten": False,
            "avoids_dairy": False,
            "has_nut_allergy": False,
            "avoids_pork": False,
            "avoids_beef": False,
            "drinks_alcohol": False,
            "appetizer_frequency": 0.5,
            "entree_vs_shared_preference": 0,
            "spice_tolerance": 1,
            "dessert_frequency": -0.5,
            "savory_vs_sweet_preference": 0.5,
        },
        headers=ctx["headers"],
    )
    resp = client.get(f"/api/v1/people/{ctx['Alice']}/taxonomy-scores", headers=ctx["headers"])
    assert resp.status_code == 200
    by_value = {row["taxonomy_value"]: row for row in resp.json()}
    assert by_value["vegetarian"]["is_hard_restriction"] is True
    assert by_value["spicy"]["score"] == 1.0
    assert all(row["source"] == "questionnaire" for row in resp.json())
