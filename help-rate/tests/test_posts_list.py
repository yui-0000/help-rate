import pytest
import re
from datetime import datetime, timedelta

from test_contact_approval import scenario
import models


@pytest.mark.parametrize("state,label", [
    ("open", "募集中"), ("discussing", "相談中"),
    ("active", "依頼中"), ("completed", "終了済み"),
])
def test_public_list_has_distinct_status_and_no_private_information(scenario, state, label):
    client, post, _, login, _ = scenario
    post.is_completed = state == "completed"
    post.contact_shared = state in ("active", "completed")
    if state == "open":
        post.helper = None
    post.save()
    login(None)
    response = client.get("/posts/list")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    html = response.get_data(as_text=True)
    assert f'class="card status-{state}"' in html
    assert label in html
    assert post.detail_address not in html
    assert "090-1234-5678" not in html
    assert "<html" not in html


def test_next_refresh_reflects_new_posts_status_changes_and_deletion(scenario):
    client, post, users, login, _ = scenario
    login(None)
    first = client.get("/posts/list").get_data(as_text=True)
    assert "新しい依頼" not in first
    added = models.Post.create(title="新しい依頼", content="庭の掃除", author=users[0])
    second = client.get("/posts/list").get_data(as_text=True)
    assert "新しい依頼" in second
    assert second.index(f'data-post-id="{added.id}"') < second.index(f'data-post-id="{post.id}"')
    added.helper = users[1]
    added.save()
    assert f'class="card status-discussing" data-post-id="{added.id}"' in client.get("/posts/list").get_data(as_text=True)
    added.contact_shared = True
    added.save()
    assert f'class="card status-active" data-post-id="{added.id}"' in client.get("/posts/list").get_data(as_text=True)
    added.is_completed = True
    added.save()
    assert f'class="card status-completed" data-post-id="{added.id}"' in client.get("/posts/list").get_data(as_text=True)
    added.delete_instance()
    assert "新しい依頼" not in client.get("/posts/list").get_data(as_text=True)


def test_empty_list_and_home_refresh_configuration(scenario):
    client, post, _, login, _ = scenario
    post.delete_instance()
    login(None)
    assert "現在、お手伝いの募集はありません" in client.get("/posts/list").get_data(as_text=True)
    home = client.get("/").get_data(as_text=True)
    assert 'id="posts-list" data-refresh-url="/posts/list"' in home
    assert '/static/js/index.js' in home


@pytest.mark.parametrize("status", ["all", "open", "discussing", "active", "completed"])
def test_status_tags_filter_home_and_refresh_consistently(scenario, status):
    client, post, users, login, _ = scenario
    post.delete_instance()
    entries = {}
    for state in ("open", "discussing", "active", "completed"):
        entries[state] = models.Post.create(
            title=state, content="内容", author=users[0],
            helper=users[1] if state != "open" else None,
            contact_shared=state in ("active", "completed"),
            is_completed=state == "completed",
        )
    login(None)
    expected = {item.id for item in entries.values()} if status == "all" else {entries[status].id}
    for url in (f"/?status={status}", f"/posts/list?status={status}"):
        html = client.get(url).get_data(as_text=True)
        actual = {int(value) for value in re.findall(r'data-post-id="(\d+)"', html)}
        assert actual == expected
    home = client.get(f"/?status={status}").get_data(as_text=True)
    assert f'class="badge status-{status} status-badge status-filter" aria-current="page"' in home
    refresh_url = "/posts/list" if status == "all" else f"/posts/list?status={status}"
    assert f'data-refresh-url="{refresh_url}"' in home


def test_newest_completed_post_is_grouped_after_all_unfinished_posts(scenario):
    client, post, users, login, _ = scenario
    done = models.Post.create(
        title="新しい終了依頼", content="内容", author=users[0],
        is_completed=True, created_at=datetime.now() + timedelta(days=1),
    )
    login(None)
    for url in ("/", "/posts/list"):
        html = client.get(url).get_data(as_text=True)
        assert html.index(f'data-post-id="{post.id}"') < html.index('終了した依頼') < html.index(f'data-post-id="{done.id}"')


def test_status_change_disappears_from_previous_filter_on_refresh(scenario):
    client, post, _, login, _ = scenario
    login(None)
    assert f'data-post-id="{post.id}"' in client.get("/posts/list?status=discussing").get_data(as_text=True)
    post.contact_shared = True
    post.save()
    html = client.get("/posts/list?status=discussing").get_data(as_text=True)
    assert f'data-post-id="{post.id}"' not in html
    assert "この状態の依頼はまだありません" in html
    assert f'data-post-id="{post.id}"' in client.get("/posts/list?status=active").get_data(as_text=True)


