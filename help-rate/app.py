import os
import click
import time
import uuid
import re
import unicodedata
from datetime import timedelta
from functools import wraps
from peewee import IntegrityError
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory, abort, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileSize
from wtforms import StringField, PasswordField, TextAreaField, SubmitField, IntegerField, SelectField, HiddenField
from wtforms.validators import DataRequired, EqualTo, Length, Optional, Email, ValidationError
from schedule import ScheduleForm
from postal import normalize_postal_code, lookup_postal_code, PostalDataError

from models import User, Post, Message, ArchivedPhoto, initialize
from retention import utcnow, cutoff_time, purge_expired

app = Flask(__name__)
app.config["SECRET_KEY"] = "hiraizumi-secret-key"
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@app.before_request
def ensure_database_initialized():
    if not app.config.get("_DATABASE_INITIALIZED"):
        initialize()
        app.config["_DATABASE_INITIALIZED"] = True
    if time.monotonic() >= app.config.get("_RETENTION_PURGE_AT", 0):
        purge_expired(app.config["UPLOAD_FOLDER"])
        app.config["_RETENTION_PURGE_AT"] = time.monotonic() + 60


@app.after_request
def protect_private_responses(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    if request.path.startswith(("/admin", "/uploads/")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.template_filter("retention_date")
def retention_date(value):
    return (value + timedelta(hours=9)).strftime("%Y/%m/%d %H:%M") if value else "—"


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def get_live_post(post_id):
    try:
        post = Post.get_by_id(post_id)
    except Post.DoesNotExist:
        abort(404)
    if getattr(post, "deleted_at", None) is not None:
        abort(404)
    return post


def admin_page(query):
    page = max(1, request.args.get("page", 1, type=int))
    rows = list(query.offset((page - 1) * 20).limit(21))
    return rows[:20], page, len(rows) > 20


@app.route("/admin/users")
@admin_required
def admin_users():
    rows, page, more = admin_page(User.select(User.id, User.username, User.is_admin, User.deleted_at).where(
        User.deleted_at.is_null(True) | (User.deleted_at > cutoff_time())
    ).order_by(User.id))
    return render_template("admin.html", mode="users", rows=rows, page=page, more=more)


@app.route("/admin/users/<int:user_id>")
@admin_required
def admin_user(user_id):
    fields = [User.id, User.username, User.last_name, User.first_name, User.last_name_kana,
              User.first_name_kana, User.phone, User.email, User.gender, User.age, User.is_admin,
              User.admin_managed, User.deleted_at]
    user = User.select(*fields).where(User.id == user_id,
        User.deleted_at.is_null(True) | (User.deleted_at > cutoff_time())).get_or_none()
    if user is None:
        abort(404)
    return render_template("admin.html", mode="user", user=user)


@app.route("/admin/users/<int:user_id>/delete", methods=["GET", "POST"])
@admin_required
def admin_delete_user(user_id):
    user = User.get_or_none((User.id == user_id) & User.deleted_at.is_null(True))
    if user is None:
        abort(404)
    if user.is_admin or user.admin_managed or user.id == current_user.id:
        abort(403)
    form = DeleteAccountForm()
    if request.method == "POST":
        if form.validate_on_submit() and form.username.data == user.username:
            from models import db
            now = utcnow()
            with db.atomic():
                changed = User.update(deleted_at=now, deleted_by=current_user.id).where(
                    User.id == user.id, User.is_admin == False, User.admin_managed == False,
                    User.deleted_at.is_null(True)
                ).execute()
                if changed != 1:
                    abort(409)
                Post.update(deleted_at=now, deleted_by=current_user.id).where(
                    Post.author == user, Post.deleted_at.is_null(True)
                ).execute()
                Message.update(deleted_at=now, deleted_by=current_user.id).where(
                    Message.sender == user, Message.deleted_at.is_null(True)
                ).execute()
                Post.update(helper=None, helper_message=None, contact_shared=False).where(
                    Post.helper == user, Post.deleted_at.is_null(True)
                ).execute()
            flash("一般ユーザーのアカウントを削除しました。関連データは90日間保管します。")
            return redirect(url_for("admin_users"))
        form.username.errors = list(form.username.errors) + ["確認のため、対象のニックネームを正確に入力してください。"]
    return render_template("admin.html", mode="delete_user", user=user, form=form)


@app.route("/admin/deleted-posts")
@admin_required
def admin_deleted_posts():
    rows, page, more = admin_page(Post.select().where(Post.deleted_at > cutoff_time()).order_by(Post.deleted_at.desc(), Post.id.desc()))
    return render_template("admin.html", mode="posts", rows=rows, page=page, more=more)


@app.route("/admin/deleted-posts/<int:post_id>")
@admin_required
def admin_deleted_post(post_id):
    post = Post.get_or_none((Post.id == post_id) & (Post.deleted_at > cutoff_time()))
    if post is None:
        abort(404)
    messages, page, more = admin_page(Message.select().where(
        Message.post == post, (Message.deleted_at.is_null(True)) | (Message.deleted_at > cutoff_time())
    ).order_by(Message.created_at, Message.id))
    return render_template("admin.html", mode="post", post=post, rows=messages, page=page, more=more)


@app.route("/admin/deleted-messages")
@admin_required
def admin_deleted_messages():
    rows, page, more = admin_page(Message.select(Message, Post).join(Post).where(
        Message.deleted_at > cutoff_time(),
        Post.deleted_at.is_null(True) | (Post.deleted_at > cutoff_time())
    ).order_by(Message.deleted_at.desc(), Message.id.desc()))
    return render_template("admin.html", mode="messages", rows=rows, page=page, more=more)


@app.route("/admin/deleted-photos")
@admin_required
def admin_deleted_photos():
    rows, page, more = admin_page(ArchivedPhoto.select(ArchivedPhoto, Post).join(Post).where(
        ArchivedPhoto.deleted_at > cutoff_time(),
        Post.deleted_at.is_null(True) | (Post.deleted_at > cutoff_time())
    ).order_by(ArchivedPhoto.deleted_at.desc(), ArchivedPhoto.id.desc()))
    return render_template("admin.html", mode="photos", rows=rows, page=page, more=more)


@app.cli.group("admin")
def admin_commands():
    """サーバーを操作できる運営者専用の管理者権限設定。"""


@admin_commands.command("list")
def list_admin_accounts():
    """ユーザーID、ニックネーム、権限を確認する。"""
    initialize()
    from models import db
    with db.connection_context():
        for user in User.select().order_by(User.id):
            click.echo(f"ID={user.id}  {user.username}  {'管理者' if user.is_admin else '一般ユーザー'}")


def prompt_operator_password(prompt="運営用パスワード"):
    click.echo("運営用パスワードは15〜64文字です。英字と数字の混在は必須ではありません。")
    password = click.prompt(
        prompt, hide_input=True,
        confirmation_prompt="確認のため、もう一度入力してください",
    )
    if not password.strip() or not 15 <= len(password) <= 64:
        raise click.ClickException("運営用パスワードは15〜64文字で入力してください。")
    return password


@admin_commands.command("reset-password")
def reset_admin_password():
    """管理者のパスワードだけを、サーバー端末から再設定する。"""
    initialize()
    from models import db
    with db.connection_context():
        username = click.prompt("再設定する運営用ログイン名").strip()
        user = User.get_or_none(
            (User.username == username) & (User.is_admin == True) & (User.admin_managed == True)
        )
        if user is None:
            raise click.ClickException("指定した管理者アカウントが見つかりません。ログイン名を確認してください。")
        click.confirm(f"ID={user.id} ログイン名={user.username} のパスワードを再設定しますか？", abort=True)
        password = prompt_operator_password("新しい運営用パスワード")
        with db.atomic():
            updated = User.update(password=generate_password_hash(password)).where(
                User.id == user.id, User.username == user.username,
                User.is_admin == True, User.admin_managed == True,
                User.password == user.password,
            ).execute()
            if updated != 1:
                raise click.ClickException("アカウントが変更されました。対象を確認してやり直してください。")
        click.echo("管理者のパスワードを再設定しました。新しいパスワードでログインしてください。")


@admin_commands.command("create")
def create_admin_account():
    """氏名や電話番号を入力せず、運営用アカウントを対話形式で作成する。"""
    initialize()
    from models import db
    with db.connection_context():
        username = click.prompt("運営用ログイン名").strip()
        if not username:
            raise click.ClickException("運営用ログイン名を入力してください。")
        if User.select().where(
            (User.username == username) | (User.email == username) | (User.phone == username)
        ).exists():
            raise click.ClickException("このログイン名はすでに使用されています。別の名前を指定してください。")
        password = prompt_operator_password()
        click.confirm(f"ログイン名={username} の運営用管理者アカウントを作成しますか？", abort=True)
        try:
            with db.atomic():
                user = User.create(
                    username=username, password=generate_password_hash(password),
                    last_name="", first_name="", last_name_kana="", first_name_kana="",
                    phone="", email=None, gender=None, age=None,
                    is_admin=True, admin_managed=True,
                )
        except IntegrityError:
            raise click.ClickException("このログイン名はすでに使用されています。別の名前を指定してください。")
        click.echo(f"運営用アカウントを作成しました。ID={user.id} ログイン名={user.username}")
        click.echo("通常のログイン画面で、このログイン名とパスワードを使ってログインできます。")


def change_admin_role(user_id, grant):
    initialize()
    from models import db
    with db.connection_context():
        try:
            user = User.get_by_id(user_id)
            if user.deleted_at is not None:
                raise click.ClickException("削除済みアカウントの権限は変更できません。")
        except User.DoesNotExist:
            raise click.ClickException("指定したユーザーIDは存在しません。")
        role = "管理者" if grant else "一般ユーザー"
        click.confirm(f"ID={user.id} ニックネーム={user.username} を{role}に変更しますか？", abort=True)
        with db.atomic():
            updated = User.update(is_admin=grant, admin_managed=True).where(
                User.id == user.id, User.username == user.username
            ).execute()
            if updated != 1:
                raise click.ClickException("ユーザー情報が変更されました。対象を確認し直してください。")
        click.echo(f"ID={user.id} の権限を{role}に変更しました。")


@admin_commands.command("grant")
@click.argument("user_id", type=click.IntRange(min=1))
def grant_admin(user_id):
    """確認した運営者のユーザーIDを指定して管理者権限を付与する。"""
    change_admin_role(user_id, True)


@admin_commands.command("revoke")
@click.argument("user_id", type=click.IntRange(min=1))
def revoke_admin(user_id):
    """指定したユーザーの管理者権限を解除する。"""
    change_admin_role(user_id, False)


class ContactApprovalForm(FlaskForm):
    helper_id = HiddenField(validators=[DataRequired()])


class DeleteForm(FlaskForm):
    pass


class DeleteAccountForm(FlaskForm):
    username = StringField("削除するニックネームを再入力", validators=[DataRequired()])


@login_manager.user_loader
def load_user(user_id):
    try:
        user = User.get_by_id(user_id)
        return user if user.deleted_at is None else None
    except User.DoesNotExist:
        return None


class RegisterForm(FlaskForm):
    username = StringField(
        "ニックネーム（ウェブ表示名・重複不可）",
        validators=[DataRequired(message="ニックネームを入力してください。")],
    )
    last_name = StringField("姓（苗字）", validators=[DataRequired(message="姓を入力してください。")])
    first_name = StringField("名（名前）", validators=[DataRequired(message="名を入力してください。")])
    last_name_kana = StringField(
        "姓のふりがな", validators=[DataRequired(message="姓のふりがなを入力してください。")]
    )
    first_name_kana = StringField(
        "名のふりがな", validators=[DataRequired(message="名のふりがなを入力してください。")]
    )

    email = StringField("メールアドレス（任意・代理人のものでも可）", validators=[Optional()])
    password = PasswordField(
        "パスワード",
        validators=[
            DataRequired(message="パスワードを入力してください。"),
            Length(min=6, max=20, message="パスワードは6〜20文字で入力してください。"),
        ],
    )
    confirm_password = PasswordField(
        "パスワード（確認用）",
        validators=[
            DataRequired(message="確認用パスワードを入力してください。"),
            EqualTo("password", message="パスワードが一致しません。同じパスワードを入力してください。"),
        ],
    )
    phone = StringField("電話番号", validators=[Optional()])
    gender = SelectField(
        "性別",
        choices=[("", "選択してください"), ("男性", "男性"), ("女性", "女性"), ("その他", "その他")],
        validators=[DataRequired(message="性別を選択してください。")],
    )
    age = IntegerField("年齢", validators=[Optional()])
    submit = SubmitField("登録する")


class LoginForm(FlaskForm):
    login_id = StringField(
        "ログインID（ニックネーム / メール / 電話番号）",
        validators=[DataRequired(message="ニックネーム、メールアドレス、または電話番号を入力してください。")],
    )
    password = PasswordField(
        "パスワード", validators=[DataRequired(message="パスワードを入力してください。")]
    )
    submit = SubmitField("ログイン")


class PostForm(ScheduleForm):
    title = StringField("タイトル", validators=[DataRequired()])
    content = TextAreaField("内容", validators=[DataRequired()])
    postal_code = StringField("来てほしい場所の郵便番号（住所入力の補助）", filters=[normalize_postal_code], validators=[Optional()])
    place_notes = TextAreaField("目印・集合場所（任意）", filters=[lambda value: value.strip() if value else value], validators=[Optional(), Length(max=500, message="目印・集合場所は500文字以内で入力してください。")])

    def validate_postal_code(self, field):
        if not re.fullmatch(r"[0-9]{7}", field.data):
            raise ValidationError("郵便番号は7桁の数字で入力してください。")

    def validate_detail_address(self, field):
        if re.fullmatch(r"[0-9]{7}", self.postal_code.data or ""):
            try:
                candidates = lookup_postal_code(self.postal_code.data)
            except PostalDataError:
                return  # データを読めない場合も手入力は妨げない。
            if field.data in candidates and not self.place_notes.data:
                raise ValidationError("番地・建物名を追記してください。番地がない場所は目印・集合場所を入力してください。")
    location = SelectField(
        "大まかな場所（地区名など）",
        choices=[
            ("", "地域を選択してください"),
            ("平泉地区", "平泉地区"),
            ("衣川地区", "衣川地区"),
            ("中尊寺周辺", "中尊寺周辺"),
            ("平泉駅周辺", "平泉駅周辺"),
            ("その他・町内全域", "その他・町内全域"),
        ],
        validators=[DataRequired()],
    )
    detail_address = StringField(
        "来てほしい場所の住所",
        filters=[lambda value: value.strip() if value else value],
        validators=[
            DataRequired(message="来てほしい場所の住所を入力してください。"),
            Length(min=10, max=500, message="来てほしい場所の住所を10〜500文字で具体的に入力してください。"),
        ],
    )
    contact_phone = StringField("連絡先の電話番号", filters=[lambda value: unicodedata.normalize("NFKC", value).strip() if value else value],
                               validators=[Optional(), Length(max=13, message="電話番号は10〜11桁、ハイフンを含めて13文字以内で入力してください。")])
    contact_email = StringField("連絡先のメールアドレス", filters=[lambda value: value.strip() if value else value],
                               validators=[Optional(), Length(max=254), Email(message="@の後ろも含め、正しいメールアドレスを入力してください（例：taro@example.com）。")])

    def validate_contact_phone(self, field):
        digits = field.data.replace("-", "")
        if not re.fullmatch(r"[0-9-]+", field.data) or field.data.count("-") > 2 or not re.fullmatch(r"0[0-9]{9,10}", digits):
            raise ValidationError("電話番号は0から始まる10〜11桁で入力してください（携帯：090-1234-5678、固定：03-1234-5678）。")

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators=extra_validators)
        if not self.contact_phone.data and not self.contact_email.data:
            self.contact_phone.errors = list(self.contact_phone.errors) + ["電話番号かメールアドレスのどちらか一方を入力してください。"]
            valid = False
        return valid

    contact_method = SelectField(
        "連絡希望方法",
        choices=[
            ("アプリ内チャット(Chat)", "アプリ内チャット(Chat)"),
            ("電話", "電話"),
            ("メール", "メール"),
        ],
        validators=[DataRequired()],
    )
    reward = StringField("謝礼・おすそ分け")
    recommendation = StringField("推奨する助っ人像")
    image = FileField("現場写真", validators=[
        FileAllowed(["jpg", "png", "jpeg"], "JPG・PNG形式の写真を選んでください。"),
        FileSize(max_size=5 * 1024 * 1024, message="写真は1枚5MB以内にしてください。"),
    ])
    submit = SubmitField("投稿する")


@app.route("/")
def index():
    posts, selected_status, selected_owner = filtered_posts()
    return render_template("index.html", posts=posts, selected_status=selected_status, selected_owner=selected_owner)


def filtered_posts():
    selected_status = request.args.get("status", "all")
    selected_owner = request.args.get("owner", "all")
    if not current_user.is_authenticated or selected_owner not in ("all", "mine", "others"):
        selected_owner = "all"
    filters = {
        "open": (Post.is_completed == False) & Post.helper.is_null(True),
        "discussing": (Post.is_completed == False) & Post.helper.is_null(False) & (Post.contact_shared == False),
        "active": (Post.is_completed == False) & Post.helper.is_null(False) & (Post.contact_shared == True),
        "completed": Post.is_completed == True,
    }
    posts = Post.select().where(Post.deleted_at.is_null(True))
    if selected_owner == "mine":
        posts = posts.where(Post.author == current_user.id)
    elif selected_owner == "others":
        posts = posts.where(Post.author != current_user.id)
    if selected_status in filters:
        posts = posts.where(filters[selected_status])
    else:
        selected_status = "all"
    return posts.order_by(Post.is_completed.asc(), Post.created_at.desc(), Post.id.desc()), selected_status, selected_owner


@app.route("/posts/list")
def posts_list():
    posts, selected_status, selected_owner = filtered_posts()
    return render_template("_posts_list.html", posts=posts, selected_status=selected_status, selected_owner=selected_owner), 200, {"Cache-Control": "no-store"}


@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if request.method == "POST":
        phone_val = request.form.get("phone", "").strip()
        if not phone_val or phone_val == "--":
            flash("電話番号を入力してください。", "danger")
            return render_template("register.html", form=form)

        if form.validate_on_submit():
            email_val = form.email.data.strip() if form.email.data else ""
            if email_val and "@" not in email_val:
                flash("有効なメールアドレスを入力してください（@が含まれていません）。", "danger")
                return render_template("register.html", form=form)

            try:
                User.get(User.username == form.username.data)
                flash(
                    "そのニックネームはすでに使われています。別のニックネームを指定してください。", "danger"
                )
            except User.DoesNotExist:
                hashed_password = generate_password_hash(form.password.data)
                User.create(
                    username=form.username.data,
                    last_name=form.last_name.data,
                    first_name=form.first_name.data,
                    last_name_kana=form.last_name_kana.data,
                    first_name_kana=form.first_name_kana.data,
                    email=email_val or None,
                    password=hashed_password,
                    phone=phone_val,
                    gender=form.gender.data,
                    age=form.age.data,
                    is_admin=False,
                    admin_managed=False,
                )
                flash("ユーザー登録が完了しました。ログインしてください。", "success")
                return redirect(url_for("login"))
        else:
            error_messages = []
            for field, errors in form.errors.items():
                for error in errors:
                    error_messages.append(error)
            if error_messages:
                flash("入力エラー: " + " / ".join(error_messages), "danger")
            else:
                flash("入力内容に誤りがあります。項目をご確認ください。", "danger")

    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = None
        identifier = form.login_id.data.strip()
        try:
            user = User.get(
                ((User.username == identifier) | (User.email == identifier) | (User.phone == identifier))
                & User.deleted_at.is_null(True)
            )
        except User.DoesNotExist:
            pass

        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for("index"))
        else:
            flash("ログインID（ニックネーム / メール / 電話番号）またはパスワードが間違っています。")
    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/post", methods=["GET", "POST"])
