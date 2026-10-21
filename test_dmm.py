
import requests
from bs4 import BeautifulSoup

URLS = {
    "DMM全国取材レポート":
        "https://p-town.dmm.com/shop_reports",
    "DMM大阪府":
        "https://p-town.dmm.com/shop_reports?prefecture=27",
    "DMM奈良県":
        "https://p-town.dmm.com/shop_reports?prefecture=29",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ja-JP,ja;q=0.9",
}

def main():
    print("=== DMMぱちタウン接続テスト ===")

    for name, url in URLS.items():
        print(f"\n【{name}】")

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=30,
                allow_redirects=True
            )

            print("HTTPステータス:", response.status_code)
            print("最終URL:", response.url)
            print("HTMLサイズ:", len(response.content))

            if response.status_code != 200:
                print("結果: アクセス失敗")
                continue

            soup = BeautifulSoup(
                response.content,
                "html.parser"
            )

            title = soup.title.get_text(
                " ", strip=True
            ) if soup.title else "タイトルなし"

            text = soup.get_text(" ", strip=True)

            print("ページタイトル:", title)
            print("実施日の記載:", "実施日" in text)
            print("奈良県の記載:", "奈良県" in text)
            print("大阪府の記載:", "大阪府" in text)
            print("本文の長さ:", len(text))

            if "実施日" in text:
                print("結果: 取材情報を含むHTMLを取得")
            else:
                print("結果: 接続成功・掲載内容は要確認")

        except requests.RequestException as error:
            print("結果: 通信エラー")
            print(str(error))

    print("\n=== テスト終了 ===")

if __name__ == "__main__":
    main()
