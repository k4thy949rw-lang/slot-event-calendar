
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

DATE_PATTERN = re.compile(
    r"(今日|明日)\s*(\d{1,2})/(\d{1,2})"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def clean(text):
    return " ".join(str(text or "").split())


def event_type(detail):
    if "来店" in detail:
        return "来店"
    if "取材" in detail:
        return "取材"
    if "景品" in detail:
        return "景品入荷"
    return "その他"


def scrape_slo_map(pref, url):
    response = requests.get(
        url, headers=HEADERS, timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(
        response.content, "html.parser"
    )

    today = datetime.now(JST).date()
    events = []
    seen = set()

    # 日付ごとに分かれた「今日・明日」の枠だけを対象にする
    for heading in soup.find_all("h3"):
        label = clean(heading.get_text(" ", strip=True))
        match = DATE_PATTERN.search(label)

        if not match:
            continue

        day_label, month, day = match.groups()

        expected = today + timedelta(
            days=0 if day_label == "今日" else 1
        )

        # 表示日と実際の日付が一致しなければ登録しない
        if (
            expected.month != int(month)
            or expected.day != int(day)
        ):
            continue

        card = heading.parent

        if card is None:
            continue

        # 取材・来店欄のみを抽出
        for section in card.find_all("div", recursive=False):
            subheading = section.find("h4")

            if not subheading:
                continue

            if "取材・来店" not in clean(
                subheading.get_text(" ", strip=True)
            ):
                continue

            for anchor in section.find_all(
                "a", href=True
            ):
                href = urljoin(
                    response.url, anchor["href"]
                )

                if "/halls/" not in href:
                    continue

                # 店舗名とイベント名を分けるため、
                # リンク内のテキスト要素を利用
                pieces = [
                    clean(s)
                    for s in anchor.stripped_strings
                    if clean(s) and clean(s) != "→"
                ]

                if len(pieces) < 2:
                    continue

                shop = pieces[0]
                detail = clean(" ".join(pieces[1:]))

                # 店舗名が長すぎる等、構造が変わった場合は除外
                if (
                    len(shop) > 100
                    or len(detail) > 200
                    or not detail
                ):
                    continue

                date = expected.isoformat()

                key = (
                    date, pref, shop, detail
                )

                if key in seen:
                    continue

                seen.add(key)

                events.append({
                    "date": date,
                    "pref": pref,
                    "shop": shop,
                    "city": "",
                    "type": event_type(detail),
                    "detail": detail,
                    "source": href,
                    "confidence": "公開掲載情報"
                })

    return events