@login_required
def create_post():
    form = PostForm()
    if form.validate_on_submit():
        filename = None
        if form.image.data:
            f = form.image.data
            filename = uuid.uuid4().hex + "." + f.filename.rsplit(".", 1)[-1].lower()
            f.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        Post.create(
            title=form.title.data,
            content=form.content.data,
            desired_date=form.schedule_text(),
            location=form.location.data,
            detail_address=form.detail_address.data,
            postal_code=form.postal_code.data or None,
            place_notes=form.place_notes.data or None,
            contact_phone=form.contact_phone.data or None,
            contact_email=form.contact_email.data or None,
            contact_method=form.contact_method.data,
            reward=form.reward.data,
            recommendation=form.recommendation.data,
            image_path=filename,
            author=current_user,
        )
        flash("お手伝い案件を投稿しました！")
        return redirect(url_for("index"))
    return render_template("post.html", form=form)


@app.get("/postal-addresses")
@login_required
def postal_address_search():
    try:
        addresses = lookup_postal_code(request.args.get("postal_code", ""))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except PostalDataError:
        return jsonify(error="住所検索が利用できません。住所を直接入力してください。"), 503
    response = jsonify(addresses=addresses)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/post/<int:post_id>")
def post_detail(post_id):
    try:
        post = get_live_post(post_id)
    except Post.DoesNotExist:
        flash("指定された案件は見つかりません。")
        return redirect(url_for("index"))

    messages = []
    is_authorized = current_user.is_authenticated and (
        post.author == current_user or post.helper == current_user or current_user.is_admin
    )

    if is_authorized:
        messages = Message.select().where(Message.post == post, Message.deleted_at.is_null(True)).order_by(Message.created_at.asc())

    approval_form = ContactApprovalForm(helper_id=str(post.helper_id or ""))
    return render_template(
        "detail.html", post=post, messages=messages,
        is_authorized=is_authorized, approval_form=approval_form, delete_form=DeleteForm(),
    )


