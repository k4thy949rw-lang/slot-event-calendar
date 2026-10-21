
import requests
from bs4 import BeautifulSoup
import re

SITES = {
    "ホルログ（奈良）": "https://horulog.com/nara/events",
    "スロマップ（奈良）": "https://slo-map.com/area/nara",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EventCalendarCheck/1.0)"
}

DATE_PATTERN = re.compile(
    r"20\d{2}[/年.-]\d{1,2}[/月.-]\d{1,2}日?"
    r"|\d{1,2}[/月]\d{1,2}日?"
)

for name, url in SITES.items():
    print(f"\n========== {name} ==========", flush=True)

    try:
        response = requests.get(
            url, headers=HEADERS, timeout=25
        )
        print("HTTP:", response.status_code)

        if response.status_code != 200:
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        print("\n【日付を含む表示テキスト：最大15件】")
        found = 0

        for line in soup.stripped_strings:
            line = " ".join(line.split())

            if DATE_PATTERN.search(line):
                print(repr(line[:180]))
                found += 1

                if found >= 15:
                    break

        print("日付候補数:", found)

        print("\n【イベント関連リンク：最大15件】")
        found = 0
        seen = set()

        for a in soup.find_all("a", href=True):
            label = a.get_text(" ", strip=True)
            href = requests.compat.urljoin(
                response.url, a["href"]
            )

            if href in seen:
                continue

            if any(word in label + href for word in [
                "来店", "取材", "イベント",
                "event", "report", "shop"
            ]):
                seen.add(href)
                print("表示:", label[:100])
                print("URL:", href[:200])
                found += 1

                if found >= 15:
                    break

        print("リンク候補数:", found)

    except Exception as e:
        print("エラー:", str(e))

print("\n=== 抽出テスト終了 ===")
