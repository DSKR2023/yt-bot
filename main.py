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
    if CHANNEL_LIST_JSON:
        CHANNELS = json.loads(CHANNEL_LIST_JSON)
    else:
        CHANNELS = []
except:
    CHANNELS = []

DATA_FILE = "video_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}
    return {}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def send_discord(channel_name, video_title, video_url, is_live, is_dskr):
    if is_live: header = f"🔴 **配信開始！ {channel_name}**"
    else: header = f"🎬 **動画投稿！ {channel_name}**"
    if is_dskr: header = f"🌟✨ **{channel_name} (DSKR公式)** ✨🌟\n{header}"

    video_id = video_url.split('=')[-1]
    image_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
    content = f"{header}\n**{video_title}**\n\n🎥 **本編はこちら**\n{video_url}\n\n🖼 **高画質サムネ**\n{image_url}"

    try: requests.post(DISCORD_WEBHOOK_URL, json={"content": content})
    except: pass

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
                if vid is not None: return {"id": vid.text, "title": title.text if title else "No Title"}
    except: pass
    return None

def check_video_details(video_id):
    if not YOUTUBE_API_KEY: return None
    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        res = youtube.videos().list(part="snippet,liveStreamingDetails", id=video_id).execute()
        if res.get("items"): return res["items"][0]
    except: pass
    return None

def check_loop():
    if not CHANNELS: return
    
    history = load_data()
    current_data = history.copy()
    check_list = []
    
    # RSSチェック
    for ch in CHANNELS:
        latest = get_latest_video_rss(ch["id"])
        if latest:
            last_id = history.get(ch["id"])
            if latest["id"] != last_id:
                current_data[ch["id"]] = latest["id"]
                # 初回(None)はスキップ、履歴があってIDが変わった時だけチェック対象へ
                if last_id is not None:
                    check_list.append((ch, latest["id"], latest["title"]))
                else:
                    print(f"初回データ登録（通知スキップ）: {latest['title']}")

    # 詳細確認と通知
    for ch, video_id, rss_title in check_list:
        details = check_video_details(video_id)
        title = rss_title
        is_live = False
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        should_notify = False

        if details:
            snippet = details["snippet"]
            live_type = snippet.get("liveBroadcastContent", "none")
            
            # 1. 配信中 (Live) -> 通知する
            if live_type == "live":
                is_live = True
                should_notify = True
            
            # 2. 待機所 (Upcoming) -> スキップ
            elif live_type == "upcoming":
                print(f"待機所のためスキップ: {title}")
                should_notify = False
                
            # 3. それ以外 (None = 動画 または アーカイブ)
            else:
                # ★ここが重要！
                # 「liveStreamingDetails」が含まれている場合は、元配信のアーカイブなので無視する
                if "liveStreamingDetails" in details:
                    print(f"アーカイブのためスキップ: {title}")
                    should_notify = False
                else:
                    # ライブ情報がないものだけを「動画投稿」として扱う
                    is_live = False
                    should_notify = True
        
        if should_notify:
            send_discord(ch["name"], title, video_url, is_live, ch.get("is_dskr", False))

    save_data(current_data)

def main():
    print("⚡ Starting 1-minute interval loop...")
    for i in range(5):
        print(f"🔄 Check {i+1}/5")
        check_loop()
        if i < 4:
            time.sleep(60)

if __name__ == "__main__":
    main()
