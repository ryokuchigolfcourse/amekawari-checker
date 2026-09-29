#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雨割り メール通知スクリプト（2026/9/29改訂：メール配信のみ版）
================================================================

amekawari_checker.py が出力した result.json を読み込み、
「雨割り適用」の場合のみ、社内スタッフへメールで通知する。
（LINE公式アカウント・ホームページ(Tumblr)への自動投稿は廃止し、
  メール配信のみとした）

【認証情報】
以下を環境変数から読み込む（GitHub Actionsでは Secrets から渡す）:
  - GMAIL_ADDRESS         送信元Gmailアドレス
  - GMAIL_APP_PASSWORD    Gmailアプリパスワード

【配信先】
  通常運用時（雨割り適用/非適用いずれのメールも）は RECIPIENTS の
  8名に送信する。

  テスト実行時（GitHub ActionsのSecrets/envで TEST_RECIPIENT が
  設定されている場合）は、RECIPIENTS の代わりに TEST_RECIPIENT
  （カンマ区切りで複数指定可）に送信する。
"""

import json
import os
import smtplib
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

RESULT_JSON_PATH = "result.json"
POP_IMAGE_PATH = "amekawari_pop.png"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# 本番運用時の配信先（8名）
RECIPIENTS = [
    "k.ikezawa@tobu.net",
    "m.masuoka@tobu.net",
    "imaizumi@tobu.net",
    "tokoyo@tobu.net",
    "k.sekiguchi@tobu.net",
    "m.matsuda@tobu.net",
    "t.inoue@tobu.net",
    "info_minamitsukuba@tobu.net",
]


def load_result(path: str = RESULT_JSON_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_recipients() -> list:
    """
    TEST_RECIPIENT 環境変数が設定されていればそちらを優先する
    （テスト実行時に本番の8名へ誤送信しないため）。
    カンマ区切りで複数指定可。既定はテスト時も t.inoue@tobu.net のみ。
    """
    test_recipient = os.environ.get("TEST_RECIPIENT", "").strip()
    if test_recipient:
        return [addr.strip() for addr in test_recipient.split(",") if addr.strip()]
    return RECIPIENTS


def build_applicable_subject(target_date: str) -> str:
    return f"【雨割り適用】{target_date} 雨割りプランを適用します"


def build_applicable_body(result: dict) -> str:
    target_date = result.get("target_date", "")
    message = result.get("message", "")
    matched_hours = result.get("matched_hours", [])
    checked = result.get("checked", [])

    lines = []
    lines.append(f"【対象日】{target_date}")
    lines.append("")
    lines.append("ウェザーニュースの予報に基づき、雨割り適用条件（前日11:59時点で")
    lines.append("翌日7時〜14時の間に1時間降水量2mm以上5mm未満の予報が1時間以上）を")
    lines.append("満たしたため、雨割りプランを適用します。")
    lines.append("")
    lines.append("---- 配信文言（LINE・掲示等に転用する場合はこのままお使いください） ----")
    lines.append(message)
    lines.append("--------------------------------------------------------------")
    lines.append("")

    if matched_hours:
        lines.append(f"該当時間帯: {', '.join(str(h) + '時台' for h in matched_hours)}")

    if checked:
        lines.append("")
        lines.append("【参考：対象時間帯の予報値】")
        for c in checked:
            lines.append(f"  {c.get('hour')}時台: {c.get('rain_mm')}mm")

    lines.append("")
    lines.append("※本メールはGitHub Actionsによる自動判定・自動送信です。")

    return "\n".join(lines)


def send_email(subject: str, body: str, recipients: list, attach_pop_image: bool = False) -> None:
    gmail_address = os.environ["GMAIL_ADDRESS"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEMultipart()
    msg["From"] = gmail_address
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attach_pop_image and os.path.exists(POP_IMAGE_PATH):
        with open(POP_IMAGE_PATH, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(POP_IMAGE_PATH))
        part["Content-Disposition"] = f'attachment; filename="{os.path.basename(POP_IMAGE_PATH)}"'
        msg.attach(part)
    elif attach_pop_image:
        print(
            f"[WARN] POP画像 '{POP_IMAGE_PATH}' が見つからないため、添付なしで送信します。",
            file=sys.stderr,
        )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(gmail_address, gmail_app_password)
        server.sendmail(gmail_address, recipients, msg.as_string())


def send_failure_alert(result: dict, recipients: list) -> None:
    status = result.get("status", "unknown")
    target_date = result.get("target_date", "")
    subject = "【要確認】雨割り自動判定でエラーが発生しました"

    if status == "no_data":
        detail = (
            "ウェザーニュースのページから対象時間帯の降水量データを取得できず、"
            "判定不可（no_data）となりました。"
        )
    else:
        detail = f"判定処理中にエラーが発生しました（status={status}）。\n{result.get('message', '')}"

    body = (
        f"【対象日】{target_date}\n\n"
        f"{detail}\n\n"
        "自動判定が正常に完了しなかったため、手動でウェザーニュースの予報を"
        "ご確認いただくようお願いいたします。\n"
        "（本日11:59頃と12:30頃の2回、自動で再試行する仕組みになっています。"
        "既に両方とも失敗している場合は、上記の手動確認をお願いします。）\n\n"
        "※本メールはGitHub Actionsによる自動送信です。"
    )
    send_email(subject, body, recipients, attach_pop_image=False)
    print(f"[INFO] エラー通知メールを送信しました（宛先: {', '.join(recipients)}）")


def main() -> int:
    recipients = get_recipients()
    print(f"[INFO] 配信先: {', '.join(recipients)}")

    try:
        result = load_result()
    except FileNotFoundError:
        print("[ERROR] result.json が見つかりません。", file=sys.stderr)
        return 1

    status = result.get("status")
    print(f"[INFO] result.json の status: {status}")

    if status in ("error", "no_data"):
        send_failure_alert(result, recipients)
        return 0

    if status != "ok":
        print(f"[WARN] 未知のstatusです（{status}）。メール送信をスキップします。")
        return 0

    applicable = result.get("applicable")
    target_date = result.get("target_date", "")

    if not applicable:
        print("[INFO] 雨割り非適用のため、メール送信はスキップします（適用時のみ送信）。")
        return 0

    print("[INFO] 雨割り適用のため、メールを送信します。")
    subject = build_applicable_subject(target_date)
    body = build_applicable_body(result)
    send_email(subject, body, recipients, attach_pop_image=True)

    print("[INFO] メール送信が完了しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
