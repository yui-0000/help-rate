import re

import pytest

import app as application
import models
import postal
from test_contact_approval import scenario
from test_post_validation import client


def test_official_postal_data_normalizes_and_preserves_multiple_candidates():
    assert postal.lookup_postal_code("０２９－４１０２") == ["岩手県西磐井郡平泉町平泉"]
    assert postal.lookup_postal_code("100-0001") == ["東京都千代田区千代田"]
    assert len(postal.lookup_postal_code("0040000")) > 1
    assert postal.lookup_postal_code("0000000") == []
    with pytest.raises(ValueError):
        postal.lookup_postal_code("../../1234567")


def test_lookup_endpoint_requires_login_and_handles_errors(scenario, monkeypatch):
    browser, _, _, login, _ = scenario
    assert browser.get("/postal-addresses?postal_code=0294102").status_code == 302
    login(0)
    response = browser.get("/postal-addresses?postal_code=029-4102")
    assert response.status_code == 200
    assert response.json == {"addresses": ["岩手県西磐井郡平泉町平泉"]}
    assert response.headers["Cache-Control"] == "no-store"
    assert browser.get("/postal-addresses?postal_code=123").status_code == 400
    assert browser.get("/postal-addresses?postal_code=0000000").json == {"addresses": []}
    def unavailable(value):
        raise postal.PostalDataError()
    monkeypatch.setattr(application, "lookup_postal_code", unavailable)
    assert browser.get("/postal-addresses?postal_code=0294102").status_code == 503


@pytest.mark.parametrize("url", ["/post", "/post/1/edit"])
@pytest.mark.parametrize("code,notes,address,accepted", [
    ("０２９－４１０２", "赤い倉庫前に集合", "岩手県西磐井郡平泉町平泉字衣関123-4", True),
    ("", "畑の南側に集合", "岩手県西磐井郡平泉町平泉字衣関123-4", True),
    ("0294102", "", "岩手県西磐井郡平泉町平泉", False),
    ("0294102", "番地なし。南側入口", "岩手県西磐井郡平泉町平泉", True),
    ("abc", "", "岩手県西磐井郡平泉町平泉字衣関123-4", False),
    ("0294102", "あ" * 501, "岩手県西磐井郡平泉町平泉字衣関123-4", False),
])
def test_address_helper_saves_and_validates_without_javascript(client, url, code, notes, address, accepted):
    browser, create, post = client
    response = browser.post(url, data=dict(
        title="依頼", content="作業", desired_day="2026-10-20", time_mode="consult", location="平泉地区",
        contact_phone="090-1234-5678", contact_method="アプリ内チャット(Chat)",
        postal_code=code, place_notes=notes, detail_address=address,
    ))
    assert response.status_code == (302 if accepted else 200)
    if accepted:
        saved = create.call_args.kwargs if url == "/post" else vars(post)
        assert saved["postal_code"] == ("0294102" if code else None)
        assert saved["place_notes"] == notes
        assert saved["detail_address"] == address
    else:
        create.assert_not_called()
        post.save.assert_not_called()


def test_new_address_fields_persist_and_edit(scenario):
    browser, post, _, login, database = scenario
    login(0)
    url = f"/post/{post.id}/edit"
    html = browser.get(url).get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)[1]
    response = browser.post(url, data=dict(
        csrf_token=token, title="依頼", content="作業", desired_day="2026-10-20", time_mode="consult", location="平泉地区",
        contact_email="taro@example.com", contact_method="アプリ内チャット(Chat)",
        postal_code="029-4102", place_notes="赤い倉庫前に集合", detail_address="岩手県西磐井郡平泉町平泉字衣関123-4",
    ))
    assert response.status_code == 302
    saved = models.Post.get_by_id(post.id)
    assert saved.postal_code == "0294102" and saved.place_notes == "赤い倉庫前に集合"
    html = browser.get(url).get_data(as_text=True)
    assert 'value="0294102"' in html and "赤い倉庫前に集合" in html
    for column in ("postal_code", "place_notes"):
        database.execute_sql(f'ALTER TABLE "post" DROP COLUMN "{column}"')
    models.initialize()
    migrated = models.Post.get_by_id(post.id)
    assert migrated.postal_code is None and migrated.place_notes is None
    assert migrated.detail_address == saved.detail_address
