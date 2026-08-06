#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import sys
from typing import Optional

import pytumblr

BLOG_IDENTIFIER = "minamitsukubag.tumblr.com"
RESULT_JSON_PATH = "result.json"
POP_IMAGE_PATH = "amekawari_pop.png"


def load_result(path: str = RESULT_JSON_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_client() -> pytumblr.TumblrRestClient:
    consumer_key = os.environ["TUMBLR_CONSUMER_KEY"]
    consumer_secret = os.environ["TUMBLR_CONSUMER_SECRET"]
    oauth_token = os.environ["TUMBLR_OAUTH_TOKEN"]
    oauth_token_secret = os.environ["TUMBLR_OAUTH_TOKEN_SECRET"]
    return pytumblr.TumblrRestClient(
        consumer_key, consumer_secret, oauth_token, oauth_token_secret
    )


def post_to_tumblr(client, message: str, target_date: str) -> dict:
    caption = message.replace("\n", "<br>")

    if os.path.exists(POP_IMAGE_PATH):
        response = client.create_photo(
            BLOG_IDENTIFIER,
            state="published",
            caption=caption,
            data=POP_IMAGE_PATH,
        )
    else:
        print(f"[WARN] POP画像 '{POP_IMAGE_PATH}' が見つかりません。テキストのみで投稿します。", file=sys.stderr)
        response = client.create_text(
            BLOG_IDENTIFIER,
            state="published",
            title=f"【雨割り適用のお知らせ】{target_date}",
            body=caption,
        )
    return response


def extract_photo_url(client, create_response: dict):
    post_id = create_response.get("id") or create_response.get("response", {}).get("id")
    if not post_id:
        return None
    try:
        detail = client.posts(BLOG_IDENTIFIER, id=post_id)
    except Exception as e:
        print(f"[WARN] 投稿詳細の取得に失敗しました（画像URLなしで続行）: {e}", file=sys.stderr)
        return None

    posts = detail.get("posts", [])
    if not posts:
        return None
    photos = posts[0].get("photos", [])
    if not photos:
        return None
    return photos[0].get("original_size", {}).get("url")


def main() -> int:
    result = load_result()
    status = result.get("status")
    print(f"[INFO] result.json の status: {status}")

    if status != "ok":
        print("[INFO] 判定結果が 'ok' ではないため、Tumblrへの投稿は行いません。")
        return 0

    applicable = result.get("applicable")
    target_date = result.get("target_date", "")
    message = result.get("message", "")

    if not applicable:
        print("[INFO] 雨割り非適用のため、Tumblrへの投稿はスキップします。")
        return 0

    print("[INFO] 雨割り適用のため、Tumblrへ投稿します。")
    client = build_client()
    try:
        response = post_to_tumblr(client, message, target_date)
    except Exception as e:
        print(f"[ERROR] Tumblrへの投稿に失敗しました: {e}", file=sys.stderr)
        return 1

    print("[INFO] Tumblrへの投稿結果:")
    print(json.dumps(response, ensure_ascii=False, indent=2))

    if isinstance(response, dict) and response.get("meta", {}).get("status") not in (200, 201, None):
        print("[ERROR] Tumblr APIがエラーを返しました。", file=sys.stderr)
        return 1

    photo_url = extract_photo_url(client, response)
    if photo_url:
        with open("tumblr_photo_url.txt", "w", encoding="utf-8") as f:
            f.write(photo_url)
        print(f"[INFO] 画像URLを取得しました（LINE配信で再利用します）: {photo_url}")
    else:
        print("[WARN] 画像URLを取得できませんでした。LINE配信では画像なしになります。")

    print("[INFO] Tumblrへの投稿が完了しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
