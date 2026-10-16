import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as application


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(application.app.config, "_DATABASE_INITIALIZED", True)
    monkeypatch.setitem(application.app.config, "TESTING", True)
    monkeypatch.setitem(application.app.config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setitem(application.app.config, "LOGIN_DISABLED", True)
    user = SimpleNamespace(id=1, is_authenticated=True, is_admin=False)
    monkeypatch.setattr(application, "current_user", user)
    post = SimpleNamespace(
        id=1, author=user, title="依頼", content="草刈り", desired_date="明日",
        location="平泉地区", detail_address="平泉字衣関123-4", contact_method="電話",
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
        "title": "依頼", "content": "草刈り", "desired_date": "明日",
        "location": "平泉地区", "contact_method": "電話", "detail_address": address,
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
        "title": "依頼", "content": "草刈り", "desired_date": "明日",
        "location": "平泉地区", "contact_method": "アプリ内チャット(Chat)",
        "detail_address": address,
    })
    assert response.status_code == 302
    if url == "/post":
        assert create.call_args.kwargs["detail_address"] == address.strip()
    else:
        post.save.assert_called_once()
        assert post.detail_address == address.strip()