def test_unknown_status_returns_all_posts(scenario):
    client, post, _, login, _ = scenario
    login(None)
    html = client.get("/?status=unknown").get_data(as_text=True)
    assert f'data-post-id="{post.id}"' in html
    assert 'class="badge status-all status-badge status-filter" aria-current="page"' in html


@pytest.mark.parametrize("owner", ["all", "mine", "others"])
@pytest.mark.parametrize("status", ["all", "open", "discussing", "active", "completed"])
def test_owner_and_status_filters_work_together_in_home_and_refresh(scenario, owner, status):
    client, post, users, login, _ = scenario
    post.delete_instance()
    entries = []
    for author in users[:2]:
        for state in ("open", "discussing", "active", "completed"):
            item = models.Post.create(title=f"{author.username}-{state}", content="内容", author=author,
                helper=users[2] if state != "open" else None,
                contact_shared=state in ("active", "completed"), is_completed=state == "completed")
            entries.append((author.id, state, item.id))
    login(0)
    expected = {item_id for author_id, state, item_id in entries
        if (owner == "all" or (owner == "mine" and author_id == users[0].id) or (owner == "others" and author_id != users[0].id))
        and (status == "all" or status == state)}
    for base in ("/", "/posts/list"):
        html = client.get(f"{base}?owner={owner}&status={status}").get_data(as_text=True)
        actual = {int(value) for value in re.findall(r'data-post-id="(\d+)"', html)}
        assert actual == expected
        assert ("自分の投稿" in html) == (owner != "others")
    html = client.get(f"/?owner={owner}&status={status}").get_data(as_text=True)
    refresh = re.search(r'data-refresh-url="([^"]+)"', html)[1].replace("&amp;", "&")
    from urllib.parse import urlparse, parse_qs
    args = parse_qs(urlparse(refresh).query)
    assert args.get("owner", ["all"])[0] == owner
    assert args.get("status", ["all"])[0] == status
    assert 'class="ownership-tab" aria-current="page"' in html


def test_owner_filter_uses_current_login_and_hides_deleted_posts(scenario):
    client, post, users, login, _ = scenario
    other = models.Post.create(title="別の方の依頼", content="内容", author=users[1])
    login(0)
    html = client.get("/posts/list?owner=mine").get_data(as_text=True)
    assert f'data-post-id="{post.id}"' in html and f'data-post-id="{other.id}"' not in html
    login(1)
    html = client.get("/posts/list?owner=mine").get_data(as_text=True)
    assert f'data-post-id="{other.id}"' in html and f'data-post-id="{post.id}"' not in html
    other.deleted_at = datetime.now()
    other.save()
    assert "自分が投稿した依頼はまだありません" in client.get("/posts/list?owner=mine").get_data(as_text=True)
    login(None)
    html = client.get("/?owner=mine").get_data(as_text=True)
    assert f'data-post-id="{post.id}"' in html
    assert 'aria-label="投稿者で依頼を絞り込む"' not in html
    assert 'class="ownership-badge"' not in html


def test_unknown_owner_defaults_to_all_and_completed_stays_last(scenario):
    client, post, users, login, _ = scenario
    login(0)
    done = models.Post.create(title="終了した自分の依頼", content="内容", author=users[0], is_completed=True,
        created_at=datetime.now() + timedelta(days=1))
    for owner in ("mine", "invalid"):
        html = client.get(f"/posts/list?owner={owner}").get_data(as_text=True)
        assert html.index(f'data-post-id="{post.id}"') < html.index(f'data-post-id="{done.id}"')


@pytest.mark.parametrize("viewer", [None, 1])
def test_other_posts_show_nickname_without_private_user_information(scenario, viewer):
    client, post, users, login, _ = scenario
    users[0].username = "ご近所のタロウ"
    users[0].save()
    login(viewer)
    for url in ("/", "/posts/list"):
        html = client.get(url).get_data(as_text=True)
        assert "投稿者：ご近所のタロウ" in html
        assert "ほかの方の投稿</div>" not in html
        assert users[0].phone not in html
        assert post.contact_email not in html


def test_own_post_keeps_its_marker(scenario):
    client, _, _, login, _ = scenario
    login(0)
    assert '<div class="ownership-badge">自分の投稿</div>' in client.get("/posts/list").get_data(as_text=True)