@app.route("/post/<int:post_id>/share-contact", methods=["POST"])
@login_required
def share_contact(post_id):
    post = get_live_post(post_id)
    if post.author != current_user:
        abort(403)
    form = ContactApprovalForm()
    if not form.validate_on_submit():
        abort(400)
    updated = (Post.update(contact_shared=True)
               .where(Post.id == post_id, Post.author == current_user.id,
                      Post.helper.is_null(False), Post.helper == form.helper_id.data,
                      Post.is_completed == False, Post.deleted_at.is_null(True))
               .execute())
    if not updated:
        abort(409)
    flash("助っ人を確定し、この相手に住所・連絡先を公開しました。")
    return redirect(url_for("post_detail", post_id=post_id))


@app.route("/post/<int:post_id>/complete", methods=["POST"])
@login_required
def complete_post(post_id):
    post = get_live_post(post_id)
    if post.author != current_user:
        abort(403)
    form = ContactApprovalForm()
    if not form.validate_on_submit():
        abort(400)
    updated = (Post.update(is_completed=True)
               .where(Post.id == post_id, Post.author == current_user.id,
                      Post.contact_shared == True, Post.is_completed == False,
                      Post.helper.is_null(False), Post.helper == form.helper_id.data,
                      Post.deleted_at.is_null(True))
               .execute())
    if not updated:
        abort(409)
    flash("依頼を終了しました。助っ人の方にも終了済みと表示されます。")
    return redirect(url_for("post_detail", post_id=post_id))


