
import re
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


JST = ZoneInfo("Asia/Tokyo")

SITES = {
    "奈良県": "https://slo-map.com/area/nara",
    "大阪府": "https://slo-map.com/area/osaka",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

DATE_PATTERN = re.compile(
    r"(今日|明日)\s*(\d{1,2})/(\d{1,2})"
)

MEDIA_PATTERN = re.compile(
    r"\s*[（(][^（）()]{1,80}[）)]\s*$"
)


def clean(value):
    return " ".join(str(value or "").split())


def resolve_date(month, day):
    today = datetime.now(JST).date()
    candidates = []

    for year in (
        today.year - 1,
        today.year,
        today.year + 1
    ):
        try:
            candidate = date(year, month, day)
            candidates.append(candidate)
        except ValueError:
            continue

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda d: abs((d - today).days)
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


def split_event(anchor):
    # リンク内の表示文字列を取得
    label = clean(
        anchor.get_text(" ", strip=True)
    )

    label = re.sub(r"\s*→\s*$", "", label)
    label = clean(label)

    if not label:
        return None

    # 媒体名はイベント内容に残す
    media = ""
    match = MEDIA_PATTERN.search(label)

    if match:
        media = clean(match.group())
        label = clean(label[:match.start()])

    if not label:
        return None

    # 店舗名とイベント内容が別要素の場合
    pieces = [
        clean(s)
        for s in anchor.stripped_strings
        if clean(s) and clean(s) != "→"
    ]

    shop = ""
    detail = ""

    if len(pieces) >= 2:
        first = pieces[0]

        # 最初の要素が店舗名だけの場合
        if (
            first in label
            and label.startswith(first + " ")
            and not any(
                word in first
                for word in ("取材", "来店", "景品")
            )
        ):
            shop = first
            detail = clean(label[len(first):])

    # 一つの文字列にまとまっている場合
    if not shop:
        # イベント名の前の空白で分割
        tokens = label.split(" ")

        if len(tokens) >= 2:
            # 店舗名に空白があるケースも考慮
            # 「店」「ホール」「館」などを目印にする
            boundary = None

            for i, token in enumerate(tokens[:-1]):
                if (
                    token.endswith("店")
                    or token.endswith("ホール")
                    or token.endswith("館")
                    or token.endswith("センター")
                ):
                    boundary = i + 1

            if boundary is None:
                boundary = 1

            shop = clean(
                " ".join(tokens[:boundary])
            )
            detail = clean(
                " ".join(tokens[boundary:])
            )

    if media:
        detail = clean(detail + " " + media)

    if not shop or not detail:
        return None

    if shop == detail:
        return None

    if len(shop) > 100 or len(detail) > 250:
        return None

    return shop, detail


def scrape_slo_map(pref, url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(
        response.content,
        "html.parser"
    )

    today = datetime.now(JST).date()
    events = []
    seen = set()

    headings = 0
    links = 0

    for heading in soup.find_all("h3"):
        text = clean(
            heading.get_text(" ", strip=True)
        )

        match = DATE_PATTERN.search(text)

        if not match:
            continue

        _, month, day = match.groups()

        target_date = resolve_date(
            int(month),
            int(day)
        )

        if target_date is None:
            continue

        days_ahead = (target_date - today).days

        # サイトの日付切り替えが遅れた場合にも対応
        # 昨日から2日後までに限定
        if not -1 <= days_ahead <= 2:
            continue

        card = heading.parent

        if card is None:
            continue

        # 過去の実績やランキングは対象外
        sections = [
            h.parent
            for h in card.find_all("h4")
            if "取材・来店" in clean(
                h.get_text(" ", strip=True)
            )
        ]

        if not sections:
            continue

        headings += 1

        for section in sections:
            if section is None:
                continue

            for anchor in section.find_all(
                "a", href=True
            ):
                href = urljoin(
                    response.url,
                    anchor["href"]
                )

                if "/halls/" not in href:
                    continue

                links += 1

                parsed = split_event(anchor)

                if parsed is None:
                    continue

                shop, detail = parsed

                key = (
                    target_date.isoformat(),
                    pref,
                    shop,
                    detail
                )

                if key in seen:
                    continue

                seen.add(key)

                events.append({
                    "date": target_date.isoformat(),
                    "pref": pref,
                    "shop": shop,
                    "city": "",
                    "type": event_type(detail),
                    "detail": detail,
                    "source": href,
                    "confidence": "公開掲載情報"
                })

    print(
        f"スロマップ/{pref}: "
        f"日付枠={headings}, "
        f"リンク={links}, "
        f"抽出={len(events)}件",
        flush=True
    )

    return events
