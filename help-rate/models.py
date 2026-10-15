import os
from peewee import *
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SqliteDatabase("help_rate.db")


class User(UserMixin, Model):
    username = CharField(unique=True)
    email = CharField(unique=True)
    password_hash = CharField()
    age_group = CharField(null=True)
    gender = CharField(null=True)

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
    desired_date = CharField(null=True)
    location = CharField(null=True)
    reward = CharField(null=True)
    recommendation = CharField(null=True)
    created_at = DateTimeField(constraints=[SQL("DEFAULT CURRENT_TIMESTAMP")])
    author = ForeignKeyField(User, backref="posts")
    helper = ForeignKeyField(User, null=True, backref="helped_posts")
    # ▼▼▼ 追加：助っ人からのひと言メッセージ ▼▼▼
    helper_message = TextField(null=True)
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

    class Meta:
        database = db