@app.route("/post/<int:post_id>/message", methods=["POST"])
@login_required
def send_message(post_id):
    post = get_live_post(post_id)
    if not (post.author == current_user or post.helper == current_user or current_user.is_admin):
        flash("このチャットに書き込む権限がありません。")
        return redirect(url_for("post_detail", post_id=post.id))

    message_text = request.form.get("message_text")
    if message_text:
        Message.create(post=post, sender=current_user, content=message_text)
    return redirect(url_for("post_detail", post_id=post.id))


@app.route("/message/<int:message_id>/delete", methods=["POST"])
@login_required
def delete_message(message_id):
    try:
        msg = Message.get_by_id(message_id)
        get_live_post(msg.post_id)
        if msg.deleted_at is not None:
            abort(404)
        if msg.sender == current_user or current_user.is_admin:
            post_id = msg.post.id
            if not DeleteForm().validate_on_submit():
                abort(400)
            Message.update(deleted_at=utcnow(), deleted_by=current_user.id).where(
                Message.id == msg.id, Message.deleted_at.is_null(True)
            ).execute()
            flash("メッセージを取り消しました。")
            return redirect(url_for("post_detail", post_id=post_id))
        else:
            flash("このメッセージを削除する権限がありません。")
            return redirect(url_for("index"))
    except Message.DoesNotExist:
        flash("指定されたメッセージは見つかりません。")
        return redirect(url_for("index"))


