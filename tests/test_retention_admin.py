from datetime import timedelta
import io
import re

import pytest
from werkzeug.security import generate_password_hash

from test_contact_approval import scenario
import app as application
import models
import retention


@pytest.fixture
def setup_retention(scenario, tmp_path, monkeypatch):
    client, post, users, login, database = scenario
    uploads = tmp_path / "photos"
    uploads.mkdir()
    monkeypatch.setitem(application.app.config, "UPLOAD_FOLDER", str(uploads))
    monkeypatch.setitem(application.app.config, "_RETENTION_PURGE_AT", float("inf"))
    now = retention.utcnow()
    monkeypatch.setattr(application, "utcnow", lambda: now)
    monkeypatch.setattr(retention, "utcnow", lambda: now)
    return client, post, users, login, database, uploads, now


def csrf(client, url):
    html = client.get(url).get_data(as_text=True)
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match, html
    return match[1]


@pytest.mark.parametrize("viewer", [None, 0, 1, 2])
@pytest.mark.parametrize("url", ["/admin/users", "/admin/users/1", "/admin/deleted-posts", "/admin/deleted-messages"])
def test_admin_pages_deny_every_non_admin(setup_retention, viewer, url):
    client, _, _, login, _, _, _ = setup_retention
    login(viewer)
    assert client.get(url).status_code == (302 if viewer is None else 403)


