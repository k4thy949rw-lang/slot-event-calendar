
import re
import requests
from bs4 import BeautifulSoup

SITES = {
    "奈良県": "https://slo-map.com/area/nara",
    "大阪府": "https://slo-map.com/area/osaka",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SlotCalendarCheck/1.0)"
}

DATE = re.compile(
    r"(?:20\d{2}[/.-])?\d{1,2}[/月]\d{1,2}日?"
)

WORDS = (
    "来店", "取材", "イベント", "調査",
    "実践", "収録"
)

for pref, url in SITES.items():
    print(f"\n===== スロマップ {pref} =====", flush=True)

    try:
        response = requests.get(
            url, headers=HEADERS, timeout=30
        )
        print("HTTP:", response.status_code)
        print("最終URL:", response.url)

        response.raise_for_status()

        soup = BeautifulSoup(
            response.content, "html.parser"
        )

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        print("\n【イベント候補と周辺情報】")

        count = 0
        seen = set()

        for a in soup.find_all("a", href=True):
            href = requests.compat.urljoin(
                response.url, a["href"]
            )

            if "/halls/" not in href:
                continue

            label = " ".join(
                a.get_text(" ", strip=True).split()
            )

            if not any(word in label for word in WORDS):
                continue

            if href + label in seen:
                continue

            seen.add(href + label)

            parent = a.parent
            context = ""

            if parent:
                context = " ".join(
                    parent.get_text(" ", strip=True).split()
                )

            print(f"\n候補 {count + 1}")
            print("リンク表示:", label[:220])
            print("周辺テキスト:", context[:450])
            print("URL:", href)
            print("日付候補:", DATE.findall(context))

            count += 1

            if count >= 20:
                break

        print("\n候補件数:", count)

        print("\n【カレンダー関連リンク】")
        for a in soup.find_all("a", href=True):
            href = requests.compat.urljoin(
                response.url, a["href"]
            )
            if "/schedule/" in href or "/events" in href:
                print(href)

    except Exception as e:
        print("取得エラー:", str(e))

print("\n=== 調査終了 ===")