@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    post = get_live_post(post_id)
    if post.author != current_user and not current_user.is_admin:
        flash("編集権限がありません。")
        return redirect(url_for("post_detail", post_id=post.id))

    form = PostForm(obj=post)
    if form.validate_on_submit():
        old_image = post.image_path if form.image.data else None
        post.title = form.title.data
        post.content = form.content.data
        post.desired_date = form.schedule_text()
        post.location = form.location.data
        post.detail_address = form.detail_address.data
        post.postal_code = form.postal_code.data or None
        post.place_notes = form.place_notes.data or None
        post.contact_phone = form.contact_phone.data or None
        post.contact_email = form.contact_email.data or None
        post.contact_method = form.contact_method.data
        post.reward = form.reward.data
        post.recommendation = form.recommendation.data

        if form.image.data:
            f = form.image.data
            filename = uuid.uuid4().hex + "." + f.filename.rsplit(".", 1)[-1].lower()
            f.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            post.image_path = filename

        edited_fields = [Post.title, Post.content, Post.desired_date, Post.location,
                         Post.detail_address, Post.postal_code, Post.place_notes, Post.contact_phone, Post.contact_email, Post.contact_method, Post.reward,
                         Post.recommendation]
        if form.image.data:
            edited_fields.append(Post.image_path)
        if old_image:
            with Post._meta.database.atomic():
                post.save(only=edited_fields)
                ArchivedPhoto.create(post=post, filename=old_image, deleted_at=utcnow())
        else:
            post.save(only=edited_fields)
        flash("案件内容を更新しました！")
        return redirect(url_for("post_detail", post_id=post.id))
    return render_template("edit.html", form=form, post=post)


