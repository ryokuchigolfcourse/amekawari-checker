#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
南筑波ゴルフ場「雨割り」自動判定ツール
====================================

【適用条件（2026/9/29改訂版）】
  前日11:59時点で、翌日 7:00〜14:00 の間に
  「1時間以上、1時間降水量が2mm以上5mm未満」の予報がある場合に適用し、
  雨割りを宣言する。
  当日の降雨については適用されない（＝前日11:59時点の“予報”だけで判定する）。

【データ取得元】
  ウェザーニュース「南筑波ゴルフ場の天気」ページ
  https://weathernews.jp/golf/kanto/ibaraki/113/
  （1時間ごとの降水量[mm]が日付・時刻付きで掲載されている）

【使い方】
  $ python3 amekawari_checker.py
  → 実行日の翌日を対象に判定し、結果を標準出力＆JSON（result.json）に保存する。

  ※本ツールは「前日11:59頃に実行する」ことを想定しています
    （GitHub Actionsで毎日11:59・12:30の2回、二重実行防止つきで自動実行）。

【重要な前提・要調整ポイント】
  1. 「7時〜14時の間」の解釈:
       ・当ページは "7時" "8時" ... "14時" という「毎正時の値」として降水量[mm]を
         表示しており、その「直前1時間（例: 8時 → 7時〜8時の降水量）」の
         予報値を表す。
       ・7時〜14時までの間の1時間降水量を見るため、
         TARGET_HOURS = [7, 8, 9, 10, 11, 12, 13] としている
         （14時台の値は「13時〜14時」を表すため13を含めればよい）。
  2. サイトのHTML構造は今後変わる可能性があるため、パーサはテキストの並び
     （日付見出し→時刻→降水量mm→気温℃→風m）というパターンに依存した
     やや保守的な実装にしています。サイト改修時は再調整が必要です。
  3. 本ツールは実行環境からウェザーニュースのサイトへ実際にHTTPアクセスできる
     ことを前提としています。
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

# このページはJavaScriptで時間ごとの天気データを後から描画するSPA(Ajax)方式のため、
# 単純なrequests.get()だけでは降水量データが1件も取得できません（= 常にno_data）。
# そのため、ヘッドレスブラウザ(Playwright)でJavaScript実行後のHTMLを取得します。
# 事前に以下のインストールが必要です:
#   pip install playwright --break-system-packages
#   playwright install chromium --with-deps
try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

# ============ 設定項目（ここを調整すれば挙動を変更できます） ============

# 判定対象ページ
TARGET_URL = "https://weathernews.jp/golf/kanto/ibaraki/113/"

# 判定対象とする「時」（24時間表記）。7時〜14時の間の1時間降水量を見る。
# 7時台〜13時台の7つ（13時台の値が「13時〜14時」の降水量を表すため、
# これで「7時〜14時」をすべてカバーする）。
TARGET_HOURS = [7, 8, 9, 10, 11, 12, 13]

# 「1時間降水量2mm以上5mm未満」の閾値(mm)　※下限含む・上限含まない
RAIN_THRESHOLD_MIN_MM = 2.0
RAIN_THRESHOLD_MAX_MM = 5.0

# 何時間以上、条件を満たしていれば適用とするか（依頼文の「1時間以上」に対応）
MIN_HIT_HOURS = 1

# リクエスト時のUser-Agent（サイト側に人間のブラウザとして認識してもらうため）
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ====================================================================


@dataclass
class HourlyForecast:
    target_date: date
    hour: int
    rain_mm: float


