import datetime
import os
import re
import time
import sys
from io import StringIO, BytesIO
import pandas as pd
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

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
    """指定された市場IDから100位までの詳細データを自動取得する関数"""
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

def text_to_image(text, title_name):
    """テキストを等幅フォントの綺麗な画像(PNG)に変換する関数"""
    # 視認性の高いダークテーマの配色
    bg_color = (43, 45, 49)     # Discord風のダークグレー
    text_color = (220, 221, 222) # 明るいグレー
    
    # Linux環境(GitHub Actions)の日本語等幅フォントパス
    font_path = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf"
        
    try:
        font = ImageFont.truetype(font_path, 16)
    except:
        font = ImageFont.load_default()

    lines = [f"=== {title_name} ==="] + text.split("\n")
    
    # 画像のサイズを計算
    max_width = 0
    total_height = 20
    
    for line in lines:
        # 簡易的な文字幅計算（全角2マス、半角1マス）
        w = sum(2 if ord(c) > 127 else 1 for c in line) * 10
        if w > max_width:
            max_width = w
        total_height += 24
        
    # 余白を持たせて土台画像を作成
    img = Image.new("RGB", (max_width + 40, total_height + 20), bg_color)
    draw = ImageDraw.Draw(img)
    
    # 文字を描画
    y = 20
    for line in lines:
        draw.text((20, y), line, fill=text_color, font=font)
        y += 24
        
    return img

def process_market(market_id, market_name, file_suffix):
    """各市場のデータ取得、保存、比較を行い、レポートテキストを返す"""
    report = []
    report.append(f"📈 【{market_name}】売買代金ランキング")
    report.append("=" * 45)
    
    ranking_data = get_matsui_market_ranking(market_id)
    if not ranking_data:
        report.append(f"❌ {market_name} のデータ自動取得に失敗しました。")
        return "\n".join(report)
        
    df_new = pd.DataFrame(ranking_data)
    target_date_str = get_trading_date()
    current_filename = f"{target_date_str}_{file_suffix}.csv"
    df_new.to_csv(current_filename, index=False, encoding="utf-8-sig")
    
    all_files = [f for f in os.listdir('.') if re.match(r'^\d{8}_' + file_suffix + r'\.csv$', f)]
    all_files.sort()
    
    if len(all_files) < 2:
        report.append(f"💡 【初回】ベースファイル作成。明日以降自動比較されます。")
        report.append(f"本日の【{market_name}】データ一覧 (1位〜100位):")
        
        # 綺麗に列を揃えるための整形フォーマット
        for _, row in df_new.iterrows():
            report.append(f"{row['順位']:>3}位  {row['コード']}  {row['銘柄名']:<14}  現:{row['現在値']:>8,.1f}  代金:{row['売買代金(百万円)']:>8,}")
        return "\n".join(report)

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
    
    report.append(f"🛑 100位圏内から【抜けた】銘柄:")
    if removed:
        for code in sorted(removed, key=lambda x: old_ranks[x]):
            report.append(f"  {code}  {old_names[code]:<14} (旧:{old_ranks[code]}位)")
    else:
        report.append("  なし")
        
    report.append(f"\n✨ 100位圏内に【新しく入った】銘柄:")
    if added:
        for code in sorted(added, key=lambda x: new_ranks[x]):
            report.append(f"  {code}  {new_names[code]:<14} (新:{new_ranks[code]}位)")
    else:
        report.append("  なし")
        
    report.append(f"\n🔄 【維持・順位変動】 (今回の順位順):")
    if stayed:
        for code in sorted(stayed, key=lambda x: new_ranks[x]):
            o_rank = old_ranks[code]
            n_rank = new_ranks[code]
            diff = o_rank - n_rank
            diff_str = f"↑ +{diff}" if diff > 0 else (f"↓ {diff}" if diff < 0 else "→ キープ")
            report.append(f"  {code}  {new_names[code]:<14} : 新{n_rank:>3}位 ← 旧{o_rank:>3}位 ({diff_str})")
    else:
        report.append("  なし")
        
    return "\n".join(report)

def send_to_discord_as_image(webhook_url, text, title_name):
    """テキストを画像化して、行単位できれいに分割してDiscordへアップロードする関数"""
    if not webhook_url:
        return
        
    # 📌 改善ポイント1: 行(改行)単位で綺麗にぶつ切りを防ぐロジック
    lines = text.split("\n")
    chunks = []
    current_chunk = []
    current_length = 0
    
    for line in lines:
        # 1ブロックあたり約1500文字(余裕を持つ)で行ごとに区切る
        if current_length + len(line) + 1 > 1500:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_length = len(line)
        else:
            current_chunk.append(line)
            current_length += len(line) + 1
            
    if current_chunk:
        chunks.append("\n".join(current_chunk))

    # 📌 改善ポイント2: 各ブロックを画像に変換してDiscordに送信
    for idx, chunk_text in enumerate(chunks):
        img = text_to_image(chunk_text, f"{title_name} ({idx+1}/{len(chunks)})")
        
        # 画像をメモリ上のバイナリデータに変換
        arr = BytesIO()
        img.save(arr, format='PNG')
        arr.seek(0)
        
        # DiscordのWebhookでファイルを送信
        files = {"file": (f"{title_name}_{idx+1}.png", arr, "image/png")}
        requests.post(webhook_url, files=files)
        time.sleep(2)

def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    
    markets = [
        {"id": 1, "name": "東証プライム", "suffix": "prime"},
        {"id": 2, "name": "東証スタンダード", "suffix": "standard"},
        {"id": 3, "name": "東証グロース", "suffix": "growth"}
    ]
    
    print("🚀 主要3市場ランキングシステムを起動（画像送信モード）...")
    
    for m in markets:
        # 各市場のテキストレポートを生成
        market_report = process_market(m["id"], m["name"], m["suffix"])
        print(market_report) # GitHub側のログ用
        
        # 画像化して送信を実行
        send_to_discord_as_image(webhook_url, market_report, m["name"])
        time.sleep(3)

if __name__ == '__main__':
    main()
