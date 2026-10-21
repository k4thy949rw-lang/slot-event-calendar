
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

JST = ZoneInfo("Asia/Tokyo")
OUTPUT = Path("events.json")
NOW = datetime.now(JST)

PWORLD = {
    "奈良県": "https://www.p-world.co.jp/hall/interviews/prefs/nara",
    "大阪府": "https://www.p-world.co.jp/hall/interviews/prefs/osaka",
}

SLOPACHI = {
    "奈良県": "https://777.slopachi-station.com/report_schedule_pref/nara/",
    "大阪府": "https://777.slopachi-station.com/report_schedule_pref/osaka/",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SlotCalendar/1.1)"
}

DATE_FULL = re.compile(
    r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})"
)

DATE_SHORT = re.compile(
    r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)"
)

LOCATION = re.compile(
    r"【(奈良県|大阪府)([^】]*)】|"
    r"〖(奈良県|大阪府)([^〗]*)〗"
)


def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def get_html(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()
    return BeautifulSoup(
        response.content,
        "html.parser"
    )


def resolve_date(month, day):
    candidates = []

    for year in (NOW.year - 1, NOW.year, NOW.year + 1):
        try:
            date = datetime(year, month, day, tzinfo=JST)
        except ValueError:
            continue

        distance = abs((date - NOW).days)
        candidates.append((distance, date))

    if not candidates:
        return None

    return min(candidates, key=lambda x: x[0])[1].strftime(
        "%Y-%m-%d"
    )


def get_type(detail):
    if "周年" in detail:
        return "周年"
    if "景品" in detail:
        return "景品入荷"
    if "取材" in detail:
        return "取材"
    if "来店" in detail:
        return "来店"
    return "その他"


def make_event(date, pref, shop, detail, source, city=""):
    if not date or not shop or not detail:
        return None

    if not source.startswith("https://"):
        return None

    return {
        "date": date,
        "pref": pref,
        "shop": clean(shop),
        "city": clean(city),
        "type": get_type(detail),
        "detail": clean(detail)[:250],
        "source": source,
        "confidence": "公開掲載情報"
    }


def scrape_pworld(pref, url):
    soup = get_html(url)
    events = []
    current_date = None

    for heading in soup.find_all(["h2", "h3"]):
        title = clean(heading.get_text(" ", strip=True))

        if heading.name == "h2":
            match = DATE_FULL.search(title)

            if match and "取材・来店情報" in title:
                y, m, d = map(int, match.groups())

                try:
                    current_date = datetime(
                        y, m, d
                    ).strftime("%Y-%m-%d")
                except ValueError:
                    current_date = None

            continue

        if not current_date or not title:
            continue

        lines = []
        source = url
        city = ""

        for element in heading.next_elements:
            if isinstance(element, Tag):
                if element.name in ("h2", "h3"):
                    break

                if element.name == "a":
                    href = element.get("href", "")
                    if href:
                        link = urljoin(url, href)
                        if link.startswith("https://"):
                            source = link

            elif isinstance(element, str):
                value = clean(element)
                if value:
                    lines.append(value)

        for line in lines:
            if line.startswith(pref):
                city = line
                break

        details = []

        for i, line in enumerate(lines):
            if line in ("来店", "取材"):
                detail = clean(
                    " ".join(lines[i:i + 7])
                )
                if len(detail) >= 5:
                    details.append(detail)

        if not details:
            for line in lines:
                if re.match(r"^(来店|取材)\s*.+", line):
                    details.append(line)

        for detail in details:
            event = make_event(
                current_date,
                pref,
                title,
                detail,
                source,
                city
            )
            if event:
                events.append(event)

    return events


def find_schedule_blocks(soup, pref):
    """
    日付と都道府県を含む小さな掲載ブロックを探す。
    大きな一覧コンテナは対象にしない。
    """
    blocks = []
    seen = set()

    for node in soup.find_all(string=True):
        text = clean(node)

        if not DATE_SHORT.search(text):
            continue

        element = node.parent

        for _ in range(6):
            if not isinstance(element, Tag):
                break

            body = clean(
                element.get_text(" ", strip=True)
            )

            if (
                pref in body
                and LOCATION.search(body)
                and DATE_SHORT.search(body)
                and 15 <= len(body) <= 350
            ):
                if id(element) not in seen:
                    blocks.append(element)
                    seen.add(id(element))
                break

            element = element.parent

    return blocks


def scrape_slopachi(pref, url):
    soup = get_html(url)
    events = []

    blocks = find_schedule_blocks(soup, pref)

    for block in blocks:
        text = clean(
            block.get_text(" ", strip=True)
        )

        date_match = DATE_SHORT.search(text)
        loc_match = LOCATION.search(text)

        if not date_match or not loc_match:
            continue

        location_pref = (
            loc_match.group(1)
            or loc_match.group(3)
        )

        if location_pref != pref:
            continue

        month, day = map(
            int, date_match.groups()
        )

        date = resolve_date(month, day)

        city = (
            loc_match.group(2)
            or loc_match.group(4)
            or ""
        )

        # 所在地表記以降が取材名・店舗名
        remaining = clean(
            text[loc_match.end():]
        )

        if not remaining:
            continue

        # 店舗リンクがあれば、リンク文字列を優先
        anchors = [
            clean(a.get_text(" ", strip=True))
            for a in block.find_all("a", href=True)
        ]
        anchors = [
            a for a in anchors
            if a and len(a) <= 80
        ]

        shop = anchors[-1] if anchors else ""

        # リンクで店舗名が判別できない場合、
        # 不確かなデータは登録しない
        if not shop:
            continue

        if shop == remaining:
            continue

        if shop in remaining:
            detail = clean(
                remaining.split(shop)[0]
            )
        else:
            continue

        if not detail or len(detail) > 120:
            continue

        event = make_event(
            date,
            pref,
            shop,
            detail,
            url,
            pref + city
        )

        if event:
            events.append(event)

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


def event_key(event):
    return (
        event.get("date", ""),
        event.get("pref", ""),
        re.sub(
            r"\s+",
            "",
            event.get("shop", "")
        ).lower(),
        re.sub(
            r"\s+",
            "",
            event.get("detail", "")
        ).lower()
    )


def main():
    previous = load_previous()
    events = []
    successful = []
    errors = []

    sources = [
        ("P-WORLD", PWORLD, scrape_pworld),
        ("スロパチステーション", SLOPACHI, scrape_slopachi),
    ]

    for name, urls, scraper in sources:
        for pref, url in urls.items():
            source_name = f"{name}/{pref}"

            try:
                found = scraper(pref, url)

                if not found:
                    raise ValueError(
                        "掲載情報を抽出できませんでした"
                    )

                events.extend(found)
                successful.append(source_name)

                print(
                    f"{source_name}: {len(found)}件"
                )

            except Exception as exc:
                errors.append(
                    f"{source_name}: {exc}"
                )
                print(
                    f"{source_name}: 取得失敗: {exc}"
                )

    # 既存データは保持し、新規データと統合
    # 過去90日から未来180日の範囲だけ保存
    min_date = (
        NOW - timedelta(days=90)
    ).strftime("%Y-%m-%d")

    max_date = (
        NOW + timedelta(days=180)
    ).strftime("%Y-%m-%d")

    merged = {}

    for item in previous + events:
        date = item.get("date", "")

        if not (min_date <= date <= max_date):
            continue

        if item.get("pref") not in (
            "奈良県", "大阪府"
        ):
            continue

        if not item.get("shop") or not item.get("source"):
            continue

        merged[event_key(item)] = item

    result = sorted(
        merged.values(),
        key=lambda e: (
            e.get("date", ""),
            e.get("pref", ""),
            e.get("shop", "")
        )
    )

    output = {
        "updated_at": NOW.isoformat(
            timespec="seconds"
        ),
        "events": result,
        "fetch_status": {
            "successful": successful,
            "errors": errors,
            "total": len(result)
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

    print(f"保存完了: {len(result)}件")
    print(f"取得成功: {len(successful)}地域・サイト")
    print(f"取得エラー: {len(errors)}件")


if __name__ == "__main__":
    main()
