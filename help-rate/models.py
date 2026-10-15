import os
from peewee import *
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SqliteDatabase("help_rate.db")


class User(UserMixin, Model):
    username = CharField(unique=True)
    email = CharField(unique=True)
    password_hash = CharField()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    class Meta:
        database = db


class Post(Model):
    title = CharField()
    content = TextField()
    image_path = CharField(null=True)
    # ▼▼▼ 追加した詳細項目 ▼▼▼
    desired_date = CharField(null=True)  # 実施希望日時
    location = CharField(null=True)  # 作業場所
    reward = CharField(null=True)  # 謝礼・お礼
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
    created_at = DateTimeField(constraints=[SQL("DEFAULT CURRENT_TIMESTAMP")])
    author = ForeignKeyField(User, backref="posts")

    class Meta:
        database = db
