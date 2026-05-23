import datetime
import os
import re
import time
import sys
from io import StringIO
import pandas as pd
import requests
from bs4 import BeautifulSoup

def clean_numeric_string(text):
    """文字列から数字（とマイナス、小数点）だけを抽出して返すヘルパー関数"""
    cleaned = re.sub(r'[^\d\.\-]', '', text)
    return cleaned

def get_trading_date():
    """
    プログラムを実行した時間に応じて、適切な「相場の日付」を返す関数。
    深夜0時〜朝5時前までの実行であれば、日付を「前日」にする。
    """
    now = datetime.datetime.now()
    # もし朝5時前（0:00〜4:59）に実行された場合は、1日前（昨日）の日付にする
    if now.hour < 5:
        trading_date = now - datetime.timedelta(days=1)
    else:
        trading_date = now
    return trading_date.strftime("%Y%m%d")

def get_matsui_market_ranking(market_id):
    """指定された市場IDから100位までの詳細データを自動取得する関数"""
    parsed_data = []
    urls = [
        f"https://finance.matsui.co.jp/ranking-trading-top/index?market={market_id}",
        f"https://finance.matsui.co.jp/ranking-trading-top/index?market={market_id}&page=2"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }
    
    for page_idx, url in enumerate(urls):
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
            print(f"⚠️ 処理中にエラーが発生しました: {e}")
            
    return parsed_data

def process_market(market_id, market_name, file_suffix):
    """各市場のデータ取得、保存、比較を一括で行う関数"""
    print(f"\n==========================================")
    print(f" 📈 【{market_name}】売買代金ランキング 取得開始")
    print("==========================================")
    
    ranking_data = get_matsui_market_ranking(market_id)
    if not ranking_data:
        print(f"❌ {market_name} のデータ自動取得に失敗しました。")
        return
        
    df_new = pd.DataFrame(ranking_data)
    
    # 修正：深夜実行を考慮したインテリジェントな日付取得
    target_date_str = get_trading_date()
    current_filename = f"{target_date_str}_{file_suffix}.csv"
    df_new.to_csv(current_filename, index=False, encoding="utf-8-sig")
    
    print(f"✅ 【データ日付: {target_date_str}】{market_name}({len(df_new)}件)を取得・保存しました！")
    
    # 過去ファイルの自動検出
    all_files = [f for f in os.listdir('.') if re.match(r'^\d{8}_' + file_suffix + r'\.csv$', f)]
    all_files.sort()
    
    if len(all_files) < 2:
        print(f"💡 【初回確認】{market_name}のベースファイルが作成されました。明日以降、自動比較されます。")
        print(f"👇 本日の【{market_name}】データ一覧 (1位〜100位すべて表示):")
        pd.set_option('display.max_rows', 110)
        print(df_new.to_string(index=False, formatters={
            "現在値": "{:,.1f}".format, "出来高": "{:,}".format, "売買代金(百万円)": "{:,}".format
        }))
        return

    old_filename = all_files[-2]
    print(f"🔄 前回データ '{old_filename}' との順位変動を自動計算します...")
    
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
    
    print(f"\n📊 {market_name} 変動比較結果 ({old_filename} → {current_filename})")
    print("-" * 42)
    
    print(f"🛑 100位圏内から【抜けた】銘柄:")
    if removed:
        for code in sorted(removed, key=lambda x: old_ranks[x]):
            print(f"  {code}  {old_names[code]:<18} (旧: {old_ranks[code]}位)")
    else:
        print("  なし")
        
    print(f"\n✨ 100位圏内に【新しく入った】銘柄:")
    if added:
        for code in sorted(added, key=lambda x: new_ranks[x]):
            print(f"  {code}  {new_names[code]:<18} (新: {new_ranks[code]}位)")
    else:
        print("  なし")
        
    print(f"\n🔄 【維持・順位変動】の一覧 (今回の順位順):")
    if stayed:
        for code in sorted(stayed, key=lambda x: new_ranks[x]):
            o_rank = old_ranks[code]
            n_rank = new_ranks[code]
            diff = o_rank - n_rank
            diff_str = f"↑ +{diff}" if diff > 0 else (f"↓ {diff}" if diff < 0 else "→ キープ")
            print(f"  {code}  {new_names[code]:<18} : 新 {n_rank:>3}位 ← 旧 {o_rank:>3}位 ({diff_str})")
    else:
        print("  なし")

def send_to_discord(webhook_url, message):
    """結果をDiscordに送信する関数"""
    if not webhook_url:
        print("⚠️ DiscordのWebhook URLが設定されていないため、送信をスキップします。")
        return
    
    # Discordの2000文字制限対策：文字数が多い場合は1900文字ごとに分割して送信
    if len(message) > 2000:
        for i in range(0, len(message), 1900):
            payload = {"content": message[i:i+1900]}
            requests.post(webhook_url, json=payload)
            time.sleep(1)
    else:
        payload = {"content": message}
        requests.post(webhook_url, json=payload)

def main():
    # GitHubのSecretsからDiscordのURLを安全に読み込む
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    
    markets = [
        {"id": 1, "name": "東証プライム", "suffix": "prime"},
        {"id": 2, "name": "東証スタンダード", "suffix": "standard"},
        {"id": 3, "name": "東証グロース", "suffix": "growth"}
    ]
    
    print("🚀 主要3市場売買代金ランキング自動一括取得システム（深夜日付対応版）を起動します...")
    
    # 画面への出力を横取りしてテキスト（文字列）化する処理
    old_stdout = sys.stdout
    sys.stdout = mystdout = StringIO()
    
    try:
        for m in markets:
            process_market(m["id"], m["name"], m["suffix"])
        print("\n🎉 主要3市場すべてのデータ取得・処理が正常に完了しました！")
    finally:
        sys.stdout = old_stdout
    
    # 画面に出るはずだった内容をすべて変数に格納
    final_report = mystdout.getvalue()
    
    # 自分のPCのコンソールにも結果を出しつつ、Discordにも送信する
    print(final_report)
    send_to_discord(webhook_url, f"```\n{final_report}\n```")

if __name__ == '__main__':
    main()