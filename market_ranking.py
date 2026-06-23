import datetime
import os
import re
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup

# --- (以下、ヘルパー関数などは既存のものを維持) ---
def clean_numeric_string(text):
    return re.sub(r'[^\d\.\-]', '', text)

def get_trading_date():
    now = datetime.datetime.now()
    if now.hour < 5:
        return (now - datetime.timedelta(days=1)).strftime("%Y%m%d")
    return now.strftime("%Y%m%d")

# --- (market_ranking.py のメインロジック) ---

def process_market(market_id, market_name, file_suffix, webhook_url):
    # 1. ランキング取得
    ranking_data = get_matsui_market_ranking(market_id)
    if not ranking_data: return
    
    # 2. 株式数データ(shares.csv)を読み込み
    try:
        shares_df = pd.read_csv("shares.csv", dtype={"コード": str})
        shares_map = dict(zip(shares_df["コード"], shares_df["発行済株式数"]))
    except:
        shares_map = {}

    df = pd.DataFrame(ranking_data)
    
    # 3. 時価総額と回転率の計算 (時価総額 = 現在値 * 発行済株式数)
    # 単位合わせ: 売買代金は百万円、時価総額も百万円単位に換算
    df["時価総額(百万円)"] = df.apply(lambda x: (x["現在値"] * shares_map.get(str(x["コード"]), 0)) / 1000000, axis=1)
    df["回転率(%)"] = (df["売買代金(百万円)"] / df["時価総額(百万円)"] * 100).round(2)

    # 4. CSV保存
    df.to_csv(f"{get_trading_date()}_{file_suffix}.csv", index=False, encoding="utf-8-sig")

    # 5. Discord通知用テキスト作成
    lines_pool = [f"📈 【{market_name}】売買代金ランキング", "=" * 35]
    
    # 基本の3情報
    for _, row in df.iterrows():
        lines_pool.append(f"{row['順位']:>3}位 {row['コード']} {row['銘柄名']}")

    # 🔥 回転率シグナル（注目枠：回転率5%以上）
    high_turnover = df[df["回転率(%)"] >= 5.0].sort_values("回転率(%)", ascending=False)
    if not high_turnover.empty:
        lines_pool.append("\n🔥【注目の大口・材料銘柄】(回転率5%超):")
        for _, row in high_turnover.head(5).iterrows():
            lines_pool.append(f"  {row['コード']} {row['銘柄名']} (回転率:{row['回転率(%)']}% / 代金:{row['売買代金(百万円)']}M)")

    # (Discord送信ロジックは前回同様)
    send_to_discord(webhook_url, lines_pool)

# (※get_matsui_market_ranking関数とsend_to_discord関数は前回のコードをそのままお使いください)
