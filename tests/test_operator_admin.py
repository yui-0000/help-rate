from test_contact_approval import scenario
import pytest
import re
from werkzeug.security import check_password_hash, generate_password_hash
import app as application
import models


def test_old_automatic_admin_is_revoked_without_deleting_user_data(scenario):
    _, post, users, _, database = scenario
    database.execute_sql('ALTER TABLE "user" DROP COLUMN "admin_managed"')
    models.initialize()
    assert models.User.select().count() == 4
    assert models.Post.get_by_id(post.id).title == post.title
    assert models.User.select().where(models.User.is_admin == True).count() == 0
    assert all(not user.admin_managed for user in models.User.select())


def test_operator_grant_and_revoke_survive_restart(scenario):
    _, _, users, _, _ = scenario
    target = users[2]
    runner = application.app.test_cli_runner()
    granted = runner.invoke(args=["admin", "grant", str(target.id)], input="y\n")
    assert granted.exit_code == 0, granted.output
    assert target.username in granted.output
    stored = models.User.get_by_id(target.id)
    assert stored.is_admin and stored.admin_managed
    models.initialize()
    assert models.User.get_by_id(target.id).is_admin
    # Other ordinary users are never promoted by a role change.
    assert not models.User.get_by_id(users[1].id).is_admin
    revoked = runner.invoke(args=["admin", "revoke", str(target.id)], input="y\n")
    assert revoked.exit_code == 0, revoked.output
    models.initialize()
    assert not models.User.get_by_id(target.id).is_admin


def test_grant_requires_local_confirmation_and_existing_account(scenario):
    _, _, users, _, _ = scenario
    runner = application.app.test_cli_runner()
    refused = runner.invoke(args=["admin", "grant", str(users[2].id)], input="n\n")
    assert refused.exit_code != 0
    assert not models.User.get_by_id(users[2].id).is_admin
    unknown = runner.invoke(args=["admin", "grant", "99999"], input="y\n")
    assert unknown.exit_code != 0
    assert "存在しません" in unknown.output


def test_account_list_does_not_print_private_contacts(scenario):
    _, _, users, _, _ = scenario
    result = application.app.test_cli_runner().invoke(args=["admin", "list"])
    assert result.exit_code == 0, result.output
    assert users[0].username in result.output
    assert users[0].phone not in result.output
    assert users[0].password not in result.output


def test_untrusted_legacy_admin_loses_access_on_next_request(scenario):
    client, post, users, login, _ = scenario
    models.User.update(is_admin=True, admin_managed=False).where(models.User.id == users[2].id).execute()
    login(2)
    # before_request runs the migration before the logged-in user is loaded.
    response = client.get(f"/post/{post.id}")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="chatLogs"' not in html
    assert not models.User.get_by_id(users[2].id).is_admin


@pytest.mark.parametrize("password", ["123456789012345", "a" * 64])
def test_create_operator_without_personal_data_and_login(scenario, password):
    client, _, _, _, _ = scenario
    runner = application.app.test_cli_runner()
    result = runner.invoke(args=["admin", "create"], input=f"運営テスト\n{password}\n{password}\ny\n")
    assert result.exit_code == 0, result.output
    assert password not in result.output
    user = models.User.get(models.User.username == "運営テスト")
    assert user.is_admin and user.admin_managed
    assert all(getattr(user, field) == "" for field in (
        "last_name", "first_name", "last_name_kana", "first_name_kana", "phone",
    ))
    assert user.email is None and user.age is None and user.gender is None
    assert user.password != password
    assert check_password_hash(user.password, password)
    html = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)[1]
    response = client.post("/login", data={"login_id": "運営テスト", "password": password, "csrf_token": token})
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["_user_id"] == str(user.id)
    models.initialize()
    assert models.User.get_by_id(user.id).is_admin


@pytest.mark.parametrize("password", ["a" * 14, "a" * 65, " " * 15])
def test_operator_password_length_rejected_without_creating_account(scenario, password):
    _, _, _, _, _ = scenario
    count = models.User.select().count()
    result = application.app.test_cli_runner().invoke(
        args=["admin", "create"], input=f"運営テスト\n{password}\n{password}\ny\n",
    )
    assert result.exit_code != 0
    assert "15〜64文字" in result.output
    assert models.User.select().count() == count