def fetch_page_html(url: str = TARGET_URL, timeout: int = 60, retries: int = 4) -> str:
    """
    ウェザーニュースのゴルフ場天気ページのHTMLを取得する。

    このページは時間ごとの天気データをJavaScriptで後から描画するため、
    Playwrightが利用可能であればヘッドレスブラウザで描画後のHTMLを取得する
    （こちらが本来の正しい取得方法）。
    Playwright未導入の環境では、参考として単純なrequests取得にフォールバック
    するが、その場合は降水量データが取得できず判定不能(no_data)になる
    可能性が高い点に注意。

    クラウド実行環境からのアクセスは、まれに一時的な遅延で失敗することが
    あるため、失敗時は少し間隔を空けて最大 retries 回まで再試行する。
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 2):  # 初回 + retries回
        try:
            if _PLAYWRIGHT_AVAILABLE:
                return _fetch_page_html_rendered(url, timeout)
            print(
                "[WARN] Playwrightが導入されていません。JavaScriptで描画される降水量データが"
                "取得できない可能性が高いです。`pip install playwright --break-system-packages` "
                "と `playwright install chromium --with-deps` を実行してください。",
                file=sys.stderr,
            )
            headers = {"User-Agent": USER_AGENT}
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except Exception as e:
            last_error = e
            print(
                f"[WARN] ページ取得に失敗しました（{attempt}回目）: {e}",
                file=sys.stderr,
            )
            if attempt <= retries:
                wait_seconds = 15
                print(f"[INFO] {wait_seconds}秒待ってから再試行します...", file=sys.stderr)
                time.sleep(wait_seconds)

    assert last_error is not None
    raise last_error


def _fetch_page_html_rendered(url: str, timeout: int = 60) -> str:
    """PlaywrightでJavaScript実行後のHTMLを取得する"""
    timeout_ms = timeout * 1000
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            # 広告・計測タグ等の常時通信があるため "networkidle" ではなく
            # "load"（ページの読み込み完了）を待つ方式に変更
            page.goto(url, timeout=timeout_ms, wait_until="load")
            # 時間ごとの予報リストが描画されるまで少し待つ（"mm"表記が出るまで）
            try:
                page.wait_for_selector("text=/\\d+mm/", timeout=timeout_ms)
            except Exception:
                # 見つからなくても、取得できているHTMLでベストエフォートのパースを試みる
                pass
            # 遅延読み込みの完了を少し待つ
            page.wait_for_timeout(2000)
            html = page.content()
        finally:
            browser.close()
    return html


def _resolve_date(day_of_month: int, base_dt: datetime) -> date:
    """
    ページ上の日付表記は「1日(土)」のように「日」しか分からないため、
    実行時点の年月を基準に、直近で辻褄が合う年月を推定する。
    （ページの並びは実行日から始まる連続した日付のはずなので、
      day_of_month が base_dt.day より小さければ月が繰り上がったとみなす）
    """
    year, month = base_dt.year, base_dt.month
    if day_of_month < base_dt.day - 3:
        # 明らかに月が繰り上がっているケース（例: 実行日30日 → 表記1日）
        month += 1
        if month > 12:
            month = 1
            year += 1
    try:
        return date(year, month, day_of_month)
    except ValueError:
        # 月末調整などで失敗した場合のフォールバック
        month += 1
        if month > 12:
            month = 1
            year += 1
        return date(year, month, day_of_month)


def parse_hourly_forecast(html: str, base_dt: Optional[datetime] = None) -> List[HourlyForecast]:
    """
    ページのHTMLから「日付・時刻・降水量(mm)」の並びをテキストベースで抽出する。

    実測したページ構造（get_text()で1行ずつ取り出した場合）:
        1日(土)      <- 日付見出し
        6            <- 時刻(0-23)
        0            <- 降水量の数値
        mm           <- 単位（別行！）
        26           <- 気温の数値
        ℃            <- 単位（別行）
        1            <- 風速の数値
        m            <- 単位（別行）
        7            <- 次の時刻
        0
        mm
        ...

    ※数値と単位（mm/℃/m）が別々のテキストノードになっているため、
      「時刻」の直後6行を [降水値, 'mm', 気温値, '℃', 風速値, 'm'] という
      固定パターンとして読み取る。
    """
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

    # 「南筑波ゴルフ場の天気予報」という見出しより前（ヘッダーメニュー等）は無視する
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

        # 「5分毎」などのタブ切り替え文言が出たら、1時間ごとの表は終了
        if line in ("5分毎", "1時間毎", "今日明日", "2週間天気", "凡例", "実況天気・観測値"):
            break

        m_hour = hour_pat.match(line)
        if m_hour and current_date is not None:
            hour_val = int(m_hour.group(1))
            if 0 <= hour_val <= 23:
                # 直後が [降水値, 'mm', 気温値, '℃', 風速値, 'm'] の固定パターンかを確認
                if (
                    i + 4 < n
                    and num_pat.match(lines[i + 1])
                    and lines[i + 2] == "mm"
                    and num_pat.match(lines[i + 3])
                    and lines[i + 4] == "℃"
                ):
                    rain_mm = float(lines[i + 1])
                    results.append(HourlyForecast(current_date, hour_val, rain_mm))
                    # 風速部分（数値 + 'm'）まで読み飛ばす。無ければ気温までで止める。
                    if i + 6 < n and num_pat.match(lines[i + 5]) and lines[i + 6] == "m":
                        i += 7
                    else:
                        i += 5
                    continue
        i += 1

    return results


def _build_applicable_message(target_date: date) -> str:
    """
    実際に運用されているLINE配信文言と同じ形式のお知らせ文を生成する。
    （現在は社内メール本文にそのまま利用している）

    実物サンプル（2026/7/2配信分）:
        ★雨割り営業のお知らせ★
        明日7/2(木)は、「雨割りプラン」を適用いたします。
        本日中に公式Webサイトまたは電話でのご予約が必要となりますので
        ご注意ください。
        ご予約がない場合は適用されませんのでご予約お待ちしております。

        ・ラウンド：2,000円引き（税込）
        ・ハーフ　：1,000円引き（税込）
    """
    weekday_kanji = ["月", "火", "水", "木", "金", "土", "日"]
    weekday_str = weekday_kanji[target_date.weekday()]
    date_str = f"{target_date.month}/{target_date.day}({weekday_str})"

    return (
        "★雨割り営業のお知らせ★\n"
        f"明日{date_str}は、「雨割りプラン」を適用いたします。\n"
        "本日中に公式Webサイトまたは電話でのご予約が必要となりますので\n"
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
    threshold_min_mm: float = RAIN_THRESHOLD_MIN_MM,
    threshold_max_mm: float = RAIN_THRESHOLD_MAX_MM,
    min_hit_hours: int = MIN_HIT_HOURS,
):
    """
    翌日の対象時間帯（既定: 7時〜14時＝7〜13時台）の降水量予報から、
    雨割り適用可否を判定する。

    条件: 1時間降水量が threshold_min_mm 以上 threshold_max_mm 未満（半開区間）
          の時間帯が min_hit_hours 時間以上あること。

    戻り値:
        applicable: True=適用 / False=非適用 / None=データ取得不可（判定できない）
        matched:    条件を満たした時刻のリスト
        checked:    対象時間帯として実際に見つかったデータ一覧（デバッグ・確認用）
    """
    checked = [f for f in forecasts if f.target_date == target_date and f.hour in target_hours]
    if not checked:
        return None, [], []

    matched = [f for f in checked if threshold_min_mm <= f.rain_mm < threshold_max_mm]
    applicable = len(matched) >= min_hit_hours
    return applicable, matched, checked


def run(save_json_path: str = "result.json") -> dict:
    now = datetime.now()
    target_date = (now + timedelta(days=1)).date()

    print(f"[INFO] 実行日時: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[INFO] 判定対象日（翌日）: {target_date}")
    print(f"[INFO] 判定対象時間帯: {TARGET_HOURS} 時台")
    print(
        f"[INFO] 閾値: {RAIN_THRESHOLD_MIN_MM}mm/h 以上 {RAIN_THRESHOLD_MAX_MM}mm/h 未満 "
        f"が {MIN_HIT_HOURS}時間以上"
    )
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
        mark = (
            " ← 該当（2mm以上5mm未満）"
            if RAIN_THRESHOLD_MIN_MM <= f.rain_mm < RAIN_THRESHOLD_MAX_MM
            else ""
        )
        print(f"    {f.hour}時台: {f.rain_mm}mm{mark}")

    if applicable:
        print(f"\n=== 判定結果: 【雨割り適用】 ===")
        for f in matched:
            print(f"  該当: {f.hour}時台 {f.rain_mm}mm")
    else:
        print(f"\n=== 判定結果: 【雨割り適用なし】 ===")

    result = {
        "status": "ok",
        "target_date": str(target_date),
        "target_hours": TARGET_HOURS,
        "threshold_min_mm": RAIN_THRESHOLD_MIN_MM,
        "threshold_max_mm": RAIN_THRESHOLD_MAX_MM,
        "applicable": applicable,
        "checked": [asdict(f) | {"target_date": str(f.target_date)} for f in checked],
        "matched_hours": [f.hour for f in matched],
        "generated_at": now.isoformat(),
        # ここに配信文言のテンプレを入れておくと、そのままメール配信に使える
        "message": (
            _build_applicable_message(target_date)
            if applicable
            else (
                f"{target_date.strftime('%m月%d日')}の天気予報では、雨割り適用条件（7時〜14時の間に"
                f"1時間降水量2mm以上5mm未満）に該当しませんでした。雨割りは適用されません。"
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
    # 適用時はexit code 0、非適用は0、エラー/データなしは1 で終了
    # （cron等での後続処理・アラート連携をしやすくするため）
    if res.get("status") != "ok":
        sys.exit(1)
    sys.exit(0)
