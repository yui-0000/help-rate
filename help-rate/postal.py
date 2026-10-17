"""日本郵便の公開CSVを使った、外部通信を伴わない郵便番号検索。"""
import csv
import io
import re
import unicodedata
import zipfile
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "utf_ken_all.zip"


class PostalDataError(Exception):
    pass


def normalize_postal_code(value):
    value = unicodedata.normalize("NFKC", value or "").strip()
    return value.replace("-", "")


@lru_cache(maxsize=1)
def postal_addresses():
    result = {}
    with zipfile.ZipFile(DATA_FILE) as archive:
        name = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        with archive.open(name) as raw:
            for row in csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig")):
                if len(row) < 9 or not re.fullmatch(r"[0-9]{7}", row[2]):
                    continue
                town = re.sub(r"（.*?）", "", row[8])
                if town == "以下に掲載がない場合" or "の次に番地がくる場合" in row[8] or town.endswith("一円"):
                    town = ""
                address = row[6] + row[7] + town
                choices = result.setdefault(row[2], [])
                if address not in choices:
                    choices.append(address)
    return result


def lookup_postal_code(value):
    code = normalize_postal_code(value)
    if not re.fullmatch(r"[0-9]{7}", code):
        raise ValueError("郵便番号は7桁の数字で入力してください。")
    try:
        return list(postal_addresses().get(code, ()))
    except (OSError, zipfile.BadZipFile, StopIteration, UnicodeError, csv.Error) as error:
        raise PostalDataError("住所検索データを読み込めません。") from error
