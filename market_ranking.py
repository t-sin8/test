import datetime
import os
import re
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

def clean_numeric(text):
    return float(re.sub(r'[^\d.]', '', text.replace(',', '')))

def get_trading_date():
    now = datetime.datetime.now()
    return (now - datetime.timedelta(days=1)).strftime("%Y%m%d") if now.hour < 5 else now.strftime("%Y%m%d")

def get_matsui_market_ranking(market_id):
    parsed_data = []
    urls = [f"https://finance.matsui.co.jp/ranking-trading-top/index?market={market_id}",
            f"https://finance.matsui.co.jp/ranking-trading-top/index?market={market_id}&page=2"]
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            rows = soup.find("table", class_="m-table").find("tbody").find_all("tr")
            for row in rows:
                tds = row.find_all("td")
                if len(tds) < 6: continue
                name_tag, code_tag = tds[1].find("a"), tds[1].find("span")
                parsed_data.append({
                    "順位": int(re.sub(r'[^\d]', '', tds[0].text)),
                    "コード": re.search(r'\d{4}', code_tag.text).group(),
                    "銘柄名": name_tag.text.strip(),
                    "現在値": clean_numeric(tds[2].text),
                    "売買代金(百万円)": int(clean_numeric(tds[5].text))
                })
        except: continue
    return parsed_data

def send_to_discord(webhook_url, lines):
    for i in range(0, len(lines), 40): # 40行ずつ分割送信
        message = "
http://googleusercontent.com/immersive_entry_chip/0

### 修正後のポイント
1.  **3市場対応**: `main()` 関数のリストに3市場すべて含めました。これでプライム・スタンダード・グロースすべて通知されます。
2.  **ロジックの統合**: 「抜けた・入った・維持」の比較ロジックを復活させました。
3.  **回転率の追加**: 比較ロジックの下に「注目の大口銘柄」として回転率のデータを追加しました。

これで、以前の使い慣れた形式に戻りつつ、新しい「大口シグナル」も受け取れるようになります！上書きして再度実行してみてください。
