
import json
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

JST = ZoneInfo("Asia/Tokyo")
OUTPUT = Path("events.json")

SOURCES = {
    "奈良県": "https://www.p-world.co.jp/hall/interviews/prefs/nara",
    "大阪府": "https://www.p-world.co.jp/hall/interviews/prefs/osaka",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EventCalendar/1.0)"
}

DATE_PATTERN = re.compile(
    r"(20\d{2})/(\d{1,2})/(\d{1,2})"
)

ADDRESS_PATTERN = re.compile(
    r"(奈良県|大阪府)([^\s]+)"
)


def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def event_type(text):
    if text.startswith("来店"):
        return "来店"
    if text.startswith("取材"):
        return "取材"
    return "その他"


def parse_page(pref, url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # 日付見出し(h2)と店舗見出し(h3)を
    # 文書の出現順に処理する
    headings = soup.find_all(["h2", "h3"])

    events = []
    current_date = None

    for heading in headings:
        title = clean(heading.get_text(" ", strip=True))

        if heading.name == "h2":
            match = DATE_PATTERN.search(title)

            if match and "取材・来店情報" in title:
                year, month, day = map(
                    int, match.groups()
                )
                try:
                    current_date = datetime(
                        year, month, day
                    ).strftime("%Y-%m-%d")
                except ValueError:
                    current_date = None

            continue

        if heading.name != "h3" or not current_date:
            continue

        shop = title
        if not shop:
            continue

        # 店舗見出しの次から、次の店舗または
        # 日付見出しまでの情報を集める
        texts = []
        source = url
        address = ""

        for element in heading.next_elements:
            if element is heading:
                continue

            if getattr(element, "name", None) in ("h2", "h3"):
                break

            if getattr(element, "name", None) == "a":
                href = element.get("href", "")
                if "p-world.jp" in href and source == url:
                    source = urljoin(url, href)

            if isinstance(element, str):
                value = clean(element)
                if value:
                    texts.append(value)

        # 同じ文字列の重複を抑える
        lines = []
        for value in texts:
            if not lines or lines[-1] != value:
                lines.append(value)

        for value in lines:
            if value.startswith(pref):
                address = value
                break

        # 「来店」「取材」で始まる掲載内容を抽出
        details = []

        for index, value in enumerate(lines):
            if value not in ("来店", "取材"):
                continue

            following = lines[index + 1:index + 7]
            detail = clean(" ".join([value] + following))

            # イベント内容が存在する場合だけ採用
            if len(detail) < 5:
                continue

            details.append(detail)

        # タグの分かれ方が異なる場合への対応
        if not details:
            for value in lines:
                if re.match(r"^(来店|取材)\s*.+", value):
                    details.append(value)

        for detail in details:
            events.append({
                "date": current_date,
                "pref": pref,
                "shop": shop,
                "city": address,
                "type": event_type(detail),
                "detail": detail[:250],
                "source": source if source.startswith("https://") else url,
                "confidence": "掲載情報"
            })

    return events


def load_previous():
    if not OUTPUT.exists():
        return []

    try:
        data = json.loads(
            OUTPUT.read_text(encoding="utf-8")
        )
        return data.get("events", [])
    except (OSError, ValueError, TypeError):
        return []


def main():
    now = datetime.now(JST)
    old_events = load_previous()

    events = []
    successful = []
    errors = []

    for pref, url in SOURCES.items():
        try:
            found = parse_page(pref, url)

            if not found:
                raise ValueError(
                    "掲載情報を抽出できませんでした"
                )

            events.extend(found)
            successful.append(pref)
            print(f"{pref}: {len(found)}件")

        except Exception as exc:
            errors.append(f"{pref}: {exc}")
            print(f"{pref} 取得失敗: {exc}")

    # 取得失敗した地域は前回のデータを保持
    for item in old_events:
        if item.get("pref") not in successful:
            events.append(item)

    unique = {}
    for item in events:
        key = (
            item.get("date"),
            item.get("pref"),
            item.get("shop"),
            item.get("detail")
        )
        unique[key] = item

    events = sorted(
        unique.values(),
        key=lambda x: (
            x.get("date", ""),
            x.get("pref", ""),
            x.get("shop", "")
        )
    )

    output = {
        "updated_at": now.isoformat(timespec="seconds"),
        "events": events,
        "fetch_status": {
            "successful": successful,
            "errors": errors
        }
    }

    OUTPUT.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        ) + "\n",
        encoding="utf-8"
    )

    print(f"合計: {len(events)}件")


if __name__ == "__main__":
    main()
