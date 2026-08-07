#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import smtplib
import sys
from email.mime.text import MIMEText
from email.utils import formatdate

RESULT_JSON_PATH = "result.json"

RECIPIENTS = [
    "k.ikezawa@tobu.net",
    "m.masuoka@tobu.net",
    "t.inoue@tobu.net",
]

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def load_result(path: str = RESULT_JSON_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def send_email(sender: str, app_password: str, recipients: list, subject: str, body: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(sender, app_password)
        server.sendmail(sender, recipients, msg.as_string())


def main() -> int:
    # --- テストモード: TEST_RECIPIENT が設定されていれば、天気判定結果に関係なく
    #     指定した宛先1件だけにテストメールを送信して終了する ---
    test_recipient = os.environ.get("TEST_RECIPIENT")
    if test_recipient:
        sender = os.environ.get("GMAIL_ADDRESS")
        app_password = os.environ.get("GMAIL_APP_PASSWORD")
        if not sender or not app_password:
            print("[ERROR] 環境変数 GMAIL_ADDRESS または GMAIL_APP_PASSWORD が設定されていません。", file=sys.stderr)
            return 1

        subject = "【テスト】雨割り自動配信システム 動作確認メール"
        body = (
            "これは「雨割り自動配信システム」の動作確認用テストメールです。\n"
            "このメールが届いていれば、メール送信の仕組みは正常に動作しています。\n\n"
            "本番運用では、雨割りが適用される日にのみ、実際の配信内容を含む\n"
            "お知らせメールが自動送信されます。\n"
        )
        print(f"[INFO] テストモード: {test_recipient} 宛にテストメールを送信します。")
        try:
            send_email(sender, app_password, [test_recipient], subject, body)
        except Exception as e:
            print(f"[ERROR] テストメール送信に失敗しました: {e}", file=sys.stderr)
            return 1
        print("[INFO] テストメール送信が完了しました。")
        return 0

    result = load_result()
    status = result.get("status")
    print(f"[INFO] result.json の status: {status}")

    if status != "ok":
        print("[INFO] 判定結果が 'ok' ではないため、メール送信は行いません。")
        return 0

    applicable = result.get("applicable")
    target_date = result.get("target_date", "")
    message = result.get("message", "")

    if not applicable:
        print("[INFO] 雨割り非適用のため、メール送信はスキップします。")
        return 0

    sender = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not app_password:
        print("[ERROR] 環境変数 GMAIL_ADDRESS または GMAIL_APP_PASSWORD が設定されていません。", file=sys.stderr)
        return 1

    subject = f"【雨割り適用のお知らせ】{target_date} 配信済み"
    body = (
        f"以下の内容で、TumblrおよびLINEへ雨割りのお知らせを自動配信しました。\n"
        f"（このメールは自動送信です）\n\n"
        f"----------------------------------------\n"
        f"{message}\n"
        f"----------------------------------------\n"
    )

    print(f"[INFO] 雨割り適用のため、メールを送信します。宛先: {RECIPIENTS}")
    try:
        send_email(sender, app_password, RECIPIENTS, subject, body)
    except Exception as e:
        print(f"[ERROR] メール送信に失敗しました: {e}", file=sys.stderr)
        return 1

    print("[INFO] メール送信が完了しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
