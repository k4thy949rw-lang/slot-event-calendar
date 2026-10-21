
import json
import re
import hashlib
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
    "User-Agent": "SlotEventCalendar/1.0 (personal event calendar)"
}

DATE_RE = re.compile(
    r"(?:(20\d{2})[/-])?(\d{1,2})[/-](\d{1,2})"
)

EVENT_WORDS = (
    "来店", "取材", "周年", "リニューアル"
)

def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()

def event_type(text):
    if "周年" in text:
        return "周年"
    if "リニューアル" in text:
        return "リニューアル"
    if "取材" in text:
        return "取材"
    if "来店" in text:
        return "来店"
    return "その他"

def extract_date(text, year):
    match = DATE_RE.search(text)
    if not match:
        return None

    y = int(match.group(1) or year)
    m = int(match.group(2))
    d = int(match.group(3))

    try:
        return datetime(y, m, d).strftime("%Y-%m-%d")
    except ValueError:
        return None

def load_previous():
    if not OUTPUT.exists():
        return {"events": []}

    try:
        data = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass

    return {"events": []}

def scrape_prefecture(pref, url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=25
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for element in soup([
        "script", "style", "nav", "footer"
    ]):
        element.decompose()

    current_year = datetime.now(JST).year
    records = []
    current_date = None

    # 見出しから日付を取得する
    # 店舗名・イベント名は同じ掲載ブロックから抽出
    for element in soup.find_all(
        ["h2", "h3", "h4", "article"]
    ):
        text = clean(element.get_text(" ", strip=True))

        if not text:
            continue

        date = extract_date(text, current_year)

        if date and len(text) < 150:
            current_date = date

        # 日付を含むイベントブロックのみ対象
        if element.name != "article":
            continue

        if not any(word in text for word in EVENT_WORDS):
            continue

        date = date or current_date
        if not date:
            continue

        heading = element.find(["h2", "h3", "h4"])
        if not heading:
            continue

        shop = clean(heading.get_text(" ", strip=True))

        if not shop or len(shop) > 80:
            continue

        link = element.find("a", href=True)
        source = (
            urljoin(url, link["href"])
            if link else url
        )

        if not source.startswith("https://"):
            source = url

        detail = text[:250]

        records.append({
            "date": date,
            "pref": pref,
            "shop": shop,
            "city": "",
            "type": event_type(detail),
            "detail": detail,
            "source": source,
            "confidence": "第三者掲載"
        })

    return records

def main():
    now = datetime.now(JST)
    previous = load_previous()
    collected = []
    errors = []
    successful = []

    for pref, url in SOURCES.items():
        try:
            records = scrape_prefecture(pref, url)
            if not records:
                raise ValueError(
                    "イベントの構造を認識できませんでした"
                )

            collected.extend(records)
            successful.append(pref)

            print(
                f"{pref}: {len(records)}件取得"
            )

        except Exception as error:
            message = f"{pref}: {error}"
            errors.append(message)
            print("取得失敗:", message)

    # 取得に失敗した地域の既存データは保持
    for event in previous.get("events", []):
        if event.get("pref") not in successful:
            collected.append(event)

    unique = {}

    for event in collected:
        key = hashlib.sha256(
            json.dumps(
                [
                    event.get("date"),
                    event.get("pref"),
                    event.get("shop"),
                    event.get("detail")
                ],
                ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()

        unique[key] = event

    events = sorted(
        unique.values(),
        key=lambda e: (
            e.get("date", ""),
            e.get("pref", ""),
            e.get("shop", "")
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

    print(f"保存完了: {len(events)}件")

    if errors:
        print("一部の取得元でエラーが発生しました")

if __name__ == "__main__":
    main()