def test_admin_user_button_and_private_user_details(setup_retention):
    client, _, users, login, _, _, _ = setup_retention
    login(0)
    assert "ユーザー情報を見る" not in client.get("/").get_data(as_text=True)
    login(3)
    assert "ユーザー情報を見る" in client.get("/").get_data(as_text=True)
    response = client.get(f"/admin/users/{users[0].id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert users[0].phone in html
    assert users[0].password not in html
    assert response.headers["Cache-Control"] == "no-store"


def test_post_deletion_retains_content_but_blocks_normal_urls(setup_retention):
    client, post, users, login, _, uploads, _ = setup_retention
    post.image_path = "retained.jpg"
    post.save()
    (uploads / post.image_path).write_bytes(b"photo")
    msg = models.Message.create(post=post, sender=users[1], content="保管する会話")
    login(0)
    url = f"/post/{post.id}/delete"
    token = csrf(client, url)
    assert models.Post.get_by_id(post.id).deleted_at is None
    assert client.post(url).status_code == 400
    assert client.post(url, data={"csrf_token": token}).status_code == 302
    assert models.Post.get_by_id(post.id).deleted_at is not None
    assert models.Message.get_by_id(msg.id).content == "保管する会話"
    assert (uploads / post.image_path).exists()
    for viewer in (None, 0, 1, 2, 3):
        login(viewer)
        assert client.get(f"/post/{post.id}").status_code == 404
        assert f'data-post-id="{post.id}"' not in client.get("/posts/list").get_data(as_text=True)
        assert client.get(f"/uploads/{post.image_path}").status_code == (200 if viewer == 3 else 404)
    login(3)
    html = client.get(f"/admin/deleted-posts/{post.id}").get_data(as_text=True)
    assert post.content in html and "保管する会話" in html
    assert post.detail_address in html
    assert client.get(f"/post/{post.id}/delete").status_code == 404
    for endpoint in ("message", "share-contact", "complete", "apply", "cancel", "edit"):
        assert client.post(f"/post/{post.id}/{endpoint}").status_code == 404


def test_message_deletion_retained_only_in_admin_archive(setup_retention):
    client, post, users, login, _, _, _ = setup_retention
    msg = models.Message.create(post=post, sender=users[1], content="取り消す会話の本文")
    login(1)
    token = csrf(client, f"/post/{post.id}")
    assert client.post(f"/message/{msg.id}/delete", data={"csrf_token": token}).status_code == 302
    first_time = models.Message.get_by_id(msg.id).deleted_at
    assert "取り消す会話の本文" not in client.get(f"/post/{post.id}").get_data(as_text=True)
    assert client.post(f"/message/{msg.id}/delete", data={"csrf_token": token}).status_code == 404
    assert models.Message.get_by_id(msg.id).deleted_at == first_time
    login(3)
    assert "取り消す会話の本文" in client.get("/admin/deleted-messages").get_data(as_text=True)
    assert "取り消す会話の本文" not in client.get(f"/post/{post.id}").get_data(as_text=True)


def test_90_day_expiry_purges_only_expired_deleted_data(setup_retention):
    _, post, users, _, _, uploads, now = setup_retention
    post.deleted_at = now - timedelta(days=90)
    post.image_path = "expired.jpg"
    post.save()
    (uploads / "expired.jpg").write_bytes(b"photo")
    models.Message.create(post=post, sender=users[1], content="expired chat")
    active = models.Post.create(title="現役", content="残す", author=users[0])
    old_message = models.Message.create(post=active, sender=users[1], content="期限切れ", deleted_at=now-timedelta(days=90))
    recent = models.Message.create(post=active, sender=users[1], content="90日未満", deleted_at=now-timedelta(days=89))
    admin_before = dict(models.User.get_by_id(users[3].id).__data__)
    retention.purge_expired(uploads)
    assert models.Post.get_or_none(models.Post.id == post.id) is None
    assert not (uploads / "expired.jpg").exists()
    assert models.Message.get_or_none(models.Message.id == old_message.id) is None
    assert models.Message.get_by_id(recent.id).content == "90日未満"
    assert models.Post.get_by_id(active.id).content == "残す"
    assert dict(models.User.get_by_id(users[3].id).__data__) == admin_before


def test_purge_preserves_shared_photos_and_prevents_path_traversal(setup_retention, tmp_path):
    _, post, users, _, _, uploads, now = setup_retention
    post.deleted_at = now - timedelta(days=91)
    post.image_path = "shared.jpg"
    post.save()
    (uploads / "shared.jpg").write_bytes(b"shared")
    models.Post.create(title="現役", content="共有写真", author=users[0], image_path="shared.jpg")
    outside = tmp_path / "keep.jpg"
    outside.write_bytes(b"keep")
    models.Post.create(title="不正なパス", content="削除対象", author=users[0], image_path="../keep.jpg", deleted_at=now-timedelta(days=91))
    retention.purge_expired(uploads)
    assert (uploads / "shared.jpg").exists()
    assert outside.read_bytes() == b"keep"


def test_deleted_user_cannot_login_and_admins_are_protected(setup_retention):
    client, post, users, login, _, _, now = setup_retention
    target = users[0]
    target.password = generate_password_hash("Password123")
    target.save()
    models.Message.create(post=post, sender=target, content="本人の会話")
    login(3)
    for protected in (users[3],):
        assert client.get(f"/admin/users/{protected.id}/delete").status_code == 403
        assert client.post(f"/admin/users/{protected.id}/delete").status_code == 403
    url = f"/admin/users/{target.id}/delete"
    token = csrf(client, url)
    assert client.post(url, data={"csrf_token": token, "username": "違う名前"}).status_code == 200
    assert models.User.get_by_id(target.id).deleted_at is None
    assert client.post(url, data={"csrf_token": token, "username": target.username}).status_code == 302
    assert models.User.get_by_id(target.id).deleted_at == now
    assert models.Post.get_by_id(post.id).deleted_at == now
    assert "削除日時" in client.get(f"/admin/users/{target.id}").get_data(as_text=True)
    login(0)
    assert client.get("/post").status_code == 302  # old login cookie no longer authenticates
    login(None)
    token = csrf(client, "/login")
    response = client.post("/login", data={"csrf_token": token, "login_id": target.username, "password": "Password123"})
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "_user_id" not in session
    assert models.User.get_by_id(users[3].id).is_admin


def test_expired_deleted_users_are_removed_but_admin_information_is_never_removed(setup_retention):
    _, post, users, _, _, uploads, now = setup_retention
    post.delete_instance()
    target = users[0]
    target.deleted_at = now - timedelta(days=90)
    target.save()
    admin = users[3]
    admin.deleted_at = now - timedelta(days=100)
    admin.save()
    admin_before = dict(models.User.get_by_id(admin.id).__data__)
    retention.purge_expired(uploads)
    assert models.User.get_or_none(models.User.id == target.id) is None
    assert dict(models.User.get_by_id(admin.id).__data__) == admin_before


def test_upload_rejects_more_than_5mb(setup_retention):
    client, _, _, login, _, _, _ = setup_retention
    login(0)
    token = csrf(client, "/post")
    response = client.post("/post", data={
        "csrf_token": token, "title": "依頼", "content": "内容", "desired_day": "2026-10-20", "time_mode": "exact", "desired_hour": "14", "desired_minute": "30",
        "location": "平泉地区", "detail_address": "平泉字衣関123-4", "contact_phone": "090-1234-5678", "contact_method": "電話",
        "image": (io.BytesIO(b"x" * (5 * 1024 * 1024 + 1)), "photo.png"),
    })
    assert response.status_code == 200
    assert "写真は1枚5MB以内" in response.get_data(as_text=True)


def test_pagination_and_legacy_migration(setup_retention):
    client, post, users, login, database, _, _ = setup_retention
    for index in range(22):
        models.User.create(username=f"追加{index}", password="hash", last_name="", first_name="", last_name_kana="", first_name_kana="", phone="")
    login(3)
    assert "次の20件" in client.get("/admin/users").get_data(as_text=True)
    assert "前の20件" in client.get("/admin/users?page=2").get_data(as_text=True)
    for table in ("user", "post", "message"):
        database.execute_sql(f'DROP INDEX IF EXISTS "{table}_deleted_at"')
        database.execute_sql(f'ALTER TABLE "{table}" DROP COLUMN "deleted_at"')
    models.initialize()
    assert models.Post.get_by_id(post.id).deleted_at is None
    assert models.User.get_by_id(users[3].id).is_admin



def test_replaced_photo_is_retained_privately_then_expires(setup_retention):
    client, post, _, login, _, uploads, now = setup_retention
    post.image_path = "previous.jpg"
    post.save()
    (uploads / "previous.jpg").write_bytes(b"old")
    login(0)
    url = f"/post/{post.id}/edit"
    token = csrf(client, url)
    response = client.post(url, data={
        "csrf_token": token, "title": "依頼", "content": "内容", "desired_day": "2026-10-20", "time_mode": "exact", "desired_hour": "14", "desired_minute": "30",
        "location": "平泉地区", "detail_address": "平泉字衣関123-4", "contact_phone": "090-1234-5678", "contact_method": "電話",
        "image": (io.BytesIO(b"new photo"), "現場写真.JPG"),
    })
    assert response.status_code == 302
    replacement = models.Post.get_by_id(post.id).image_path
    assert replacement.endswith(".jpg") and replacement != "previous.jpg"
    assert (uploads / replacement).exists()
    old = models.ArchivedPhoto.get()
    assert old.filename == "previous.jpg" and old.deleted_at == now
    assert client.get("/uploads/previous.jpg").status_code == 404
    login(3)
    assert client.get("/uploads/previous.jpg").status_code == 200
    assert "previous.jpg" in client.get("/admin/deleted-photos").get_data(as_text=True)
    old.deleted_at = now - timedelta(days=90)
    old.save()
    retention.purge_expired(uploads)
    assert not (uploads / "previous.jpg").exists()
    assert (uploads / replacement).exists()
    assert models.ArchivedPhoto.select().count() == 0


def test_managed_operator_is_protected_even_after_role_revoked(setup_retention):
    client, _, users, login, _, _, _ = setup_retention
    operator = users[2]
    operator.admin_managed = True
    operator.save()
    login(3)
    assert client.post(f"/admin/users/{operator.id}/delete").status_code == 403
    assert models.User.get_by_id(operator.id).deleted_at is None



def test_new_contact_fields_persist_and_migrate_without_changing_existing_data(setup_retention):
    client, post, users, login, database, _, _ = setup_retention
    login(0)
    token = csrf(client, "/post")
    response = client.post("/post", data={
        "csrf_token": token, "title": "新しい依頼", "content": "作業内容", "desired_day": "2026-10-20",
        "time_mode": "consult", "location": "平泉地区", "contact_method": "アプリ内チャット(Chat)",
        "detail_address": "岩手県西磐井郡平泉町平泉字衣関123-4", "contact_email": "request@example.com",
    })
    assert response.status_code == 302
    created = models.Post.get(models.Post.title == "新しい依頼")
    assert created.contact_email == "request@example.com" and created.contact_phone is None
    html = client.get(f"/post/{created.id}/edit").get_data(as_text=True)
    assert 'value="request@example.com"' in html
    assert 'type="email"' in html and 'type="tel"' in html
    admin_before = dict(models.User.get_by_id(users[3].id).__data__)
    old_address = post.detail_address
    for name in ("contact_phone", "contact_email"):
        database.execute_sql(f'ALTER TABLE "post" DROP COLUMN "{name}"')
    models.initialize()
    assert models.Post.get_by_id(post.id).detail_address == old_address
    assert models.Post.get_by_id(post.id).contact_email is None
    assert dict(models.User.get_by_id(users[3].id).__data__) == admin_before