@app.route("/post/<int:post_id>/delete", methods=["GET", "POST"])
@login_required
def delete_post(post_id):
    post = get_live_post(post_id)
    if post.author == current_user or current_user.is_admin:
        form = DeleteForm()
        if request.method == "GET":
            return render_template("delete_confirm.html", post=post, form=form)
        if not form.validate_on_submit():
            abort(400)
        Post.update(deleted_at=utcnow(), deleted_by=current_user.id).where(
            Post.id == post.id, Post.deleted_at.is_null(True)
        ).execute()
        flash("案件を削除しました。")
    else:
        flash("削除権限がありません。")
    return redirect(url_for("index"))


@app.route("/post/<int:post_id>/apply", methods=["GET", "POST"])
@login_required
def apply_post(post_id):
    post = get_live_post(post_id)
    if post.is_completed:
        flash("この依頼は終了しているため、応募できません。")
        return redirect(url_for("post_detail", post_id=post.id))
    if post.author == current_user:
        flash("ご自身の案件には応募できません。")
        return redirect(url_for("post_detail", post_id=post.id))
    if post.helper:
        flash("すでに応募者と相談中、または助っ人が決定している案件です。")
        return redirect(url_for("post_detail", post_id=post.id))

    (request.method == "POST")  # カッコのバランスを綺麗に整理
    if request.method == "POST":
        helper_message = request.form.get("helper_message")
        post.helper = current_user
        post.helper_message = helper_message
        post.contact_shared = False
        post.save(only=[Post.helper, Post.helper_message, Post.contact_shared])
        flash("助っ人として応募が完了しました！")
        return redirect(url_for("post_detail", post_id=post.id))

    return (
        render_template("apply_apply.html", post=post)
        if False
        else render_template("apply_confirm.html", post=post)
    )


