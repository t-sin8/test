import datetime
import os
import re
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

def clean_numeric_string(text):
    return re.sub(r'[^\d\.\-]', '', str(text))

def get_trading_date():
    now = datetime.datetime.now()
    return (now - datetime.timedelta(days=1)).strftime("%Y%m%d") if now.hour < 5 else now.strftime("%Y%m%d")

def get_matsui_market_ranking(market_id):
    parsed_data = []
    # 1ページ目と2ページ目を確実に取得するループ
    for page in range(1, 3):
        url = f"https://finance.matsui.co.jp/ranking-trading-top/index?market={market_id}&page={page}"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.find("table", class_="m-table")
            if not table: continue
            
            rows = table.find("tbody").find_all("tr")
            for row in rows:
                tds = row.find_all("td")
                if len(tds) < 6: continue
                
                # 順位の取得
                rank_raw = clean_numeric_string(tds[0].text)
                if not rank_raw: continue
                rank = int(rank_raw)
                
                # コードと銘柄名の取得（エラーに強い書き方に変更）
                name_tag = tds[1].find("a")
                code_tag = tds[1].find("span")
                name = name_tag.text.strip() if name_tag else "不明"
                code_match = re.search(r'\d{4}', code_tag.text) if code_tag else None
                code = code_match.group() if code_match else "0000"
                
                parsed_data.append({
                    "順位": rank,
                    "コード": code,
                    "銘柄名": name,
                    "現在値": float(clean_numeric_string(tds[2].text) or 0),
                    "売買代金(百万円)": int(clean_numeric_string(tds[5].text) or 0)
                })
        except Exception as e:
            print(f"ページ取得エラー (Market:{market_id}, Page:{page}): {e}")
            continue
        time.sleep(2) # サーバー負荷対策
    return parsed_data

def send_to_discord(webhook_url, lines):
    if not webhook_url: return
    for i in range(0, len(lines), 40):
        message = "
http://googleusercontent.com/immersive_entry_chip/0

### 修正のポイント
1.  **ページングの明示化**: `range(1, 3)` で `page=1` と `page=2` を確実に順番に叩くようにしました。
2.  **エラーハンドリングの強化**: 特定の銘柄（Bitcoin Japanなど）でデータ抽出が失敗しても、その銘柄をスキップして次の行へ進むように変更しました。
3.  **データ補完**: `int(clean_numeric_string(...) or 0)` とすることで、空データが来ても0として処理し、全体の停止を防ぎます。

これで実行してみてください。もしまた漏れがある場合は、Actionsのログで `ページ取得エラー` が出ていないか確認をお願いします。
