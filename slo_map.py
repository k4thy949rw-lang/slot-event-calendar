
import re
from datetime import datetime, timedelta
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


def clean(value):
    return " ".join(str(value or "").split())


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

    # 今日・明日の日付見出しを取得
    for heading in soup.find_all("h3"):
        heading_text = clean(
            heading.get_text(" ", strip=True)
        )

        match = DATE_PATTERN.search(heading_text)

        if not match:
            continue

        day_label, month, day = match.groups()

        target_date = today + timedelta(
            days=0 if day_label == "今日" else 1
        )

        # 日付が一致しない情報は登録しない
        if (
            target_date.month != int(month)
            or target_date.day != int(day)
        ):
            continue

        # 見出しを含む日付枠全体
        card = heading.parent

        if card is None:
            continue

        # 日付枠内の取材・来店セクションを探す
        for subheading in card.find_all("h4"):
            title = clean(
                subheading.get_text(" ", strip=True)
            )

            if "取材・来店" not in title:
                continue

            section = subheading.parent

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

                # リンクのテキストを分割
                pieces = [
                    clean(text)
                    for text in anchor.stripped_strings
                    if clean(text) != "→"
                ]

                if len(pieces) < 2:
                    continue

                shop = pieces[0]
                detail = clean(
                    " ".join(pieces[1:])
                )

                # 異常な文字列は除外
                if not shop or not detail:
                    continue

                if len(shop) > 100:
                    continue

                if len(detail) > 250:
                    continue

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
        f"スロマップ/{pref}: {len(events)}件抽出",
        flush=True
    )

    return events
