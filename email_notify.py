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
TUMBLR_POST_RESULT_PATH = "tumblr_post_result.txt"

RECIPIENTS = [
    "k.ikezawa@tobu.net",
    "m.masuoka@tobu.net",
    "t.inoue@tobu.net",
    "k.kondou@tobu.net",
]

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

TUMBLR_LOGIN_URL = "https://www.tumblr.com/blog/minamitsukubag"


def load_result(path: str = RESULT_JSON_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_tumblr_post_status(path: str = TUMBLR_POST_RESULT_PATH) -> str:
    if not os.path.exists(path):
        return "unknown"
    with open(path, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()
    return first_line or "unknown"


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


def send_failure_alert(sender: str, app_password: str, status: str, target_date: str) -> None:
    subject = "【緊急・要確認】雨割り自動判定システムが失敗しました"
    reason = {
        "error": "天気予報サイト（ウェザーニュース）へのアクセスに失敗しました。",
        "no_data": "天気予報サイトから、必要なデータが取得できませんでした。",
    }.get(status, f"不明な状態（status={status}）です。")

    body = (
        "雨割り自動判定システムが、本日の判定処理に失敗しました。\n"
        "自動配信（Tumblr・LINE・メール）は行われていません。\n\n"
        f"■ 判定対象日: {target_date}\n"
        f"■ 失敗理由: {reason}\n\n"
        "お手数ですが、以下のいずれかの対応をお願いします。\n"
        "  1. ウェザーニュース「南筑波ゴルフ場」のページを手動で確認し、\n"
        "     必要であれば手動で雨割りを宣言してください。\n"
        "     https://weathernews.jp/golf/kanto/ibaraki/113/\n"
        "  2. しばらく時間を置いて、システムが自動で再試行するのを待つ\n"
        "     （本日 12:30頃にも自動で再試行される設定になっています）\n\n"
        "（このメールは自動送信です）\n"
    )
    print(f"[INFO] 判定失敗のため、緊急アラートメールを送信します。宛先: {RECIPIENTS}")
    send_email(sender, app_password, RECIPIENTS, subject, body)


def build_applicable_body(message: str, tumblr_status: str) -> str:
    parts = []
    parts.append("雨割り適用の判定が出ました。以下の内容で自動配信しています。\n")

    if tumblr_status == "success":
        parts.append("■ ホームページ（Tumblr）: 自動投稿 完了しました。特に対応は不要です。\n")
    else:
        parts.append(
            "■ ホームページ（Tumblr）: 自動投稿に失敗しました。"
            "お手数ですが、下記の手順で手動投稿をお願いします。\n"
            "\n"
            "【手動投稿の手順】\n"
            f"  1. {TUMBLR_LOGIN_URL} を開き、南筑波ゴルフ場のアカウントでログイン\n"
            "  2. 「投稿を作成」→「画像」を選択\n"
            "  3. 添付されている告知画像（amekawari_pop.png）をアップロード\n"
            "  4. 下記の【コピペ用】の文章を、キャプション欄にそのまま貼り付け\n"
            "  5. 「公開」ボタンを押して投稿\n"
        )

    parts.append("■ LINE公式アカウント: 自動配信 完了しました。特に対応は不要です。\n")

    parts.append("\n【コピペ用：配信文章】\n")
    parts.append("----------------------------------------")
    parts.append(message)
    parts.append("----------------------------------------\n")
    parts.append("（このメールは自動送信です）")
    return "\n".join(parts)


def main() -> int:
    test_recipient_raw = os.environ.get("TEST_RECIPIENT")
    if test_recipient_raw:
        test_recipients = [addr.strip() for addr in test_recipient_raw.split(",") if addr.strip()]
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
        body = build_applicable_body(sample_message, tumblr_status="failed")
        body = "【これはテストメールです。以下は仮の内容です】\n\n" + body
        print(f"[INFO] テストモード: {test_recipients} 宛にテストメールを送信します。")
        try:
            send_email(sender, app_password, test_recipients, subject, body, image_path=POP_IMAGE_PATH)
        except Exception as e:
            print(f"[ERROR] テストメール送信に失敗しました: {e}", file=sys.stderr)
            return 1
        print("[INFO] テストメール送信が完了しました。")
        return 0

    result = load_result()
    status = result.get("status")
    print(f"[INFO] result.json の status: {status}")

    sender = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not app_password:
        print("[ERROR] 環境変数 GMAIL_ADDRESS または GMAIL_APP_PASSWORD が設定されていません。", file=sys.stderr)
        return 1

    if status in ("error", "no_data"):
        target_date = result.get("target_date", "不明")
        try:
            send_failure_alert(sender, app_password, status, target_date)
        except Exception as e:
            print(f"[ERROR] 緊急アラートメールの送信に失敗しました: {e}", file=sys.stderr)
            return 1
        print("[INFO] 緊急アラートメールを送信しました。")
        return 0

    applicable = result.get("applicable")
    target_date = result.get("target_date", "")
    message = result.get("message", "")

    if not applicable:
        print("[INFO] 雨割り非適用のため、メール送信はスキップします。")
        return 0

    tumblr_status = load_tumblr_post_status()
    print(f"[INFO] Tumblr投稿結果: {tumblr_status}")

    subject_mark = "" if tumblr_status == "success" else "【要対応】"
    subject = f"{subject_mark}【雨割り適用のお知らせ】{target_date}"
    body = build_applicable_body(message, tumblr_status)

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
