import datetime
import os
import re
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

def clean_numeric_string(text):
    return re.sub(r'[^\d\.\-]', '', text)

def get_trading_date():
    now = datetime.datetime.now()
    if now.hour < 5:
        trading_date = now - datetime.timedelta(days=1)
    else:
        trading_date = now
    return trading_date.strftime("%Y%m%d")

def get_matsui_market_ranking(market_id):
    parsed_data = []
    urls = [
        f"https://finance.matsui.co.jp/ranking-trading-top/index?market={market_id}",
        f"https://finance.matsui.co.jp/ranking-trading-top/index?market={market_id}&page=2"
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for url in urls:
        try:
            time.sleep(1)
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code != 200: continue
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.find("table", class_="m-table")
            if not table: continue
            
            for row in table.find("tbody").find_all("tr"):
                tds = row.find_all("td")
                if len(tds) < 6: continue
                
                name_tag, code_tag = tds[1].find("a"), tds[1].find("span")
                if not (name_tag and code_tag): continue
                
                parsed_data.append({
                    "順位": int(clean_numeric_string(tds[0].text)),
                    "コード": re.search(r'\d{4}', code_tag.text).group(),
                    "銘柄名": name_tag.text.strip(),
                    "現在値": float(clean_numeric_string(tds[2].text)),
                    "売買代金(百万円)": int(clean_numeric_string(tds[5].text))
                })
        except: continue
    return parsed_data

def process_market(market_id, market_name, file_suffix, webhook_url):
    # 1. データ取得
    ranking_data = get_matsui_market_ranking(market_id)
    if not ranking_data: return
    
    # 2. 株式数データの読み込み
    try:
        shares_df = pd.read_csv("shares.csv", dtype={"コード": str})
        shares_map = {str(c).strip(): int(s) for c, s in zip(shares_df["コード"], shares_df["発行済株式数"])}
    except: shares_map = {}
        
    df_new = pd.DataFrame(ranking_data)
    
    # 回転率を計算する関数
    def get_turnover(row):
        shares = shares_map.get(str(row["コード"]).strip(), 0)
        if shares == 0: return 0
        market_cap = (row["現在値"] * shares) / 1000000
        return (row["売買代金(百万円)"] / market_cap * 100) if market_cap > 0 else 0

    # CSV保存
    df_new.to_csv(f"{get_trading_date()}_{file_suffix}.csv", index=False, encoding="utf-8-sig")
    
    all_files = sorted([f for f in os.listdir('.') if re.match(r'^\d{8}_' + file_suffix + r'\.csv$', f)])
    
    lines_pool = [f"📈 【{market_name}】売買代金ランキング", "=" * 35]
    
    if len(all_files) < 2:
        for _, row in df_new.iterrows():
            rot = get_turnover(row)
            lines_pool.append(f"{row['順位']:>3}位  {row['コード']}  {row['銘柄名']} (回転率:{rot:.1f}%)")
    else:
        df_old = pd.read_csv(all_files[-2], dtype={"コード": str})
        old_ranks = {str(r["コード"]): int(r["順位"]) for _, r in df_old.iterrows()}
        old_names = {str(r["コード"]): r["銘柄名"] for _, r in df_old.iterrows()}
        
        # 比較ロジック
        removed = set(old_ranks.keys()) - set(df_new["コード"].astype(str))
        added = set(df_new["コード"].astype(str)) - set(old_ranks.keys())
        
        lines_pool.append("🛑 100位圏内から【抜けた】銘柄:")
        for c in sorted(removed, key=lambda x: old_ranks[x]): lines_pool.append(f"  {c}  {old_names[c]} (旧:{old_ranks[c]}位)")
        
        lines_pool.append("\n✨ 100位圏内に【新しく入った】銘柄:")
        for _, r in df_new[df_new["コード"].astype(str).isin(added)].iterrows(): lines_pool.append(f"  {r['コード']}  {r['銘柄名']} (新:{r['順位']}位)")
            
        lines_pool.append("\n🔄 【維持・順位変動】 (回転率:売買代金÷時価総額):")
        for _, r in df_new.iterrows():
            code = str(r["コード"])
            rot = get_turnover(r)
            if code in old_ranks:
                diff = old_ranks[code] - r["順位"]
                d_str = f"↑ +{diff}" if diff > 0 else (f"↓ {abs(diff)}" if diff < 0 else "→ キープ")
                lines_pool.append(f"  {code}  {r['銘柄名']} : 新{r['順位']:>3}位 (旧:{old_ranks[code]:>3}位 {d_str} / 回転率:{rot:.1f}%)")
            else:
                lines_pool.append(f"  {code}  {r['銘柄名']} : 新{r['順位']:>3}位 (新規 / 回転率:{rot:.1f}%)")

    # Discord送信
    if webhook_url:
        for i in range(0, len(lines_pool), 40):
            message = "
http://googleusercontent.com/immersive_entry_chip/0

### この後のアクション
1. GitHubの `market_ranking.py` を上記コードで上書きしてください。
2. そのまま GitHub Actions で `Run workflow` を実行すれば、今まで通りの順位比較フォーマットに、回転率が追加された状態で通知が届くはずです。

もしこれで動けば、懸案だった「順位比較」と「回転率分析」が両立することになります。確認してみてください！
