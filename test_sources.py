
import requests
from bs4 import BeautifulSoup

SITES = {
    "ホルログ（奈良）": "https://horulog.com/nara/events",
    "スロマップ（奈良）": "https://slo-map.com/area/nara",
}

headers = {
    "User-Agent": "Mozilla/5.0 (compatible; EventCalendarCheck/1.0)"
}

print("=== イベント情報サイト接続テスト ===", flush=True)

for name, url in SITES.items():
    print(f"\n【{name}】", flush=True)

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=20,
        )

        print("HTTPステータス:", response.status_code)
        print("最終URL:", response.url)
        print("HTMLサイズ:", len(response.content))

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")

            title = soup.title.get_text(
                " ", strip=True
            ) if soup.title else "なし"

            text = soup.get_text(" ", strip=True)

            print("ページタイトル:", title)
            print("本文文字数:", len(text))
            print("イベント関連語:", {
                word: word in text
                for word in [
                    "奈良", "大阪", "来店", "取材", "イベント"
                ]
            })
            print("結果: 接続成功（内容の検証は別途必要）")
        else:
            print("結果: アクセス失敗")

    except requests.RequestException as e:
        print("結果: 通信エラー")
        print("エラー:", str(e))

print("\n=== テスト終了 ===")
