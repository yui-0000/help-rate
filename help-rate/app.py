import os
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, TextAreaField, SubmitField, IntegerField, SelectField
from wtforms.validators import DataRequired, Optional

from models import User, Post, Message, initialize

app = Flask(__name__)
app.config["SECRET_KEY"] = "hiraizumi-secret-key"
app.config["UPLOAD_FOLDER"] = "uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.get_by_id(user_id)
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
        "パスワード", validators=[DataRequired(message="パスワードを入力してください。")]
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


class PostForm(FlaskForm):
    title = StringField("タイトル", validators=[DataRequired()])
    content = TextAreaField("内容", validators=[DataRequired()])
    desired_date = StringField("実施希望日時", validators=[DataRequired()])
    location = SelectField(
        "大まかな場所（地区名など）",
        choices=[
            ("平泉地区", "平泉地区"),
            ("衣川地区", "衣川地区"),
            ("中尊寺周辺", "中尊寺周辺"),
            ("平泉駅周辺", "平泉駅周辺"),
            ("その他・町内全域", "その他・町内全域"),
        ],
        validators=[DataRequired()],
    )
    detail_address = StringField("詳細な住所・連絡先", validators=[DataRequired()])
    contact_method = SelectField(
        "連絡希望方法",
        choices=[
            ("電話", "電話"),
            ("メール", "メール"),
            ("アプリ内チャット(Chat)", "アプリ内チャット(Chat)"),
        ],
        validators=[DataRequired()],
    )
    reward = StringField("謝礼")
    recommendation = StringField("推奨する助っ人像")
    image = FileField("現場写真", validators=[FileAllowed(["jpg", "png", "jpeg"], "Images only!")])
    submit = SubmitField("投稿する")


@app.route("/")
def index():
    posts = Post.select().order_by(Post.created_at.desc())
    return render_template("index.html", posts=posts)


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
                is_first = User.select().count() == 0
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
                    is_admin=is_first,
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
                (User.username == identifier) | (User.email == identifier) | (User.phone == identifier)
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
            filename = secure_filename(f.filename)
            f.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        Post.create(
            title=form.title.data,
            content=form.content.data,
            desired_date=form.desired_date.data,
            location=form.location.data,
            detail_address=form.detail_address.data,
            contact_method=form.contact_method.data,
            reward=form.reward.data,
            recommendation=form.recommendation.data,
            image_path=filename,
            author=current_user,
        )
        flash("お手伝い案件を投稿しました！")
        return redirect(url_for("index"))
    return render_template("post.html", form=form)


@app.route("/post/<int:post_id>")
def post_detail(post_id):
    try:
        post = Post.get_by_id(post_id)
    except Post.DoesNotExist:
        flash("指定された案件は見つかりません。")
        return redirect(url_for("index"))

    messages = []
    is_authorized = current_user.is_authenticated and (
        post.author == current_user or post.helper == current_user or current_user.is_admin
    )

    if is_authorized:
        messages = Message.select().where(Message.post == post).order_by(Message.created_at.asc())

    return render_template("detail.html", post=post, messages=messages, is_authorized=is_authorized)


@app.route("/post/<int:post_id>/message", methods=["POST"])
@login_required
def send_message(post_id):
    post = Post.get_by_id(post_id)
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
        if msg.sender == current_user or current_user.is_admin:
            post_id = msg.post.id
            msg.delete_instance()
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
    post = Post.get_by_id(post_id)
    if post.author != current_user and not current_user.is_admin:
        flash("編集権限がありません。")
        return redirect(url_for("post_detail", post_id=post.id))

    form = PostForm(obj=post)
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        post.desired_date = form.desired_date.data
        post.location = form.location.data
        post.detail_address = form.detail_address.data
        post.contact_method = form.contact_method.data
        post.reward = form.reward.data
        post.recommendation = form.recommendation.data

        if form.image.data:
            f = form.image.data
            filename = secure_filename(f.filename)
            f.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            post.image_path = filename

        post.save()
        flash("案件内容を更新しました！")
        return redirect(url_for("post_detail", post_id=post.id))
    return render_template("edit.html", form=form, post=post)


@app.route("/post/<int:post_id>/delete")
@login_required
def delete_post(post_id):
    post = Post.get_by_id(post_id)
    if post.author == current_user or current_user.is_admin:
        Message.delete().where(Message.post == post).execute()
        post.delete_instance()
        flash("案件を削除しました。")
    else:
        flash("削除権限がありません。")
    return redirect(url_for("index"))


@app.route("/post/<int:post_id>/apply", methods=["GET", "POST"])
@login_required
def apply_post(post_id):
    post = Post.get_by_id(post_id)
    if post.author == current_user:
        flash("ご自身の案件には応募できません。")
        return redirect(url_for("post_detail", post_id=post.id))
    if post.helper:
        flash("すでに助っ人が決定している案件です。")
        return redirect(url_for("post_detail", post_id=post.id))

    (request.method == "POST")  # カッコのバランスを綺麗に整理
    if request.method == "POST":
        helper_message = request.form.get("helper_message")
        post.helper = current_user
        post.helper_message = helper_message
        post.save()
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
    post = Post.get_by_id(post_id)
    if post.helper != current_user:
        flash("この応募を取り消す権限はありません。")
        return redirect(url_for("post_detail", post_id=post.id))

    if request.method == "POST":
        post.helper = None
        post.helper_message = None
        post.save()
        flash("応募を取り消しました。")
        return redirect(url_for("post_detail", post_id=post.id))

    return render_template("cancel_confirm.html", post=post)


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


if __name__ == "__main__":
    initialize()
    app.run(port=8000, debug=True)
