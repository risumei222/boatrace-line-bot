import os
import json
import urllib.request
import urllib.error

LINE_NOTIFY_TOKEN = os.getenv("LINE_NOTIFY_TOKEN")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")


def send_line(text: str):
    # LINE Notify
    if LINE_NOTIFY_TOKEN:
        try:
            req = urllib.request.Request(
                "https://notify-api.line.me/api/notify",
                data=urllib.parse.urlencode({"message": f"\n{text}"}).encode("utf-8"),
                headers={"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"}
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

    # LINE Messaging API
    if LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID:
        try:
            payload = json.dumps({
                "to": LINE_USER_ID,
                "messages": [{"type": "text", "text": text[:4000]}]
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.line.me/v2/bot/message/push",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
                }
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass


def main():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    lines = ["📡【公式データファイル 通信テスト結果】"]

    # ① データ配信サーバー（mbrace）
    url1 = "http://www1.mbrace.or.jp/od2/K/202611/k261109.lzh"
    try:
        req1 = urllib.request.Request(url1, headers=headers)
        with urllib.request.urlopen(req1, timeout=10) as res1:
            data = res1.read()
            lines.append("\n① データ配信サーバー (mbrace):")
            lines.append(f"・HTTPステータス: {res1.status}")
            lines.append(f"・取得サイズ: {len(data)} バイト")
            lines.append("➔ 【成功】ブロックされずに取得可能！")
    except urllib.error.HTTPError as e:
        lines.append("\n① データ配信サーバー (mbrace):")
        lines.append(f"・HTTPエラー: {e.code}")
    except Exception as e:
        lines.append(f"\n① 接続エラー: {e}")

    # ② 公式サイト ダウンロードページ
    url2 = "https://www.boatrace.jp/owpc/pc/extra/data/download.html"
    try:
        req2 = urllib.request.Request(url2, headers=headers)
        with urllib.request.urlopen(req2, timeout=10) as res2:
            lines.append("\n② 公式ダウンロード窓口:")
            lines.append(f"・HTTPステータス: {res2.status}")
    except urllib.error.HTTPError as e:
        lines.append(f"\n② 公式ダウンロード窓口 HTTPエラー: {e.code}")
    except Exception as e:
        lines.append(f"\n② 接続エラー: {e}")

    report = "\n".join(lines)
    print(report)
    send_line(report)


if __name__ == "__main__":
    main()
