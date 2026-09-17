#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tumblr認証テスト専用スクリプト
"""

import os
import sys

import pytumblr

BLOG_IDENTIFIER = "minamitsukubag.tumblr.com"


def main():
    consumer_key = os.environ["TUMBLR_CONSUMER_KEY"]
    consumer_secret = os.environ["TUMBLR_CONSUMER_SECRET"]
    oauth_token = os.environ["TUMBLR_OAUTH_TOKEN"]
    oauth_token_secret = os.environ["TUMBLR_OAUTH_TOKEN_SECRET"]

    client = pytumblr.TumblrRestClient(
        consumer_key, consumer_secret, oauth_token, oauth_token_secret
    )

    info = client.info()
    print("[INFO] Tumblr API レスポンス:")
    print(info)

    if "meta" in info and info["meta"].get("status") not in (200, None):
        print("[ERROR] 認証エラーです。", file=sys.stderr)
        return 1

    if "user" in info:
        print(f"[INFO] 認証成功。ユーザー名: {info['user'].get('name')}")
        return 0

    print("[WARN] 想定外のレスポンス形式でした。上記内容を確認してください。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
