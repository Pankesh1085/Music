from flask import Flask, request, render_template, jsonify
from flask_sock import Sock
import threading
import subprocess
import logging
import queue
import os
import json
import time
import re
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
sock = Sock(app)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Configuration
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', "/media/Music")
COOKIES_FILE = os.getenv('COOKIES_FILE', "/home/server/cookies.txt")
MAX_RETRIES = 3
LOG_FILE = "logs/download.log"

# Setup
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Global state
clients = []
download_queue = queue.Queue()
current = {"url": None, "completed": None}

def is_valid_spotify_url(url):
    pattern = r'^https?://open\.spotify\.com/(album|playlist)/[a-zA-Z0-9]+(\?.*)?$'
    return re.match(pattern, url) is not None

def parse_url(url):
    if not url:
        return {"title": "Unknown", "artist": "Unknown"}
    name = url.strip('/').split('/')[-1].split('?')[0]
    title = name.replace('-', ' ').replace('%20', ' ').title()
    return {"title": title, "artist": "Unknown"}

def get_status():
    q = list(download_queue.queue)
    queue_items = [parse_url(url) for url in q]
    current_url = current['url']
    return {
        "current": parse_url(current_url) if current_url else None,
        "queue": queue_items,
        "completed": current["completed"],
        "is_downloading": bool(current_url)
    }

def worker():
    while True:
        url = download_queue.get()
        current["url"] = url
        current["completed"] = None
        
        logger.info(f"Starting download: {url}")
        success = False
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                subprocess.run([
                    "spotdl", url,
                    "--output", f"{DOWNLOAD_DIR}/{{artist}}/{{album}}/{{title}}.{{output_ext}}",
                    "--bitrate", "320k",
                    "--yt-dlp-args",
                    f"--cookies {COOKIES_FILE} --age-limit 99 --geo-bypass --no-playlist --embed-metadata"
                ], check=True)
                success = True
                break
            except subprocess.CalledProcessError:
                logger.error(f"Attempt {attempt} failed for {url}")

        current["completed"] = {
            "url": url,
            "title": parse_url(url)["title"],
            "success": success,
            "time": time.time()
        }
        current["url"] = None
        download_queue.task_done()

@sock.route('/ws')
def websocket_route(ws):
    clients.append(ws)
    try:
        ws.send(json.dumps({"type": "connection", "status": "connected"}))
        ws.send(json.dumps(get_status()))
        while True:
            if ws.receive() is None:
                break
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        if ws in clients:
            clients.remove(ws)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400
        
    url = data.get('query', '').strip()
    if not url:
        return jsonify({"error": "Missing URL"}), 400
        
    if not is_valid_spotify_url(url):
        return jsonify({"error": "Download Only Album|Playlist Spotify URL"}), 400
        
    download_queue.put(url)
    return jsonify({"status": "success", "url": url})

def broadcast_status():
    last_state = None
    while True:
        current_state = json.dumps(get_status())
        if current_state != last_state:
            for ws in clients[:]:
                try:
                    ws.send(current_state)
                except Exception:
                    clients.remove(ws)
            last_state = current_state
        time.sleep(0.5)

if __name__ == '__main__':
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=broadcast_status, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
