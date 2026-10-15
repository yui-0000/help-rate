from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, PasswordField, RadioField, SubmitField
from flask_wtf.file import FileField, FileAllowed


class RegisterForm(FlaskForm):
    username = StringField("ユーザー名")
    email = StringField("メールアドレス")
    password = PasswordField("パスワード")
    confirm_password = PasswordField("パスワード（確認用）")

    # ▼▼▼ プルダウンからラジオボタン（選択ボタン）に変更 ▼▼▼
    age_group = RadioField(
        "年代（任意）",
        choices=[
            ("未選択・非公開", "選択しない・非公開"),
            ("10代・20代", "10代・20代"),
            ("30代・40代", "30代・40代"),
            ("50代・60代", "50代・60代"),
            ("70代以上", "70代以上"),
        ],
        default="未選択・非公開",
    )

    gender = RadioField(
        "性別（任意）",
        choices=[
            ("未選択・非公開", "選択しない・非公開"),
            ("男性", "男性"),
            ("女性", "女性"),
            ("その他・回答しない", "その他・回答しない"),
        ],
        default="未選択・非公開",
    )
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

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
    reward = StringField("謝礼（例: 採れたて野菜 / お礼の品 など）")
    recommendation = StringField("推奨する助っ人像・条件（例: 重労働につき体力に自信のある方。任意）")
    image = FileField(
        "現場写真（任意）",
        validators=[FileAllowed(["jpg", "png", "jpeg"], "画像ファイルのみアップロード可能です")],
    )
    submit = SubmitField("投稿する")
