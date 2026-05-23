import datetime
import os
import re
import time
import sys
from io import BytesIO
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

def text_to_image(lines, title_name):
    """テキストをスマホでもクッキリ読める大きな等幅画像に変換する関数"""
    bg_color = (30, 31, 34)       # Discord純正のダーク背景
    text_color = (242, 243, 245)   # クッキリ見える白文字
    
    # Linux環境(GitHub Actions)に100%入っている日本語フォントを強制指定
    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf"
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"
        
    # 文字サイズを24px（かなり大きめ）に設定して視認性を確保
    try:
        font = ImageFont.truetype(font_path, 24)
        title_font = ImageFont.truetype(font_path, 28)
    except:
        font = ImageFont.load_default()
        title_font = ImageFont.load_default()

    # 画像のサイズを「スマホで見やすい横幅」で固定計算
    # 全角スペースや数字のズレを防ぐため固定のキャンバスサイズを設定
    img_width = 1000
    line_height = 40
    total_height = (len(lines) + 2) * line_height + 40
        
    img = Image.new("RGB", (img_width, total_height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # タイトル（市場名）を描画
    draw.text((30, 20), f"■ {title_name}", fill=(88, 101, 242), font=title_font) # Discordブルーのアクセント
    
    # 各銘柄の行を描画
    y = 70
    for line in lines:
        draw.text((30, y), line, fill=text_color, font=font)
        y += line_height
        
    return img

def process_market(market_id, market_name, file_suffix, webhook_url):
    """各市場のデータ処理、保存、および25行ずつの画像分割送信"""
    ranking_data = get_matsui_market_ranking(market_id)
    if not ranking_data:
        print(f"❌ {market_name} のデータ自動取得に失敗しました。")
        return
        
    df_new = pd.DataFrame(ranking_data)
    target_date_str = get_trading_date()
    current_filename = f"{target_date_str}_{file_suffix}.csv"
    df_new.to_csv(current_filename, index=False, encoding="utf-8-sig")
    
    all_files = [f for f in os.listdir('.') if re.match(r'^\d{8}_' + file_suffix + r'\.csv$', f)]
    all_files.sort()
    
    lines_pool = []
    
    # 綺麗に幅を揃えるための文字列フォーマット（日本語幅を考慮）
    if len(all_files) < 2:
        lines_pool.append("【初回実行】ベースデータを作成しました。明日から比較します。")
        for _, row in df_new.iterrows():
            # 銘柄名を左詰めで綺麗に12文字分確保する整形
            name_padded = f"{row['銘柄名']}{' ' * (12 - len(row['銘柄名']))}"[:12]
            lines_pool.append(f"{row['順位']:>3}位  {row['コード']}  {name_padded}  現:{row['現在値']:>8,.1f}  代金:{row['売買代金(百万円)']:>7,}")
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
                name_padded = f"{old_names[code]}{' ' * (12 - len(old_names[code]))}"[:12]
                lines_pool.append(f"  {code}  {name_padded} (旧:{old_ranks[code]}位)")
        else:
            lines_pool.append("  なし")
            
        lines_pool.append("\n✨ 100位圏内に【新しく入った】銘柄:")
        if added:
            for code in sorted(added, key=lambda x: new_ranks[x]):
                name_padded = f"{new_names[code]}{' ' * (12 - len(new_names[code]))}"[:12]
                lines_pool.append(f"  {code}  {name_padded} (新:{new_ranks[code]}位)")
        else:
            lines_pool.append("  なし")
            
        lines_pool.append("\n🔄 【維持・順位変動】 (今回の順位順):")
        if stayed:
            for code in sorted(stayed, key=lambda x: new_ranks[x]):
                o_rank = old_ranks[code]
                n_rank = new_ranks[code]
                diff = o_rank - n_rank
                diff_str = f"↑ +{diff}" if diff > 0 else (f"↓ {diff}" if diff < 0 else "→ キープ")
                name_padded = f"{new_names[code]}{' ' * (12 - len(new_names[code]))}"[:12]
                lines_pool.append(f"  {code}  {name_padded} : 新{n_rank:>3}位 ← 旧{o_rank:>3}位 ({diff_str})")
        else:
            lines_pool.append("  なし")

    # 📌 ここがキモ：必ず「25行ずつ」で綺麗にぶつ切りを防いで画像化して送信
    chunk_size = 25
    total_chunks = (len(lines_pool) + chunk_size - 1) // chunk_size
    
    for i in range(0, len(lines_pool), chunk_size):
        chunk_lines = lines_pool[i:i+chunk_size]
        chunk_idx = (i // chunk_size) + 1
        
        # 画像の生成
        title_with_page = f"{market_name} ({chunk_idx}/{total_chunks})"
        img = text_to_image(chunk_lines, title_with_page)
        
        # Discordへ送信
        if webhook_url:
            arr = BytesIO()
            img.save(arr, format='PNG')
            arr.seek(0)
            files = {"file": (f"{file_suffix}_{chunk_idx}.png", arr, "image/png")}
            requests.post(webhook_url, files=files)
            time.sleep(2)

def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    
    markets = [
        {"id": 1, "name": "東証プライム", "suffix": "prime"},
        {"id": 2, "name": "東証スタンダード", "suffix": "standard"},
        {"id": 3, "name": "東証グロース", "suffix": "growth"}
    ]
    
    print("🚀 高解像度・文字崩れ対策版システムを起動します...")
    
    for m in markets:
        process_market(m["id"], m["name"], m["suffix"], webhook_url)
        time.sleep(3)

if __name__ == '__main__':
    main()
