
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup, Tag

JST = ZoneInfo("Asia/Tokyo")
NOW = datetime.now(JST)
OUTPUT = Path("events.json")

PWORLD = {
    "奈良県": "https://www.p-world.co.jp/hall/interviews/prefs/nara",
    "大阪府": "https://www.p-world.co.jp/hall/interviews/prefs/osaka",
}

HORULOG = {
    "奈良県": "https://horulog.com/nara/events",
    "大阪府": "https://horulog.com/osaka/events",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SlotCalendar/1.2)"
}

FULL_DATE = re.compile(
    r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})"
)

SHORT_DATE = re.compile(
    r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)"
)

HORULOG_ENTRY = re.compile(
    r"^(.+?)\s+(\d{1,2})/(\d{1,2})\s+(取材|来店)(?:\s|$)"
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def get_html(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()
    return BeautifulSoup(response.content, "html.parser")


def resolve_date(month, day):
    candidates = []

    for year in (NOW.year - 1, NOW.year, NOW.year + 1):
        try:
            date = datetime(year, month, day, tzinfo=JST)
        except ValueError:
            continue

        distance = abs((date.date() - NOW.date()).days)
        candidates.append((distance, date))

    if not candidates:
        return None

    return min(candidates, key=lambda x: x[0])[1].strftime(
        "%Y-%m-%d"
    )


def event_type(detail):
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
    if not all([date, pref, shop, detail, source]):
        return None

    if not source.startswith("https://"):
        return None

    return {
        "date": date,
        "pref": pref,
        "shop": clean(shop),
        "city": clean(city),
        "type": event_type(detail),
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
            match = FULL_DATE.search(title)

            if match and "取材・来店情報" in title:
                try:
                    y, m, d = map(int, match.groups())
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
                detail = clean(" ".join(lines[i:i + 7]))
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


def scrape_horulog(pref, url):
    soup = get_html(url)
    events = []
    seen = set()

    for anchor in soup.find_all("a", href=True):
        href = urljoin(url, anchor["href"])

        if not href.startswith("https://horulog.com/hall/"):
            continue

        # 他府県の店舗は登録しない
        decoded = unquote(href)
        if f"/hall/{pref}/" not in decoded:
            continue

        label = clean(anchor.get_text(" ", strip=True))
        match = HORULOG_ENTRY.search(label)

        if not match:
            continue

        shop = clean(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        category = match.group(4)

        date = resolve_date(month, day)
        if not date:
            continue

        # リンク表示に明記された分類のみ使用。
        # 詳しい取材名・演者名は推測しない。
        detail = category

        key = (date, pref, shop, category, href)
        if key in seen:
            continue
        seen.add(key)

        event = make_event(
            date,
            pref,
            shop,
            detail,
            href
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
            r"\s+", "",
            event.get("shop", "")
        ).lower(),
        re.sub(
            r"\s+", "",
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
        ("ホルログ", HORULOG, scrape_horulog),
    ]

    for name, urls, scraper in sources:
        for pref, url in urls.items():
            source_name = f"{name}/{pref}"

            try:
                found = scraper(pref, url)

                if not found:
                    raise ValueError(
                        "イベントを抽出できませんでした"
                    )

                events.extend(found)
                successful.append(source_name)

                print(
                    f"{source_name}: {len(found)}件",
                    flush=True
                )

            except Exception as exc:
                errors.append(
                    f"{source_name}: {exc}"
                )
                print(
                    f"{source_name}: 取得失敗: {exc}",
                    flush=True
                )

    min_date = (
        NOW - timedelta(days=90)
    ).strftime("%Y-%m-%d")

    max_date = (
        NOW + timedelta(days=180)
    ).strftime("%Y-%m-%d")

    merged = {}

    # 既存のデータを維持
    for item in previous:
        date = item.get("date", "")
        if not (min_date <= date <= max_date):
            continue
        if item.get("pref") not in ("奈良県", "大阪府"):
            continue
        if not item.get("shop") or not item.get("source"):
            continue

        merged[event_key(item)] = item

    # 今回取得したデータを反映
    for item in events:
        date = item.get("date", "")
        if not (min_date <= date <= max_date):
            continue

        key = event_key(item)

        # 同じ日付・店舗・内容なら既存を優先
        if key not in merged:
            merged[key] = item

    result = sorted(
        merged.values(),
        key=lambda e: (
            e.get("date", ""),
            e.get("pref", ""),
            e.get("shop", "")
        )
    )

    output = {
        "updated_at": NOW.isoformat(timespec="seconds"),
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

    print(f"保存完了: {len(result)}件", flush=True)
    print(f"取得成功: {len(successful)}地域・サイト")
    print(f"取得エラー: {len(errors)}件")


if __name__ == "__main__":
    main()
