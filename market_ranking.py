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
                        "順位": int(clean_numeric_string(tds[0].text)),
                        "コード": re.search(r'\d{4}', code_tag.text).group(),
                        "銘柄名": name_tag.text.strip(),
                        "現在値": float(clean_numeric_string(tds[2].text)),
                        "売買代金(百万円)": int(clean_numeric_string(tds[5].text))
                    })
        except: continue
    return parsed_data

def send_to_discord(webhook_url, lines):
    if not webhook_url: return
    # 40行ずつ分割して送信
    for i in range(0, len(lines), 40):
        message = "
http://googleusercontent.com/immersive_entry_chip/0

このコードを保存して再度実行すれば、エラーが解消され、回転率を含めたデータが正しく通知されるはずです。
