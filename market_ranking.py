import datetime
import os
import re
import time
import sys
import pandas as pd
import requests
from bs4 import BeautifulSoup

def clean_numeric_string(text):
    """文字列から数字（とマイナス、小数点）だけを抽出して返すヘルパー関数"""
    cleaned = re.sub(r'[^\d\.\-]', '', text)
    return cleaned

def get_trading_date():
    """深夜0時〜朝5時前までの実行であれば、日付を「前日」にする"""
    now = datetime.datetime.now()
    if now.hour < 5:
        trading_date = now - datetime.timedelta(days=1)
    else:
        trading_date = now
    return trading_date.strftime("%Y%m%d")

def get_matsui_market_ranking(market_id):
    """指定された市場IDから100位までの詳細データを自動取得する関数（CSV用）"""
    parsed_data = []
    urls = [
        f"https://finance.matsui.co.jp/ranking-trading-top/index?market={market_id}",
        f"https://finance.matsui.co.jp/ranking-trading-top/index?market={market_id}&page=2"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for url in urls:
        try:
            time.sleep(1)
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code != 200:
                continue
                
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.find("table", class_="m-table")
            if not table:
                continue
                
            rows = table.find("tbody").find_all("tr")
            for row in rows:
                tds = row.find_all("td")
                if len(tds) < 6:
                    continue
                
                rank_text = clean_numeric_string(tds[0].text.strip())
                rank = int(rank_text) if rank_text else None
                
                td_name = tds[1]
                a_tag = td_name.find("a")
                span_tag = td_name.find("span")
                if not (a_tag and span_tag):
                    continue
                    
                name = a_tag.text.strip()
                code_match = re.search(r'([A-Z0-9]{4})', span_tag.text.strip())
                code = code_match.group(1) if code_match else ""
                
                price_str = clean_numeric_string(tds[2].text.strip())
                volume_str = clean_numeric_string(tds[4].text.strip())
                trading_value_str = clean_numeric_string(tds[5].text.strip())
                
                if rank and code and name and price_str and volume_str and trading_value_str:
                    price = float(price_str) if '.' in price_str else int(price_str)
                    volume = int(volume_str)
                    trading_value = int(trading_value_str)
                    
                    parsed_data.append({
                        "順位": rank,
                        "コード": code,
                        "銘柄名": name,
                        "現在値": price,
                        "出来高": volume,
                        "売買代金(百万円)": trading_value
                    })
        except Exception as e:
            print(f"⚠️ エラー: {e}")
            
    return parsed_data

def process_market(market_id, market_name, file_suffix, webhook_url):
    """各市場のデータを取得・CSVへ全保存し、Discordへは3情報のみを綺麗な行単位でテキスト送信する"""
    ranking_data = get_matsui_market_ranking(market_id)
    if not ranking_data:
        print(f"❌ {market_name} のデータ自動取得に失敗しました。")
        return
        
    # 1. 【今まで通り】すべてのデータをCSVにしっかり保存
    df_new = pd.DataFrame(ranking_data)
    target_date_str = get_trading_date()
    current_filename = f"{target_date_str}_{file_suffix}.csv"
    df_new.to_csv(current_filename, index=False, encoding="utf-8-sig")
    
    all_files = [f for f in os.listdir('.') if re.match(r'^\d{8}_' + file_suffix + r'\.csv$', f)]
    all_files.sort()
    
    # --- 【安全追加】shares.csv から発行済株式数を読み込む（壊さないようtry-exceptで囲む） ---
    try:
        shares_df = pd.read_csv("shares.csv", dtype={"コード": str})
        shares_map = {str(c).strip(): int(s) for c, s in zip(shares_df["コード"], shares_df["発行済株式数"])}
    except Exception as e:
        print(f"⚠️ shares.csvの読み込みに失敗しました(回転率は0%になります): {e}")
        shares_map = {}

    # --- 【安全追加】回転率を計算する内部ヘルパー関数 ---
    def calculate_turnover(row):
        code_str = str(row["コード"]).strip()
        shares = shares_map.get(code_str, 0)
        if shares == 0:
            return 0.0
        # 時価総額(百万円) = 現在値 * 発行済株式数 / 1,000,000
        market_cap = (row["現在値"] * shares) / 1000000
        if market_cap <= 0:
            return 0.0
        # 回転率(%) = 売買代金(百万円) / 時価総額(百万円) * 100
        return (row["売買代金(百万円)"] / market_cap) * 100
    # ----------------------------------------------------------------------------------
    
    # Discord用のテキストを作成するプール
    lines_pool = []
    lines_pool.append(f"📈 【{market_name}】売買代金ランキング")
    lines_pool.append("=" * 35)
    
    # 2. 【改善】Discordに送るテキストは「順位・コード・銘柄名」の3つに絞る＋末尾に回転率を追加
    if len(all_files) < 2:
        lines_pool.append("💡【初回確認】明日から前日比の自動比較がスタートします。")
        for _, row in df_new.iterrows():
            turnover_val = calculate_turnover(row)
            lines_pool.append(f"{row['順位']:>3}位  {row['コード']}  {row['銘柄名']} (回転率:{turnover_val:.1f}%)")
    else:
        old_filename = all_files[-2]
        df_old = pd.read_csv(old_filename, dtype={"コード": str})
        
        old_ranks = {str(row["コード"]): int(row["順位"]) for _, row in df_old.iterrows()}
        old_names = {str(row["コード"]): row["銘柄名"] for _, row in df_old.iterrows()}
        new_ranks = {str(row["コード"]): int(row["順位"]) for _, row in df_new.iterrows()}
        new_names = {str(row["コード"]): row["銘柄名"] for _, row in df_new.iterrows()}
        
        old_set = set(old_ranks.keys())
        new_set = set(new_ranks.keys())
        
        removed = old_set - new_set
        added = new_set - old_set
        stayed = old_set & new_set
        
        lines_pool.append("🛑 100位圏内から【抜けた】銘柄:")
        if removed:
            for code in sorted(removed, key=lambda x: old_ranks[x]):
                lines_pool.append(f"  {code}  {old_names[code]} (旧:{old_ranks[code]}位)")
        else:
            lines_pool.append("  なし")
            
        lines_pool.append("\n✨ 100位圏内に【新しく入った】銘柄:")
        if added:
            for code in sorted(added, key=lambda x: new_ranks[x]):
                # 新規に入った銘柄の行を取得して回転率を出す
                matched_rows = df_new[df_new["コード"] == code]
                turnover_val = calculate_turnover(matched_rows.iloc[0]) if not matched_rows.empty else 0.0
                lines_pool.append(f"  {code}  {new_names[code]} (新:{new_ranks[code]}位 / 回転率:{turnover_val:.1f}%)")
        else:
            lines_pool.append("  なし")
            
        lines_pool.append("\n🔄 【維持・順位変動】 (今回の順位順):")
        if stayed:
            for code in sorted(stayed, key=lambda x: new_ranks[x]):
                o_rank = old_ranks[code]
                n_rank = new_ranks[code]
                diff = o_rank - n_rank
                diff_str = f"↑ +{diff}" if diff > 0 else (f"↓ {diff}" if diff < 0 else "→ キープ")
                
                # 維持した銘柄の行を取得して回転率を出す
                matched_rows = df_new[df_new["コード"] == code]
                turnover_val = calculate_turnover(matched_rows.iloc[0]) if not matched_rows.empty else 0.0
                
                lines_pool.append(f"  {code}  {new_names[code]} : 新{n_rank:>3}位 (旧:{o_rank:>3}位 {diff_str} / 回転率:{turnover_val:.1f}%)")
        else:
            lines_pool.append("  なし")

    # 3. 【徹底対策】2000文字を超えないよう「行（銘柄）の区切り」で安全に分割して送信
    if not webhook_url:
        return

    current_chunk = []
    current_length = 0
    
    for line in lines_pool:
        if current_length + len(line) + 1 > 1600:
            message = "```\n" + "\n".join(current_chunk) + "\n```"
            requests.post(webhook_url, json={"content": message})
            time.sleep(1.5)
            
            current_chunk = [line]
            current_length = len(line)
        else:
            current_chunk.append(line)
            current_length += len(line) + 1
            
    if current_chunk:
        message = "```\n" + "\n".join(current_chunk) + "\n```"
        requests.post(webhook_url, json={"content": message})
        time.sleep(1.5)

def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    
    markets = [
        {"id": 1, "name": "東証プライム", "suffix": "prime"},
        {"id": 2, "name": "東証スタンダード", "suffix": "standard"},
        {"id": 3, "name": "東証グロース", "suffix": "growth"}
    ]
    
    print("🚀 テキスト回帰・3情報スリム化システムを起動します...")
    
    for m in markets:
        process_market(m["id"], m["name"], m["suffix"], webhook_url)
        time.sleep(2)

if __name__ == '__main__':
    main()
