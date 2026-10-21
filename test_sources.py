
import re
import requests
from bs4 import BeautifulSoup, Tag

SITES = {
    "奈良県": "https://slo-map.com/area/nara",
    "大阪府": "https://slo-map.com/area/osaka",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

DATE = re.compile(
    r"(?:20\d{2}[/.-])?\d{1,2}[/月]\d{1,2}日?"
)

def clean(value):
    return " ".join(str(value).split())

def describe(tag):
    if not isinstance(tag, Tag):
        return ""

    classes = " ".join(tag.get("class", []))
    return (
        f"<{tag.name} class='{classes[:120]}'> "
        f"{clean(tag.get_text(' ', strip=True))[:280]}"
    )

for pref, url in SITES.items():
    print(f"\n========== {pref} ==========", flush=True)

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )
        print("HTTP:", response.status_code)
        response.raise_for_status()

        soup = BeautifulSoup(
            response.content,
            "html.parser"
        )

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        print("\n【イベントリンクの親要素】")

        count = 0

        for a in soup.find_all("a", href=True):
            href = requests.compat.urljoin(
                response.url, a["href"]
            )

            if "/halls/" not in href:
                continue

            label = clean(a.get_text(" ", strip=True))

            if not any(x in label for x in (
                "来店", "取材", "景品", "調査"
            )):
                continue

            if "過去のイベント実績" in label:
                continue

            count += 1
            print(f"\n--- イベント {count} ---")
            print("名称:", label[:180])
            print("URL:", href)

            current = a

            for depth in range(1, 5):
                current = current.parent

                if not isinstance(current, Tag):
                    break

                print(
                    f"親{depth}:",
                    describe(current)
                )

                if depth <= 2:
                    previous = current.find_previous_sibling()
                    if previous:
                        print(
                            "直前の兄弟要素:",
                            describe(previous)
                        )

            if count >= 6:
                break

        print("\n【日付・見出し周辺】")

        found = 0

        for tag in soup.find_all(
            ["h2", "h3", "h4", "time"]
        ):
            label = clean(tag.get_text(" ", strip=True))

            if (
                DATE.search(label)
                or "今日" in label
                or "明日" in label
                or "イベント予定" in label
            ):
                print("見出し:", describe(tag))
                parent = tag.parent

                if parent:
                    print("親要素:", describe(parent))

                found += 1

                if found >= 12:
                    break

        print("\n【カレンダーページ】")

        schedule_url = (
            "https://slo-map.com/schedule/"
            + ("nara" if pref == "奈良県" else "osaka")
        )

        try:
            schedule = requests.get(
                schedule_url,
                headers=HEADERS,
                timeout=30
            )
            print("URL:", schedule_url)
            print("HTTP:", schedule.status_code)

            if schedule.status_code == 200:
                page = BeautifulSoup(
                    schedule.content, "html.parser"
                )

                for tag in page(
                    ["script", "style", "noscript"]
                ):
                    tag.decompose()

                lines = [
                    clean(x)
                    for x in page.stripped_strings
                ]

                print("表示テキスト先頭:")
                for line in lines[:35]:
                    print(line[:160])

        except Exception as e:
            print("カレンダー調査エラー:", e)

    except Exception as e:
        print("取得エラー:", e)

print("\n=== 調査完了 ===")
