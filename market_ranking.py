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
    # 40行ずつに分割して送信するロジックを修正
    for i in range(0, len(lines), 40):
        # f-stringではなく、連結して文字列を完結させる
        chunk = lines[i:i+40]
        message = "```\n" + "\n".join(chunk) + "\n```"
        requests.post(webhook_url, json={"content": message})
        time.sleep(1.5)

def process_market(market_id, market_name, file_suffix, webhook_url):
    df_new = pd.DataFrame(get_matsui_market_ranking(market_id))
    if df_new.empty: return
    
    try:
        shares_df = pd.read_csv("shares.csv", dtype={"コード": str})
        shares_map = {str(c).strip(): int(s) for c, s in zip(shares_df["コード"], shares_df["発行済株式数"])}
    except: shares_map = {}
    
    # 回転率計算
    df_new["回転率"] = df_new.apply(lambda r: (r["売買代金(百万円)"] / ((r["現在値"] * shares_map.get(str(r["コード"]), 0))/1000000) * 100) if shares_map.get(str(r["コード"])) else 0, axis=1)
    df_new.to_csv(f"{get_trading_date()}_{file_suffix}.csv", index=False, encoding="utf-8-sig")

    all_files = sorted([f for f in os.listdir('.') if re.match(r'^\d{8}_' + file_suffix + r'\.csv$', f)])
    lines = [f"📈 【{market_name}】売買代金ランキング", "=" * 35]

    if len(all_files) >= 2:
        df_old = pd.read_csv(all_files[-2], dtype={"コード": str})
        old_ranks = {str(r["コード"]): int(r["順位"]) for _, r in df_old.iterrows()}
        old_names = {str(r["コード"]): r["銘柄名"] for _, r in df_old.iterrows()}
        
        removed = set(old_ranks.keys()) - set(df_new["コード"].astype(str))
        if removed:
            lines.append("\n🛑 100位圏内から【抜けた】銘柄:")
            for c in sorted(removed, key=lambda x: old_ranks[x]): lines.append(f"  {c}  {old_names[c]} (旧:{old_ranks[c]}位)")
        
        added = set(df_new["コード"].astype(str)) - set(old_ranks.keys())
        if added:
            lines.append("\n✨ 100位圏内に【新しく入った】銘柄:")
            for _, r in df_new[df_new["コード"].astype(str).isin(added)].iterrows(): lines.append(f"  {r['コード']}  {r['銘柄名']} (新:{r['順位']}位)")
            
        lines.append("\n🔄 【維持・順位変動】:")
        for _, r in df_new.iterrows():
            c = str(r["コード"])
            if c in old_ranks:
                diff = old_ranks[c] - r["順位"]
                d_str = f"↑ +{diff}" if diff > 0 else (f"↓ {abs(diff)}" if diff < 0 else "→ キープ")
                lines.append(f"  {c}  {r['銘柄名']} : 新{r['順位']:>3}位 (旧:{old_ranks[c]:>3}位 {d_str})")
    
    high_turnover = df_new[df_new["回転率"] >= 5.0].sort_values("回転率", ascending=False)
    if not high_turnover.empty:
        lines.append("\n🔥【注目の大口・材料銘柄】(回転率5%超):")
        for _, r in high_turnover.head(5).iterrows():
            lines.append(f"  {r['コード']} {r['銘柄名']} ({r['回転率']:.1f}% / {r['売買代金(百万円)']}M)")

    send_to_discord(webhook_url, lines)

def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    for mid, mname, msuf in [(1, "東証プライム", "prime"), (2, "東証スタンダード", "standard"), (3, "東証グロース", "growth")]:
        process_market(mid, mname, msuf, webhook_url)
        time.sleep(2)

if __name__ == '__main__':
    main()
