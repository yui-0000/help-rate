import os
from peewee import SqliteDatabase, Model, CharField, TextField, DateTimeField, ForeignKeyField
from datetime import datetime

# データベースファイルのパス設定（プロジェクト直下に help_rate.db を作成）
db_path = os.path.join(os.path.dirname(__file__), "help_rate.db")
db = SqliteDatabase(db_path)


class BaseModel(Model):
    """すべてのモデルの共通ベースクラス"""

    class Meta:
        database = db


class User(BaseModel):
    """ユーザーモデル"""

    username = CharField(unique=True, max_length=50)
    email = CharField(unique=True, max_length=100)
    password = CharField(max_length=255)  # ハッシュ化されたパスワードを保存


class Post(BaseModel):
    """お手伝い案件の投稿モデル"""

    title = CharField(max_length=100)
    content = TextField()
    image_path = CharField(max_length=255, null=True)  # 画像の保存パス（後ほど使用）
    author = ForeignKeyField(User, backref="posts")
    created_at = DateTimeField(default=datetime.now)


import os
from peewee import SqliteDatabase, Model, CharField, TextField, DateTimeField, ForeignKeyField
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# データベースファイルのパス設定
db_path = os.path.join(os.path.dirname(__file__), "help_rate.db")
db = SqliteDatabase(db_path)


class BaseModel(Model):
    class Meta:
        database = db


class User(UserMixin, BaseModel):
    """ユーザーモデル（Flask-Login対応、パスワードハッシュ化保持）"""

    username = CharField(unique=True, max_length=50)
    email = CharField(unique=True, max_length=100)
    password_hash = CharField(max_length=255)

    def set_password(self, password):
        """パスワードをハッシュ化して保存"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """入力されたパスワードが一致するか検証"""
        return check_password_hash(self.password_hash, password)


class Post(BaseModel):
    """お手伝い案件の投稿モデル"""

    title = CharField(max_length=100)
    content = TextField()
    image_path = CharField(max_length=255, null=True)
    author = ForeignKeyField(User, backref="posts")
    created_at = DateTimeField(default=datetime.now)
