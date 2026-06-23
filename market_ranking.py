import datetime
import os
import re
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

def clean_numeric(text):
    return float(re.sub(r'[^\d.]', '', str(text).replace(',', '')))

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
            table = soup.find("table", class_="m-table")
            if not table: continue
            for row in table.find("tbody").find_all("tr"):
                tds = row.find_all("td")
                if len(tds) < 6: continue
                name_tag, code_tag = tds[1].find("a"), tds[1].find("span")
                if name_tag and code_tag:
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
    if not webhook_url: return
    for i in range(0, len(lines), 40):
        message = "
http://googleusercontent.com/immersive_entry_chip/0

### 次のステップ
1. このコードに差し替えて再度 GitHub Actions を実行してください。
2. これでエラーが消えれば解決です！もしまたエラーになる場合は、Actionsのタブで「どの行（何行目）でエラーが出ているか」を確認します。

警告の `Node.js 20 is deprecated` については、引き続き無視して問題ありません（現在の動作には一切支障ありません）。
