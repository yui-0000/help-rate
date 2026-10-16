import os
from peewee import *
from flask_login import UserMixin
import datetime

# データベースの場所をアプリのフォルダ内に絶対パスで固定します
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db = SqliteDatabase(os.path.join(BASE_DIR, "helprate.db"))


class User(UserMixin, Model):
    username = CharField(unique=True)  # ニックネーム（表示用・重複不可）
    last_name = CharField()  # 姓（苗字・非公開）
    first_name = CharField()  # 名（名前・非公開）
    last_name_kana = CharField()  # 姓のふりがな（非公開）
    first_name_kana = CharField()  # 名のふりがな（非公開）
    email = CharField(null=True)  # 任意
    password = CharField()
    phone = CharField()  # 電話番号
    gender = CharField(null=True)
    age = IntegerField(null=True)
    is_admin = BooleanField(default=False)

    class Meta:
        database = db


class Post(Model):
    title = CharField()
    content = TextField()
    desired_date = CharField(null=True)
    location = CharField(null=True)
    detail_address = CharField(null=True)
    contact_method = CharField(default="電話")
    reward = CharField(null=True)
    recommendation = CharField(null=True)

    image_path = CharField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)

    author = ForeignKeyField(User, backref="posts")
    helper = ForeignKeyField(User, backref="helped_posts", null=True)
    helper_message = TextField(null=True)

    class Meta:
        database = db


class Message(Model):
    post = ForeignKeyField(Post, backref="messages")
    sender = ForeignKeyField(User, backref="sent_messages")
    content = TextField()
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = db


def initialize():
    db.connect()
    db.create_tables([User, Post, Message], safe=True)
    db.close()


if __name__ == "__main__":
    db.connect()
    db.create_tables([User, Post, Message], safe=True)
