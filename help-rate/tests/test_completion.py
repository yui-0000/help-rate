import pytest

from test_contact_approval import scenario, approval_data
import models


@pytest.mark.parametrize("viewer", [1, 2, 3])
def test_only_owner_can_complete(scenario, viewer):
    client, post, _, login, _ = scenario
    post.contact_shared = True
    post.save()
    login(viewer)
    assert client.post(f"/post/{post.id}/complete").status_code == 403
    assert not models.Post.get_by_id(post.id).is_completed


def test_completion_requires_confirmation_and_csrf(scenario):
    client, post, _, login, _ = scenario
    login(0)
    url = f"/post/{post.id}/complete"
    assert client.get(url).status_code == 405
    assert client.post(url).status_code == 400
    data = approval_data(client, post)
    assert client.post(url, data=data).status_code == 409
    assert not models.Post.get_by_id(post.id).is_completed


def test_complete_and_keep_history_closed_to_reapplication(scenario):
    client, post, users, login, _ = scenario
    post.contact_shared = True
    post.save()
    models.Message.create(post=post, sender=users[1], content="作業が終わりました")
    login(0)
    html = client.get(f"/post/{post.id}").get_data(as_text=True)
    assert "この依頼を終了する" in html
    data = approval_data(client, post)
    assert client.post(f"/post/{post.id}/complete", data=data).status_code == 302
    assert models.Post.get_by_id(post.id).is_completed
    for viewer in (0, 1, None):
        login(viewer)
        html = client.get(f"/post/{post.id}").get_data(as_text=True)
        assert 'data-state="completed"' in html
        assert "/complete" not in html
        assert "/apply" not in html
        if viewer in (0, 1):
            assert "作業が終わりました" in html
    login(1)
    client.post(f"/post/{post.id}/cancel")
    assert models.Post.get_by_id(post.id).helper_id == users[1].id
    login(2)
    client.post(f"/post/{post.id}/apply")
    assert models.Post.get_by_id(post.id).is_completed
    assert models.Post.get_by_id(post.id).helper_id == users[1].id
    assert "終了済み" in client.get("/").get_data(as_text=True)


def test_old_database_migrates_without_marking_posts_complete(scenario):
    _, post, _, _, database = scenario
    database.execute_sql('ALTER TABLE "post" DROP COLUMN "is_completed"')
    models.initialize()
    assert not models.Post.get_by_id(post.id).is_completed
