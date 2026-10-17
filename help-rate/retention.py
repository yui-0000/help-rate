"""削除済みデータを90日間だけ管理者向けに保管する。日時はUTC。"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models import User, Post, Message, ArchivedPhoto

RETENTION_DAYS = 90


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def cutoff_time():
    return utcnow() - timedelta(days=RETENTION_DAYS)


def purge_expired(upload_folder):
    db = Post._meta.database
    cutoff = cutoff_time()
    root = Path(upload_folder).resolve()
    db.execute_sql("PRAGMA secure_delete=ON")
    for old_photo in ArchivedPhoto.select().where(ArchivedPhoto.deleted_at <= cutoff).iterator():
        with db.atomic():
            shared = Post.select().where(Post.image_path == old_photo.filename).exists() or ArchivedPhoto.select().where(
                ArchivedPhoto.filename == old_photo.filename, ArchivedPhoto.id != old_photo.id
            ).exists()
            if not shared:
                photo = (root / old_photo.filename).resolve()
                if photo.is_relative_to(root):
                    try:
                        photo.unlink(missing_ok=True)
                    except OSError:
                        continue
            old_photo.delete_instance()
    # 確認用一覧からは期限で除外する。ファイル削除失敗時は記録を残して再試行する。
    for post in Post.select().where(Post.deleted_at <= cutoff).iterator():
        with db.atomic():
            if ArchivedPhoto.select().where(ArchivedPhoto.post == post).exists():
                continue
            if post.image_path:
                shared = Post.select().where(
                    Post.image_path == post.image_path, Post.id != post.id
                ).exists() or ArchivedPhoto.select().where(ArchivedPhoto.filename == post.image_path).exists()
                if not shared:
                    photo = (root / post.image_path).resolve()
                    if photo.is_relative_to(root):
                        try:
                            photo.unlink(missing_ok=True)
                        except OSError:
                            continue
            Message.delete().where(Message.post == post).execute()
            post.delete_instance()
    Message.delete().where(Message.deleted_at <= cutoff).execute()
    # 管理者・運営者が設定したアカウントは期限に関係なく消去対象から外す。
    for user in User.select().where(
        User.deleted_at <= cutoff, User.is_admin == False, User.admin_managed == False
    ).iterator():
        with db.atomic():
            if Post.select().where(Post.author == user).exists():
                continue  # 写真の削除を再試行中なら、参照整合性を保つ。
            Message.delete().where(Message.sender == user).execute()
            Post.update(helper=None, helper_message=None, contact_shared=False).where(Post.helper == user).execute()
            Post.update(deleted_by=None).where(Post.deleted_by == user).execute()
            Message.update(deleted_by=None).where(Message.deleted_by == user).execute()
            User.update(deleted_by=None).where(User.deleted_by == user).execute()
            user.delete_instance()
