#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import sys

import requests

RESULT_JSON_PATH = "result.json"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


def load_result(path: str = RESULT_JSON_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def broadcast_line_message(access_token: str, message_text: str) -> requests.Response:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }
    payload = {
        "messages": [
            {"type": "text", "text": message_text[:5000]}
        ]
    }
    response = requests.post(LINE_BROADCAST_URL, headers=headers, json=payload, timeout=15)
    return response


def main() -> int:
    result = load_result()
    status = result.get("status")
    print(f"[INFO] result.json の status: {status}")

    if status != "ok":
        print("[INFO] 判定結果が 'ok' ではないため、LINEへの配信は行いません。")
        return 0

    applicable = result.get("applicable")
    message = result.get("message", "")

    if not applicable:
        print("[INFO] 雨割り非適用のため、LINEへの配信はスキップします。")
        return 0

    access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not access_token:
        print("[ERROR] 環境変数 LINE_CHANNEL_ACCESS_TOKEN が設定されていません。", file=sys.stderr)
        return 1

    print("[INFO] 雨割り適用のため、LINEへ配信します。")
    resp = broadcast_line_message(access_token, message)

    print(f"[INFO] LINE API レスポンス status_code: {resp.status_code}")
    print(f"[INFO] LINE API レスポンス本文: {resp.text}")

    if resp.status_code != 200:
        print("[ERROR] LINEへの配信に失敗しました。", file=sys.stderr)
        return 1

    print("[INFO] LINEへの配信が完了しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
