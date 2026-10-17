import re
import sys
from pathlib import Path

import pytest
from peewee import SqliteDatabase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as application
import models


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    database = SqliteDatabase(tmp_path / "test.db")
    monkeypatch.setattr(models, "db", database)
    monkeypatch.setitem(application.app.config, "TESTING", True)
    monkeypatch.setitem(application.app.config, "WTF_CSRF_ENABLED", True)
    monkeypatch.setitem(application.app.config, "LOGIN_DISABLED", False)
    monkeypatch.setitem(application.app.config, "_DATABASE_INITIALIZED", False)
    with database.bind_ctx([models.User, models.Post, models.Message, models.ArchivedPhoto]):
        models.initialize()
        users = [models.User.create(
            username=f"user{i}", last_name="姓", first_name="名",
            last_name_kana="せい", first_name_kana="めい", password="unused",
            phone="090-1234-5678", is_admin=(i == 3), admin_managed=(i == 3),
        ) for i in range(4)]
        post = models.Post.create(
            title="依頼", content="草刈り", author=users[0], helper=users[1],
            detail_address="非公開の住所123-4 / 090-1111-2222",
            contact_phone="080-9876-5432", contact_email="private-contact@example.com",
            postal_code="0294102", place_notes="非公開の目印：南側の倉庫前",
        )
        client = application.app.test_client()

        def login(index):
            with client.session_transaction() as session:
                session.clear()
                if index is not None:
                    session["_user_id"] = str(users[index].id)
                    session["_fresh"] = True

        yield client, post, users, login, database
        database.close()


@pytest.mark.parametrize("viewer,shared,visible", [
    (None, False, False), (None, True, False),
    (0, False, True), (0, True, True),
    (1, False, False), (1, True, True),
    (2, False, False), (2, True, False),
    (3, False, False), (3, True, False),
])
def test_contact_visibility(scenario, viewer, shared, visible):
    client, post, users, login, _ = scenario
    post.contact_shared = shared
    post.save()
    login(viewer)
    response = client.get(f"/post/{post.id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert (post.detail_address in html) == visible
    assert (post.contact_phone in html) == visible
    assert (post.contact_email in html) == visible
    assert (post.postal_code in html) == visible
    assert (post.place_notes in html) == visible
    assert ('id="chatLogs"' in html) == (viewer in (0, 1, 3))
    assert ("/share-contact" in html) == (viewer == 0 and not shared)
    assert ('class="confirmation-heading"' in html) == (viewer == 1 and shared)
    if viewer in (0, 1):
        assert f'data-state="{"confirmed" if shared else "pending"}"' in html


def approval_data(client, post):
    html = client.get(f"/post/{post.id}").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)[1]
    return {"csrf_token": token, "helper_id": str(post.helper_id)}


def test_only_owner_can_approve_with_csrf(scenario):
    client, post, users, login, _ = scenario
    url = f"/post/{post.id}/share-contact"
    login(1)
    assert client.post(url, data={"helper_id": users[1].id}).status_code == 403
    login(3)
    assert client.post(url, data={"helper_id": users[1].id}).status_code == 403
    login(0)
    assert client.get(url).status_code == 405
    assert client.post(url, data={"helper_id": users[1].id}).status_code == 400
    assert not models.Post.get_by_id(post.id).contact_shared
    data = approval_data(client, post)
    assert client.post(url, data=data).status_code == 302
    assert models.Post.get_by_id(post.id).contact_shared
    login(1)
    assert post.detail_address in client.get(f"/post/{post.id}").get_data(as_text=True)


def test_approval_cannot_be_transferred_to_new_applicant(scenario, monkeypatch):
    client, post, users, login, _ = scenario
    login(0)
    stale_data = approval_data(client, post)
    client.post(f"/post/{post.id}/share-contact", data=stale_data)
    login(1)
    assert client.post(f"/post/{post.id}/cancel").status_code == 302
    assert not models.Post.get_by_id(post.id).contact_shared
    assert post.detail_address not in client.get(f"/post/{post.id}").get_data(as_text=True)
    login(2)
    assert client.post(f"/post/{post.id}/apply").status_code == 302
    assert not models.Post.get_by_id(post.id).contact_shared
    assert post.detail_address not in client.get(f"/post/{post.id}").get_data(as_text=True)
    login(0)
    fresh_data = approval_data(client, models.Post.get_by_id(post.id))
    fresh_data["helper_id"] = stale_data["helper_id"]
    assert client.post(f"/post/{post.id}/share-contact", data=fresh_data).status_code == 409
    assert not models.Post.get_by_id(post.id).contact_shared


def test_existing_posts_migrate_to_private_by_default(scenario):
    _, post, _, _, database = scenario
    database.execute_sql('ALTER TABLE "post" DROP COLUMN "contact_shared"')
    models.initialize()
    migrated = models.Post.get_by_id(post.id)
    assert not migrated.contact_shared
    assert migrated.detail_address == post.detail_address
    models.initialize()
    assert models.Post.select().count() == 1


@pytest.mark.parametrize("viewer", [None, 0, 1, 2])
def test_area_map_is_visible_before_approval_without_disclosing_contact(scenario, viewer):
    client, post, _, login, _ = scenario
    post.location = "平泉駅周辺"
    post.save()
    login(viewer)
    html = client.get(f"/post/{post.id}").get_data(as_text=True)
    assert 'data-location="平泉駅周辺"' in html
    assert 'id="area-map-canvas"' in html
    assert '赤い枠内' in html
    assert '/static/js/area-map.js' in html
    assert html.index('dist/leaflet.js') < html.index('/static/js/area-map.js')
    assert (post.detail_address in html) == (viewer == 0)