def test_operator_creation_requires_matching_confirmation_and_final_approval(scenario):
    _, _, _, _, _ = scenario
    count = models.User.select().count()
    runner = application.app.test_cli_runner()
    mismatch = runner.invoke(args=["admin", "create"], input="運営テスト\nExamplePassword123\nDifferentPassword123\n")
    assert mismatch.exit_code != 0
    assert "ExamplePassword123" not in mismatch.output
    assert "DifferentPassword123" not in mismatch.output
    cancelled = runner.invoke(args=["admin", "create"], input="運営テスト\nExamplePassword123\nExamplePassword123\nn\n")
    assert cancelled.exit_code != 0
    assert models.User.select().count() == count


@pytest.mark.parametrize("identifier", ["user0", "090-1234-5678"])
def test_operator_creation_rejects_existing_login_identifier(scenario, identifier):
    _, _, _, _, _ = scenario
    count = models.User.select().count()
    result = application.app.test_cli_runner().invoke(args=["admin", "create"], input=identifier + "\n")
    assert result.exit_code != 0
    assert "すでに使用されています" in result.output
    assert models.User.select().count() == count


@pytest.mark.parametrize("password", ["123456789012345", "b" * 64])
def test_admin_password_reset_changes_only_password_and_allows_login(scenario, password):
    client, post, users, _, _ = scenario
    target = users[3]
    old_password = "OriginalPassword123"
    target.password = generate_password_hash(old_password)
    target.save()
    before = {user.id: dict(user.__data__) for user in models.User.select()}
    post_before = dict(models.Post.get_by_id(post.id).__data__)
    result = application.app.test_cli_runner().invoke(
        args=["admin", "reset-password"],
        input=f"{target.username}\ny\n{password}\n{password}\n",
    )
    assert result.exit_code == 0, result.output
    assert password not in result.output
    assert old_password not in result.output
    for user in models.User.select():
        saved = dict(user.__data__)
        if user.id == target.id:
            assert check_password_hash(saved["password"], password)
            assert not check_password_hash(saved["password"], old_password)
            saved["password"] = before[user.id]["password"]
        assert saved == before[user.id]
    assert dict(models.Post.get_by_id(post.id).__data__) == post_before
    html = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)[1]
    for candidate, status in [(old_password, 200), (password, 302)]:
        response = client.post("/login", data={
            "login_id": target.username, "password": candidate, "csrf_token": token,
        })
        assert response.status_code == status
    with client.session_transaction() as session:
        assert session["_user_id"] == str(target.id)


@pytest.mark.parametrize("password", ["a" * 14, "a" * 65, " " * 15])
def test_reset_rejects_invalid_password_without_changes(scenario, password):
    _, _, users, _, _ = scenario
    target = users[3]
    original = target.password
    result = application.app.test_cli_runner().invoke(
        args=["admin", "reset-password"],
        input=f"{target.username}\ny\n{password}\n{password}\n",
    )
    assert result.exit_code != 0
    assert "15〜64文字" in result.output
    assert models.User.get_by_id(target.id).password == original


@pytest.mark.parametrize("username", ["user0", "nonexistent"])
def test_reset_is_limited_to_existing_admins(scenario, username):
    _, _, _, _, _ = scenario
    before = {user.id: user.password for user in models.User.select()}
    result = application.app.test_cli_runner().invoke(
        args=["admin", "reset-password"], input=username + "\n",
    )
    assert result.exit_code != 0
    assert "管理者アカウントが見つかりません" in result.output
    assert before == {user.id: user.password for user in models.User.select()}


@pytest.mark.parametrize("answer", [
    "n\n",
    "y\nExamplePassword123\nDifferentPassword123\n",
])
def test_reset_cancellation_or_mismatch_does_not_change_password(scenario, answer):
    _, _, users, _, _ = scenario
    target = users[3]
    result = application.app.test_cli_runner().invoke(
        args=["admin", "reset-password"], input=target.username + "\n" + answer,
    )
    assert result.exit_code != 0
    assert models.User.get_by_id(target.id).password == target.password
    assert "ExamplePassword123" not in result.output
    assert "DifferentPassword123" not in result.output


def test_reset_aborts_when_admin_role_changes_during_prompt(scenario, monkeypatch):
    _, _, users, _, _ = scenario
    target = users[3]
    def revoke_while_prompting(prompt):
        models.User.update(is_admin=False).where(models.User.id == target.id).execute()
        return "ExamplePassword123"
    monkeypatch.setattr(application, "prompt_operator_password", revoke_while_prompting)
    result = application.app.test_cli_runner().invoke(
        args=["admin", "reset-password"], input=target.username + "\ny\n",
    )
    assert result.exit_code != 0
    assert "アカウントが変更されました" in result.output
    assert models.User.get_by_id(target.id).password == target.password
