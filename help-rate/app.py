import os
from flask import Flask, render_template, redirect, url_for, flash, request, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from models import db, User, Post
from forms import RegisterForm, LoginForm, PostForm

# .envファイルから環境変数を読み込む
load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "default-secret-key")
# 画像アップロード先のフォルダ設定
app.config["UPLOAD_FOLDER"] = "uploads"

# Flask-Loginの設定
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.get_by_id(int(user_id))
    except User.DoesNotExist:
        return None


@app.before_request
def before_request():
    db.connect()


@app.teardown_request
def teardown_request(exc):
    if not db.is_closed():
        db.close()


@app.route("/")
def index():
    """トップページ（案件一覧を表示）"""
    posts = Post.select().order_by(Post.created_at.desc())
    return render_template("index.html", posts=posts)


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    """アップロードされた画像をブラウザに配信するルート"""
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    form = RegisterForm()
    if form.validate_on_submit():
        if User.select().where(User.email == form.email.data).exists():
            flash("このメールアドレスは既に登録されています。", "danger")
            return render_template("register.html", form=form)

        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        user.save()

        flash("アカウントが作成されました！ログインしてください。", "success")
        return redirect(url_for("login"))

    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = User.get(User.email == form.email.data)
            if user.check_password(form.password.data):
                login_user(user)
                flash("ログインしました！", "success")
                return redirect(url_for("index"))
            else:
                flash("メールアドレスまたはパスワードが間違っています。", "danger")
        except User.DoesNotExist:
            flash("メールアドレスまたはパスワードが間違っています。", "danger")

    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("ログアウトしました。", "info")
    return redirect(url_for("index"))


@app.route("/post", methods=["GET", "POST"])
@login_required
def create_post():
    """お手伝い案件の投稿処理"""
    form = PostForm()
    if form.validate_on_submit():
        image_filename = None
        image_file = form.image.data
        if image_file and image_file.filename:
            filename = secure_filename(image_file.filename)
            filename = filename.replace(" ", "_")

            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            image_file.save(file_path)
            image_filename = filename

        Post.create(
            title=form.title.data, content=form.content.data, image_path=image_filename, author=current_user
        )
        flash("新しいお手伝い案件を投稿しました！", "success")
        return redirect(url_for("index"))

    return render_template("post.html", form=form)


@app.route("/delete/<int:post_id>", methods=["GET", "POST"])
@login_required
def delete_post(post_id):
    """お手伝い案件の削除処理（確認画面表示 ＆ 削除実行）"""
    try:
        post = Post.get_by_id(post_id)

        # 投稿者本人かどうかをチェック
        if post.author != current_user:
            flash("他のユーザーの投稿は削除できません。", "danger")
            return redirect(url_for("index"))

        # POSTリクエスト（確認画面で「本当に削除する」が押されたとき）
        if request.method == "POST":
            if post.image_path:
                image_path = os.path.join(app.config["UPLOAD_FOLDER"], post.image_path)
                if os.path.exists(image_path):
                    os.remove(image_path)

            post.delete_instance()
            flash("案件を削除しました。", "success")
            return redirect(url_for("index"))

        # GETリクエスト（削除確認画面を表示する）
        return render_template("delete_confirm.html", post=post)

    except Post.DoesNotExist:
        flash("該当する案件が見つかりませんでした。", "danger")
        return redirect(url_for("index"))


if __name__ == "__main__":
    db.connect()
    db.create_tables([User, Post], safe=True)
    db.close()
    app.run(debug=True, port=8000)
