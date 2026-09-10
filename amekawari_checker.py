#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
南筑波ゴルフ場「雨割り」自動判定ツール
"""

import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, date
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

TARGET_URL = "https://weathernews.jp/golf/kanto/ibaraki/113/"
TARGET_HOURS = [7, 8, 9]
RAIN_THRESHOLD_MM = 3.0
MIN_HIT_HOURS = 1
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class HourlyForecast:
    target_date: date
    hour: int
    rain_mm: float


def fetch_page_html(url: str = TARGET_URL, timeout: int = 60, retries: int = 4) -> str:
    last_error = None
    for attempt in range(1, retries + 2):
        try:
            if _PLAYWRIGHT_AVAILABLE:
                return _fetch_page_html_rendered(url, timeout)
            print(
                "[WARN] Playwrightが導入されていません。`pip install playwright` と "
                "`playwright install chromium` を実行してください。",
                file=sys.stderr,
            )
            headers = {"User-Agent": USER_AGENT}
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except Exception as e:
            last_error = e
            print(f"[WARN] ページ取得に失敗しました（{attempt}回目）: {e}", file=sys.stderr)
            if attempt <= retries:
                print("[INFO] 10秒待ってから再試行します...", file=sys.stderr)
                time.sleep(10)
    raise last_error


def _fetch_page_html_rendered(url: str, timeout: int = 45) -> str:
    timeout_ms = timeout * 1000
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, timeout=timeout_ms, wait_until="load")
            try:
                page.wait_for_selector("text=/\\d+mm/", timeout=timeout_ms)
            except Exception:
                pass
            page.wait_for_timeout(2000)
            html = page.content()
        finally:
            browser.close()
    return html


def _resolve_date(day_of_month: int, base_dt: datetime) -> date:
    year, month = base_dt.year, base_dt.month
    if day_of_month < base_dt.day - 3:
        month += 1
        if month > 12:
            month = 1
            year += 1
    try:
        return date(year, month, day_of_month)
    except ValueError:
        month += 1
        if month > 12:
            month = 1
            year += 1
        return date(year, month, day_of_month)


def parse_hourly_forecast(html: str, base_dt: Optional[datetime] = None) -> List[HourlyForecast]:
    if base_dt is None:
        base_dt = datetime.now()

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    date_pat = re.compile(r"^(\d{1,2})日\([日月火水木金土]\)$")
    hour_pat = re.compile(r"^(\d{1,2})$")
    num_pat = re.compile(r"^\d+(?:\.\d+)?$")

    results: List[HourlyForecast] = []
    current_date: Optional[date] = None

    try:
        start_idx = lines.index("南筑波ゴルフ場の天気予報") + 1
    except ValueError:
        start_idx = 0

    i = start_idx
    n = len(lines)
    while i < n:
        line = lines[i]

        m_date = date_pat.match(line)
        if m_date:
            current_date = _resolve_date(int(m_date.group(1)), base_dt)
            i += 1
            continue

        if line in ("5分毎", "1時間毎", "今日明日", "2週間天気", "凡例", "実況天気・観測値"):
            break

        m_hour = hour_pat.match(line)
        if m_hour and current_date is not None:
            hour_val = int(m_hour.group(1))
            if 0 <= hour_val <= 23:
                if (
                    i + 4 < n
                    and num_pat.match(lines[i + 1])
                    and lines[i + 2] == "mm"
                    and num_pat.match(lines[i + 3])
                    and lines[i + 4] == "℃"
                ):
                    rain_mm = float(lines[i + 1])
                    results.append(HourlyForecast(current_date, hour_val, rain_mm))
                    if i + 6 < n and num_pat.match(lines[i + 5]) and lines[i + 6] == "m":
                        i += 7
                    else:
                        i += 5
                    continue
        i += 1

    return results


def _build_applicable_message(target_date: date) -> str:
    weekday_kanji = ["月", "火", "水", "木", "金", "土", "日"]
    weekday_str = weekday_kanji[target_date.weekday()]
    date_str = f"{target_date.month}/{target_date.day}({weekday_str})"

    return (
        "★雨割り営業のお知らせ★\n"
        f"明日{date_str}は、「雨割りプラン」を適用いたします。\n"
        "本日中に公式Webサイトまたは電話でのご予約の方が必要となりますので\n"
        "ご注意ください。\n"
        "ご予約がない場合は適用されませんのでご予約お待ちしております。\n"
        "\n"
        "・ラウンド：2,000円引き（税込）\n"
        "・ハーフ　：1,000円引き（税込）\n"
        "\n"
        "予約・お問い合わせ：営業課予約係 TEL 029-847-7521"
    )


def judge_amekawari(
    forecasts: List[HourlyForecast],
    target_date: date,
    target_hours: List[int] = TARGET_HOURS,
    threshold_mm: float = RAIN_THRESHOLD_MM,
    min_hit_hours: int = MIN_HIT_HOURS,
):
    checked = [f for f in forecasts if f.target_date == target_date and f.hour in target_hours]
    if not checked:
        return None, [], []

    matched = [f for f in checked if f.rain_mm >= threshold_mm]
    applicable = len(matched) >= min_hit_hours
    return applicable, matched, checked


def run(save_json_path: str = "result.json") -> dict:
    now = datetime.now()
    target_date = (now + timedelta(days=1)).date()

    print(f"[INFO] 実行日時: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[INFO] 判定対象日（翌日）: {target_date}")
    print(f"[INFO] 判定対象時間帯: {TARGET_HOURS} 時台")
    print(f"[INFO] 閾値: {RAIN_THRESHOLD_MM}mm/h 以上 が {MIN_HIT_HOURS}時間以上")
    print(f"[INFO] データ取得元: {TARGET_URL}")

    try:
        html = fetch_page_html(TARGET_URL)
    except Exception as e:
        print(f"[ERROR] ページ取得に失敗しました: {e}")
        result = {
            "status": "error",
            "message": f"fetch failed: {e}",
            "target_date": str(target_date),
        }
        _save_json(result, save_json_path)
        return result

    forecasts = parse_hourly_forecast(html, base_dt=now)
    applicable, matched, checked = judge_amekawari(forecasts, target_date)

    if applicable is None:
        print("[WARN] 対象日・対象時間帯のデータが取得できませんでした。判定不可。")
        result = {
            "status": "no_data",
            "target_date": str(target_date),
            "target_hours": TARGET_HOURS,
        }
        _save_json(result, save_json_path)
        return result

    print("[INFO] 対象時間帯の予報値:")
    for f in checked:
        mark = " ← 3mm以上" if f.rain_mm >= RAIN_THRESHOLD_MM else ""
        print(f"    {f.hour}時台: {f.rain_mm}mm{mark}")

    if applicable:
        print("\n=== 判定結果: 【雨割り適用】 ===")
        for f in matched:
            print(f"  該当: {f.hour}時台 {f.rain_mm}mm")
    else:
        print("\n=== 判定結果: 【雨割り適用なし】 ===")

    result = {
        "status": "ok",
        "target_date": str(target_date),
        "target_hours": TARGET_HOURS,
        "threshold_mm": RAIN_THRESHOLD_MM,
        "applicable": applicable,
        "checked": [asdict(f) | {"target_date": str(f.target_date)} for f in checked],
        "matched_hours": [f.hour for f in matched],
        "generated_at": now.isoformat(),
        "message": (
            _build_applicable_message(target_date)
            if applicable
            else (
                f"{target_date.strftime('%m月%d日')}の天気予報では、雨割り適用条件（7時〜10時の間に"
                f"1時間降水量3mm以上）に該当しませんでした。雨割りは適用されません。"
            )
        ),
    }
    _save_json(result, save_json_path)
    return result


def _save_json(result: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[INFO] 判定結果を {path} に保存しました。")


if __name__ == "__main__":
    res = run()
    if res.get("status") != "ok":
        sys.exit(1)
    sys.exit(0)
