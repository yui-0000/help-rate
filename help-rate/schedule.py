"""依頼の実施日と、確定・おおよその時間指定。既存の日時文字列も読み込む。"""
import re
from datetime import datetime

from flask_wtf import FlaskForm
from wtforms import DateField, SelectField
from wtforms.validators import DataRequired, Optional

PERIODS = ("早朝", "午前", "午後", "夕方", "夜")


def parse_schedule(value):
    if not value:
        return {}
    try:
        exact = datetime.fromisoformat(value)
        return dict(desired_day=exact.date(), time_mode="exact",
                    desired_hour=f"{exact.hour:02d}", desired_minute=f"{exact.minute:02d}")
    except ValueError:
        pass
    day, separator, label = value.partition(" ")
    try:
        day = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        return {}
    if not separator:
        return {}
    if label in PERIODS:
        return dict(desired_day=day, time_mode="period", desired_period=label)
    if label == "相談して決める":
        return dict(desired_day=day, time_mode="consult")
    match = re.fullmatch(r"(\d{1,2})時(?:(\d{1,2})分)?頃", label)
    if match and 0 <= int(match[1]) <= 23 and 0 <= int(match[2] or 0) <= 59:
        return dict(desired_day=day, time_mode="around", desired_hour=f"{int(match[1]):02d}",
                    desired_minute=f"{int(match[2] or 0):02d}")
    return {}


class ScheduleForm(FlaskForm):
    desired_day = DateField("実施日（年・月・日）", format="%Y-%m-%d", validators=[
        DataRequired(message="実施日を正しい日付で入力してください。")])
    time_mode = SelectField("時間の指定方法", default="exact", choices=[
        ("exact", "時刻を指定"), ("around", "○時頃"),
        ("period", "時間帯"), ("consult", "相談して決める")],
        validators=[DataRequired(message="時間の指定方法を選んでください。")])
    desired_hour = SelectField("時（0〜23時）", choices=[("", "時を選択")] + [
        (f"{hour:02d}", f"{hour}時") for hour in range(24)], validators=[Optional()])
    desired_minute = SelectField("分", default="00", choices=[("", "分を選択")] + [
        (f"{minute:02d}", f"{minute:02d}分") for minute in range(60)], validators=[Optional()])
    desired_period = SelectField("時間帯", choices=[("", "時間帯を選択")] + [
        (period, period) for period in PERIODS], validators=[Optional()])

    def __init__(self, *args, **kwargs):
        obj = kwargs.get("obj")
        super().__init__(*args, **kwargs)
        self.legacy_schedule = None
        if obj is not None and not self.is_submitted():
            stored = getattr(obj, "desired_date", None)
            parsed = parse_schedule(stored)
            for name, value in parsed.items():
                getattr(self, name).data = value
            if stored and not parsed:
                self.legacy_schedule = stored

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators=extra_validators)
        required = []
        if self.time_mode.data in ("exact", "around"):
            required = [(self.desired_hour, "時を選んでください。"),
                        (self.desired_minute, "分を選んでください。")]
        elif self.time_mode.data == "period":
            required = [(self.desired_period, "時間帯を選んでください。")]
        for field, message in required:
            if not field.data:
                field.errors = list(field.errors) + [message]
                valid = False
        return valid

    def schedule_text(self):
        day = self.desired_day.data.strftime("%Y-%m-%d")
        if self.time_mode.data == "consult":
            return f"{day} 相談して決める"
        if self.time_mode.data == "period":
            return f"{day} {self.desired_period.data}"
        if self.time_mode.data == "around":
            minute = int(self.desired_minute.data)
            label = f"{int(self.desired_hour.data)}時" + (f"{minute}分" if minute else "") + "頃"
            return f"{day} {label}"
        return f"{day} {self.desired_hour.data}:{self.desired_minute.data}"
