from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, EqualTo
from flask_wtf.file import FileField, FileAllowed


class RegisterForm(FlaskForm):
    """新規ユーザー登録フォーム"""

    username = StringField("ユーザー名", validators=[DataRequired(), Length(min=2, max=50)])
    email = StringField("メールアドレス", validators=[DataRequired(), Email()])
    password = PasswordField("パスワード", validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField("パスワード（確認）", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("登録する")


class LoginForm(FlaskForm):
    """ログインフォーム"""

    email = StringField("メールアドレス", validators=[DataRequired(), Email()])
    password = PasswordField("パスワード", validators=[DataRequired()])
    submit = SubmitField("ログインする")


class PostForm(FlaskForm):
    """お手伝い案件投稿フォーム"""

    title = StringField("案件タイトル", validators=[DataRequired(), Length(max=100)])
    content = TextAreaField("依頼内容・詳細", validators=[DataRequired()])
    image = FileField(
        "現場の写真（任意）",
        validators=[
            FileAllowed(["jpg", "png", "jpeg"], "画像ファイル（jpg, png）のみアップロード可能です。")
        ],
    )
    submit = SubmitField("投稿する")
