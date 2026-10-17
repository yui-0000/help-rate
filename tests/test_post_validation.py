import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as application


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(application.app.config, "_RETENTION_PURGE_AT", float("inf"))
    monkeypatch.setitem(application.app.config, "_DATABASE_INITIALIZED", True)
    monkeypatch.setitem(application.app.config, "TESTING", True)
    monkeypatch.setitem(application.app.config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setitem(application.app.config, "LOGIN_DISABLED", True)
    user = SimpleNamespace(id=1, is_authenticated=True, is_admin=False)
    monkeypatch.setattr(application, "current_user", user)
    post = SimpleNamespace(
        id=1, author=user, title="依頼", content="草刈り", desired_date="2026-10-20 14:30",
        location="平泉地区", detail_address="平泉字衣関123-4", contact_phone="090-1234-5678", contact_method="電話",
        reward="", recommendation="", save=Mock(),
    )
    monkeypatch.setattr(application.Post, "get_by_id", Mock(return_value=post))
    create = Mock()
    monkeypatch.setattr(application.Post, "create", create)
    return application.app.test_client(), create, post


@pytest.mark.parametrize("url", ["/post", "/post/1/edit"])
@pytest.mark.parametrize("address", ["", "あ", " " * 20, " あ ", "あ" * 9, "あ" * 501])
def test_invalid_address_does_not_save(client, url, address):
    browser, create, post = client
    response = browser.post(url, data={
        "title": "依頼", "content": "草刈り", "desired_day": "2026-10-20", "time_mode": "exact", "desired_hour": "14", "desired_minute": "30",
        "location": "平泉地区", "contact_phone": "090-1234-5678", "contact_method": "電話", "detail_address": address,
    })
    assert response.status_code == 200
    assert 'id="detail-address-errors"' in response.get_data(as_text=True)
    assert "入力してください" in response.get_data(as_text=True)
    create.assert_not_called()
    post.save.assert_not_called()


@pytest.mark.parametrize("url", ["/post", "/post/1/edit"])
@pytest.mark.parametrize("address", ["あ" * 10, "あ" * 500, "  平泉字衣関123-4 / 連絡はチャット  "])
def test_valid_address_is_saved_with_outer_spaces_removed(client, url, address):
    browser, create, post = client
    response = browser.post(url, data={
        "title": "依頼", "content": "草刈り", "desired_day": "2026-10-20", "time_mode": "exact", "desired_hour": "14", "desired_minute": "30",
        "location": "平泉地区", "contact_phone": "090-1234-5678", "contact_method": "アプリ内チャット(Chat)",
        "detail_address": address,
    })
    assert response.status_code == 302
    if url == "/post":
        assert create.call_args.kwargs["detail_address"] == address.strip()
    else:
        post.save.assert_called_once()
        assert post.detail_address == address.strip()


@pytest.mark.parametrize("url", ["/post", "/post/1/edit"])
@pytest.mark.parametrize("changes", [
    {"desired_day": ""}, {"desired_day": "明日"}, {"desired_day": "2026-02-30"},
    {"time_mode": "fake"}, {"desired_hour": "25"}, {"desired_hour": ""},
    {"desired_minute": "60"}, {"desired_minute": ""},
    {"time_mode": "period", "desired_period": ""},
    {"time_mode": "period", "desired_period": "未定の自由文"},
])
def test_invalid_schedule_never_saves(client, url, changes):
    browser, create, post = client
    data = dict(title="依頼", content="草刈り", desired_day="2026-10-20", time_mode="exact",
                desired_hour="14", desired_minute="30", location="平泉地区", contact_phone="090-1234-5678", contact_method="電話",
                detail_address="平泉字衣関123-4")
    data.update(changes)
    response = browser.post(url, data=data)
    assert response.status_code == 200
    assert 'role="alert"' in response.get_data(as_text=True)
    create.assert_not_called()
    post.save.assert_not_called()


@pytest.mark.parametrize("url", ["/post", "/post/1/edit"])
@pytest.mark.parametrize("time_values, expected", [
    ({"time_mode": "exact", "desired_hour": "09", "desired_minute": "05"}, "09:05"),
    ({"time_mode": "around", "desired_hour": "12", "desired_minute": "00"}, "12時頃"),
    ({"time_mode": "around", "desired_hour": "00", "desired_minute": "30"}, "0時30分頃"),
    *[({"time_mode": "period", "desired_period": period}, period) for period in ("早朝", "午前", "午後", "夕方", "夜")],
    ({"time_mode": "consult"}, "相談して決める"),
])
def test_all_schedule_modes_save_and_can_be_edited(client, url, time_values, expected):
    browser, create, post = client
    data = dict(title="依頼", content="草刈り", desired_day="2028-02-29",
                location="平泉地区", contact_phone="090-1234-5678", contact_method="電話", detail_address="平泉字衣関123-4")
    data.update(time_values)
    response = browser.post(url, data=data)
    assert response.status_code == 302
    stored = create.call_args.kwargs["desired_date"] if url == "/post" else post.desired_date
    assert stored == f"2028-02-29 {expected}"
    post.desired_date = stored
    with application.app.test_request_context("/post/1/edit"):
        form = application.PostForm(obj=post)
        assert form.desired_day.data.isoformat() == "2028-02-29"
        assert form.time_mode.data == time_values["time_mode"]
        for name, value in time_values.items():
            assert getattr(form, name).data == value
        assert form.validate()
        assert form.schedule_text() == stored


def test_separate_date_and_time_and_existing_datetime(client):
    browser, _, _ = client
    html = browser.get("/post/1/edit").get_data(as_text=True)
    assert 'type="date"' in html
    assert 'datetime-local' not in html
    assert 'value="2026-10-20"' in html
    assert '<option selected value="14">14時</option>' in html
    assert '<option selected value="30">30分</option>' in html
    assert "実施日（年・月・日）" in html
    assert "時（0〜23時）" in html


def test_legacy_free_text_datetime_can_be_corrected(client):
    browser, _, post = client
    post.desired_date = "明日の午後"
    response = browser.get("/post/1/edit")
    assert response.status_code == 200
    assert "以前の入力：明日の午後" in response.get_data(as_text=True)
    assert post.desired_date == "明日の午後"


@pytest.mark.parametrize("url", ["/post", "/post/1/edit"])
@pytest.mark.parametrize("phone,email,accepted", [
    ("", "", False), ("   ", "   ", False), ("あ", "", False),
    ("123", "", False),
    ("090123456", "", False), ("090123456789", "", False),
    ("0" * 100, "", False), ("+819012345678", "", False),
    ("09012345678", "", True), ("0312345678", "", True),
    ("", "user@example", False), ("", "user@example.", False),
    ("", "user@.com", False), ("", "user@@example.com", False),
    ("", "user@example..com", False), ("", "user@example.co.jp", True), ("", "メール", False), ("", "user@", False),
    ("090-1234-5678", "", True), ("03-1234-5678", "", True),
    ("０９０－１２３４－５６７８", "", True),
    ("", "taro@example.com", True), ("090-1234-5678", "taro@example.com", True),
    ("090-1234-5678", "invalid", False), ("invalid", "taro@example.com", False),
])
def test_separate_contact_is_required_and_validated(client, url, phone, email, accepted):
    browser, create, post = client
    response = browser.post(url, data=dict(
        title="依頼", content="草刈り", desired_day="2026-10-20", time_mode="consult",
        location="平泉地区", contact_method="アプリ内チャット(Chat)",
        detail_address="岩手県西磐井郡平泉町平泉字衣関123-4", contact_phone=phone, contact_email=email,
    ))
    assert response.status_code == (302 if accepted else 200)
    if not accepted:
        create.assert_not_called()
        post.save.assert_not_called()
        return
    saved = create.call_args.kwargs if url == "/post" else vars(post)
    assert saved["contact_email"] == (email or None)
    assert saved["contact_phone"] == ("090-1234-5678" if phone.startswith("０") else phone or None)
