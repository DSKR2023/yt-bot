import os
import sys
import json
import urllib.request
import xml.etree.ElementTree as ET
import requests
import time
from googleapiclient.discovery import build

# --- 金庫(Secrets)から情報を取る ---
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
CHANNEL_LIST_JSON = os.environ.get("CHANNEL_LIST")

# リストの読み込み
try:
    CHANNELS = json.loads(CHANNEL_LIST_JSON) if CHANNEL_LIST_JSON else []
except:
    CHANNELS = []

DATA_FILE = "video_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 互換性維持：古い形式（辞書のみ）なら新しい形式に変換
                if isinstance(data, dict) and "notified_ids" not in data:
                    return {"notified_ids": list(data.values())}
                return data
        except: return {"notified_ids": []}
    return {"notified_ids": []}

def save_data(notified_ids):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({"notified_ids": notified_ids}, f, indent=2, ensure_ascii=False)

def send_discord(channel_name, video_title, video_url, is_live, is_dskr):
    if is_live: header = f"🔴 **配信開始！ {channel_name}**"
    else: header = f"🎬 **動画投稿！ {channel_name}**"
    if is_dskr: header = f"🌟✨ **{channel_name} (DSKR公式)** ✨🌟\n{header}"

    video_id = video_url.split('=')[-1]
    image_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
    
    # メッセージ構築
    content = f"{header}\n**{video_title}**\n\n🎥 **本編はこちら**\n{video_url}\n\n🖼 **高画質サムネ**\n{image_url}"

    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": content})
    except:
        pass

def get_latest_video_rss(channel_id):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        with urllib.request.urlopen(url) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            entry = root.find("{http://www.w3.org/2005/Atom}entry")
            if entry:
                vid = entry.find("{http://www.youtube.com/xml/schemas/2015}videoId")
                title = entry.find("{http://www.w3.org/2005/Atom}title")
                if vid is not None:
                    return {"id": vid.text, "title": title.text if title else "No Title"}
    except:
        pass
    return None

def check_video_details(video_id):
    if not YOUTUBE_API_KEY: return None
    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        res = youtube.videos().list(part="snippet,liveStreamingDetails", id=video_id).execute()
        if res.get("items"):
            return res["items"][0]
    except:
        pass
    return None

def check_loop():
    if not CHANNELS: return
    
    history = load_data()
    notified_ids = history.get("notified_ids", [])
    
    for ch in CHANNELS:
        latest = get_latest_video_rss(ch["id"])
        if not latest:
            continue
            
        video_id = latest["id"]
        
        # すでに通知済みのIDならスキップ
        if video_id in notified_ids:
            continue

        # 詳細を取得して判定
        details = check_video_details(video_id)
        if not details:
            continue

        snippet = details["snippet"]
        # ★原因修正1: RSSのタイトルではなく、APIから取得した最新のタイトルを使う
        title = snippet.get("title", latest["title"])
        live_type = snippet.get("liveBroadcastContent", "none")
        
        should_notify = False
        is_live = False

        # 1. 配信中 (live)
        if live_type == "live":
            is_live = True
            should_notify = True
        
        # 2. 待機所 (upcoming)
        elif live_type == "upcoming":
            print(f"待機所のためスキップ(次回またチェック): {title}")
            continue # notified_idsに追加せず、次のループで再度チェックされるようにする

        # 3. 動画 or アーカイブ (none)
        else:
            # 配信のアーカイブ（過去に配信されたもの）は通知しない
            if "liveStreamingDetails" in details:
                print(f"アーカイブのためスキップ: {title}")
                # アーカイブは二度と通知したくないので、通知済みリストには入れる
                notified_ids.append(video_id)
                continue
            else:
                # 純粋な動画投稿
                is_live = False
                should_notify = True

        if should_notify:
            print(f"通知を送信: {title}")
            send_discord(ch["name"], title, f"https://www.youtube.com/watch?v={video_id}", is_live, ch.get("is_dskr", False))
            notified_ids.append(video_id)

    # 履歴が溜まりすぎないよう直近100件程度を保持
    save_data(notified_ids[-100:])

def main():
    # GitHub Actionsの制限時間があるため、ループ回数は控えめに調整（5分間隔実行なら1回でもOK）
    print("🔄 Checking YouTube Channels...")
    check_loop()

if __name__ == "__main__":
    main()
