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
    admin_managed = BooleanField(default=False)  # 運営者が専用コマンドで権限を設定したか
    deleted_at = DateTimeField(null=True)
    deleted_by = ForeignKeyField('self', null=True, backref="deleted_accounts", index=False)

    class Meta:
        database = db


class Post(Model):
    title = CharField()
    content = TextField()
    desired_date = CharField(null=True)
    location = CharField(null=True)
    detail_address = CharField(null=True)
    postal_code = CharField(null=True)
    place_notes = CharField(null=True)
    contact_phone = CharField(null=True)
    contact_email = CharField(null=True)
    contact_method = CharField(default="電話")
    reward = CharField(null=True)
    recommendation = CharField(null=True)

    image_path = CharField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)

    author = ForeignKeyField(User, backref="posts")
    helper = ForeignKeyField(User, backref="helped_posts", null=True)
    helper_message = TextField(null=True)
    contact_shared = BooleanField(default=False)
    is_completed = BooleanField(default=False)
    deleted_at = DateTimeField(null=True)
    deleted_by = ForeignKeyField(User, null=True, backref="deleted_posts", index=False)

    class Meta:
        database = db


class Message(Model):
    post = ForeignKeyField(Post, backref="messages")
    sender = ForeignKeyField(User, backref="sent_messages")
    content = TextField()
    created_at = DateTimeField(default=datetime.datetime.now)
    deleted_at = DateTimeField(null=True)
    deleted_by = ForeignKeyField(User, null=True, backref="deleted_messages", index=False)

    class Meta:
        database = db


class ArchivedPhoto(Model):
    post = ForeignKeyField(Post, backref="archived_photos")
    filename = CharField()
    deleted_at = DateTimeField(default=lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None), index=True)

    class Meta:
        database = db


def initialize():
    with db.connection_context():
        with db.atomic():
            db.create_tables([User, Post, Message, ArchivedPhoto], safe=True)
            user_columns = {column.name for column in db.get_columns("user")}
            if "admin_managed" not in user_columns:
                db.execute_sql(
                    'ALTER TABLE "user" ADD COLUMN "admin_managed" INTEGER NOT NULL DEFAULT 0'
                )
            # 登録順によって自動付与された旧管理者権限は引き継がない。
            User.update(is_admin=False).where(
                User.is_admin == True, User.admin_managed == False
            ).execute()
            columns = {column.name for column in db.get_columns("post")}
            for name in ("contact_phone", "contact_email", "postal_code", "place_notes"):
                if name not in columns:
                    db.execute_sql(f'ALTER TABLE "post" ADD COLUMN "{name}" VARCHAR(255)')
            for name in ("contact_shared", "is_completed"):
                if name not in columns:
                    db.execute_sql(
                        f'ALTER TABLE "post" ADD COLUMN "{name}" INTEGER NOT NULL DEFAULT 0'
                    )
            for table in ("user", "post", "message"):
                existing = {column.name for column in db.get_columns(table)}
                if "deleted_at" not in existing:
                    db.execute_sql(f'ALTER TABLE "{table}" ADD COLUMN "deleted_at" DATETIME')
                if "deleted_by_id" not in existing:
                    db.execute_sql(f'ALTER TABLE "{table}" ADD COLUMN "deleted_by_id" INTEGER REFERENCES "user"("id")')
                db.execute_sql(f'CREATE INDEX IF NOT EXISTS "{table}_deleted_at" ON "{table}" ("deleted_at")')


if __name__ == "__main__":
    initialize()
