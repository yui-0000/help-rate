from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, PasswordField, SubmitField
from flask_wtf.file import FileField, FileAllowed


class RegisterForm(FlaskForm):
    username = StringField("ユーザー名")
    email = StringField("メールアドレス")
    password = PasswordField("パスワード")
    confirm_password = PasswordField("パスワード（確認用）")
    submit = SubmitField("登録する")


class LoginForm(FlaskForm):
    email = StringField("メールアドレス")
    password = PasswordField("パスワード")
    submit = SubmitField("ログインする")


class PostForm(FlaskForm):
    title = StringField("案件タイトル")
    content = TextAreaField("お手伝いの内容詳細")
    desired_date = StringField("実施希望日時（例: 10月25日 13:00〜）")
    location = StringField("作業場所・エリア（例: 平泉字衣関）")
    reward = StringField("謝礼・金品（例: 現金 3,000円 / 野菜の詰め合わせ など）")
    image = FileField(
        "現場写真（任意）",
        validators=[FileAllowed(["jpg", "png", "jpeg"], "画像ファイルのみアップロード可能です")],
    )
    submit = SubmitField("投稿する")
