import datetime
import os
import re
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

# Discordへの送信関数（これがないと通知されません）
def send_to_discord(webhook_url, lines):
    if not webhook_url:
        return
    
    # メッセージを1600文字以内で分割して送信
    chunk = []
    current_len = 0
    for line in lines:
        if current_len + len(line) + 1 > 1600:
            message = "```\n" + "\n".join(chunk) + "\n```"
            requests.post(webhook_url, json={"content": message})
            time.sleep(1.5)
            chunk = []
            current_len = 0
        chunk.append(line)
        current_len += len(line) + 1
    
    if chunk:
        message = "```\n" + "\n".join(chunk) + "\n```"
        requests.post(webhook_url, json={"content": message})

def get_matsui_market_ranking(market_id):
    parsed_data = []
    urls = [
        f"https://finance.matsui.co.jp/ranking-trading-top/index?market={market_id}",
        f"https://finance.matsui.co.jp/ranking-trading-top/index?market={market_id}&page=2"
    ]
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
                
                name_tag = tds[1].find("a")
                code_tag = tds[1].find("span")
                if not (name_tag and code_tag): continue
                
                parsed_data.append({
                    "順位": int(re.sub(r'[^\d]', '', tds[0].text)),
                    "コード": re.search(r'\d{4}', code_tag.text).group(),
                    "銘柄名": name_tag.text.strip(),
                    "現在値": float(re.sub(r'[^\d.]', '', tds[2].text.replace(',', ''))),
                    "売買代金(百万円)": int(re.sub(r'[^\d]', '', tds[5].text.replace(',', '')))
                })
        except: continue
    return parsed_data

def process_market(market_id, market_name, file_suffix, webhook_url):
    ranking_data = get_matsui_market_ranking(market_id)
    if not ranking_data: return
    
    # 株式数データの読み込み
    try:
        shares_df = pd.read_csv("shares.csv", dtype={"コード": str})
        shares_map = {str(c).strip(): int(s) for c, s in zip(shares_df["コード"], shares_df["発行済株式数"])}
    except:
        shares_map = {}

    df = pd.DataFrame(ranking_data)
    
    # 時価総額・回転率計算
    def calc(row):
        shares = shares_map.get(str(row["コード"]).strip(), 0)
        market_cap = (row["現在値"] * shares) / 1000000 if shares > 0 else 0
        turnover = (row["売買代金(百万円)"] / market_cap * 100) if market_cap > 0 else 0
        return market_cap, turnover

    df[["時価総額", "回転率"]] = df.apply(calc, axis=1, result_type="expand")

    # Discord通知用テキスト作成（強制的に作成する）
    lines = [f"📈 【{market_name}】売買代金ランキング", "=" * 35]
    for _, row in df.iterrows():
        lines.append(f"{row['順位']:>3}位 {row['コード']} {row['銘柄名']}")

    # 注目銘柄
    high_turnover = df[df["回転率"] >= 5.0].sort_values("回転率", ascending=False)
    if not high_turnover.empty:
        lines.append("\n🔥【注目の大口・材料銘柄】(回転率5%超):")
        for _, row in high_turnover.head(5).iterrows():
            lines.append(f"  {row['コード']} {row['銘柄名']} ({row['回転率']:.1f}% / {row['売買代金(百万円)']}M)")

    # 確実に送信
    send_to_discord(webhook_url, lines)

def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    markets = [
        (1, "東証プライム", "prime"),
        (2, "東証スタンダード", "standard"),
        (3, "東証グロース", "growth")
    ]
    for mid, mname, msuf in markets:
        process_market(mid, mname, msuf, webhook_url)
        time.sleep(2)

if __name__ == '__main__':
    main()
