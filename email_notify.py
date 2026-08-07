#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import smtplib
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.utils import formatdate

RESULT_JSON_PATH = "result.json"
POP_IMAGE_PATH = "amekawari_pop.png"

RECIPIENTS = [
    "k.ikezawa@tobu.net",
    "m.masuoka@tobu.net",
    "t.inoue@tobu.net",
    "k.kondou@tobu.net",
]

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def load_result(path: str = RESULT_JSON_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def send_email(
    sender: str,
    app_password: str,
    recipients: list,
    subject: str,
    body: str,
    image_path: str = None,
) -> None:
    if image_path and os.path.exists(image_path):
        msg = MIMEMultipart()
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with open(image_path, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header(
                "Content-Disposition", "attachment", filename=os.path.basename(image_path)
            )
            msg.attach(img)
    else:
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
    test_recipient = os.environ.get("TEST_RECIPIENT")
    if test_recipient:
        sender = os.environ.get("GMAIL_ADDRESS")
        app_password = os.environ.get("GMAIL_APP_PASSWORD")
        if not sender or not app_password:
            print("[ERROR] 環境変数 GMAIL_ADDRESS または GMAIL_APP_PASSWORD が設定されていません。", file=sys.stderr)
            return 1

        subject = "【テスト】雨割り自動配信システム 動作確認メール（仮内容）"
        sample_message = (
            "★雨割り営業のお知らせ★\n"
            "明日8/4(火)は、「雨割りプラン」を適用いたします。\n"
            "本日中に公式Webサイトまたは電話でのご予約の方が必要となりますので\n"
            "ご注意ください。\n"
            "ご予約がない場合は適用されませんのでご予約お待ちしております。\n"
            "\n"
            "・ラウンド：2,000円引き（税込）\n"
            "・ハーフ　：1,000円引き（税込）\n"
            "\n"
            "予約・お問い合わせ：営業課予約係 TEL 029-847-7521"
        )
        body = (
            "これは「雨割り自動配信システム」の動作確認用テストメールです。\n"
            "（※日付・内容は仮のものです。実際の配信では、その日の判定結果に応じた\n"
            "　正しい日付・内容が自動生成されます）\n\n"
            "実際にTumblr・LINEへ配信されるのと同じ文面・画像を、以下に再現しています。\n\n"
            "----------------------------------------\n"
            f"{sample_message}\n"
            "----------------------------------------\n"
            "\n"
            "（添付：告知用POP画像）\n"
        )
        print(f"[INFO] テストモード: {test_recipient} 宛にテストメールを送信します。")
        try:
            send_email(sender, app_password, [test_recipient], subject, body, image_path=POP_IMAGE_PATH)
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
        send_email(sender, app_password, RECIPIENTS, subject, body, image_path=POP_IMAGE_PATH)
    except Exception as e:
        print(f"[ERROR] メール送信に失敗しました: {e}", file=sys.stderr)
        return 1

    print("[INFO] メール送信が完了しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
