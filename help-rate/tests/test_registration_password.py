import sys
from pathlib import Path

import pytest
from peewee import SqliteDatabase
from werkzeug.security import check_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as application
from models import User


@pytest.fixture
def registration_client(monkeypatch):
    monkeypatch.setitem(application.app.config, "_RETENTION_PURGE_AT", float("inf"))
    monkeypatch.setitem(application.app.config, "TESTING", True)
    monkeypatch.setitem(application.app.config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setitem(application.app.config, "_DATABASE_INITIALIZED", True)
    monkeypatch.setitem(application.app.config, "LOGIN_DISABLED", False)
    database = SqliteDatabase(":memory:")
    with database.bind_ctx([User]):
        database.connect()
        database.create_tables([User])
        yield application.app.test_client()
        database.close()


def registration_data():
    return dict(
        username="テスト用ニックネーム", last_name="姓", first_name="名",
        last_name_kana="せい", first_name_kana="めい", email="",
        password="ExamplePass123!", confirm_password="ExamplePass123!",
        phone="090-1234-5678", gender="その他", age="",
    )


@pytest.mark.parametrize("confirmation,error", [
    (None, "確認用パスワードを入力してください。"),
    ("", "確認用パスワードを入力してください。"),
    ("AnotherPass123!", "パスワードが一致しません。"),
    ("examplePass123!", "パスワードが一致しません。"),
    ("ExamplePass123! ", "パスワードが一致しません。"),
])
def test_invalid_confirmation_does_not_register_or_redisplay_password(registration_client, confirmation, error):
    data = registration_data()
    if confirmation is None:
        data.pop("confirm_password")
    else:
        data["confirm_password"] = confirmation
    response = registration_client.post("/register", data=data)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert error in html
    assert 'id="confirm-password-errors"' in html
    assert "ExamplePass123!" not in html
    assert "AnotherPass123!" not in html
    assert User.select().count() == 0


def test_matching_confirmation_registers_and_existing_login_still_works(registration_client):
    data = registration_data()
    response = registration_client.post("/register", data=data)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert User.select().count() == 1
    user = User.get()
    assert not user.is_admin
    assert not user.admin_managed
    assert user.password != data["password"]
    assert check_password_hash(user.password, data["password"])
    assert "confirm_password" not in User._meta.fields
    for identifier in (data["username"], data["phone"]):
        response = registration_client.post("/login", data={"login_id": identifier, "password": data["password"]})
        assert response.status_code == 302
        with registration_client.session_transaction() as session:
            assert session["_user_id"] == str(user.id)


def test_registration_fields_have_independent_toggle_controls(registration_client):
    html = registration_client.get("/register").get_data(as_text=True)
    assert 'id="confirmPasswordField"' in html
    assert 'name="confirm_password"' in html
    assert 'aria-controls="passwordField"' in html
    assert 'aria-controls="confirmPasswordField"' in html
    assert "確認のため、同じパスワードをもう一度入力してください。" in html


@pytest.mark.parametrize("password,valid", [
    ("12345", False), ("123456", True),
    ("1" * 20, True), ("1" * 21, False),
    ("abcdef", True), ("abc123", True),
])
def test_password_length_and_optional_character_mixing(registration_client, password, valid):
    data = registration_data()
    data.update(password=password, confirm_password=password)
    response = registration_client.post("/register", data=data)
    assert response.status_code == (302 if valid else 200)
    assert User.select().count() == int(valid)
    if not valid:
        assert "パスワードは6〜20文字で入力してください。" in response.get_data(as_text=True)


def test_registration_cannot_request_admin_even_as_first_user(registration_client):
    for index in range(2):
        data = registration_data()
        data.update(username=f"一般ユーザー{index}", is_admin="1", admin_managed="1")
        response = registration_client.post("/register", data=data)
        assert response.status_code == 302
        user = User.get(User.username == data["username"])
        assert not user.is_admin
        assert not user.admin_managed
