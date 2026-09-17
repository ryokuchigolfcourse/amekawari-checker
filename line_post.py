#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LINE公式アカウント自動配信スクリプト
"""

import json
import os
import sys

import requests

RESULT_JSON_PATH = "result.json"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

# GitHub Pagesで恒久的に公開されているPOP画像のURL
# （Tumblrへの投稿が成功したかどうかに関係なく、常にこのURLを使う）
POP_IMAGE_URL = "https://ryokuchigolfcourse.github.io/amekawari-checker/amekawari_pop.png"


def load_result(path: str = RESULT_JSON_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def broadcast_line_message(access_token: str, message_text: str, photo_url=None) -> requests.Response:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }
    messages = []
    if photo_url:
        messages.append({
            "type": "image",
            "originalContentUrl": photo_url,
            "previewImageUrl": photo_url,
        })
    messages.append({"type": "text", "text": message_text[:5000]})

    payload = {"messages": messages}
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
    print(f"[INFO] 画像URL（GitHub Pages固定URL）: {POP_IMAGE_URL}")

    resp = broadcast_line_message(access_token, message, photo_url=POP_IMAGE_URL)

    print(f"[INFO] LINE API レスポンス status_code: {resp.status_code}")
    print(f"[INFO] LINE API レスポンス本文: {resp.text}")

    if resp.status_code != 200:
        print("[ERROR] LINEへの配信に失敗しました。", file=sys.stderr)
        return 1

    print("[INFO] LINEへの配信が完了しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