@app.route("/post/<int:post_id>/cancel", methods=["GET", "POST"])
@login_required
def cancel_confirm(post_id):
    post = get_live_post(post_id)
    if post.is_completed:
        flash("終了済みの依頼は、応募を取り消せません。")
        return redirect(url_for("post_detail", post_id=post.id))
    if post.helper != current_user:
        flash("この応募を取り消す権限はありません。")
        return redirect(url_for("post_detail", post_id=post.id))

    if request.method == "POST":
        post.helper = None
        post.helper_message = None
        post.contact_shared = False
        post.save(only=[Post.helper, Post.helper_message, Post.contact_shared])
        flash("応募を取り消しました。")
        return redirect(url_for("post_detail", post_id=post.id))

    return render_template("cancel_confirm.html", post=post)


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    references = Post.select().where(Post.image_path == filename)
    if not references.where(Post.deleted_at.is_null(True)).exists():
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(404)
        archived = ArchivedPhoto.select().join(Post).where(
            ArchivedPhoto.filename == filename, ArchivedPhoto.deleted_at > cutoff_time(),
            Post.deleted_at.is_null(True) | (Post.deleted_at > cutoff_time())
        ).exists()
        if not references.where(Post.deleted_at > cutoff_time()).exists() and not archived:
            abort(404)
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


if __name__ == "__main__":
    app.run(port=8000, debug=True)
