from flask import Flask, render_template, jsonify
from qbittorrent_manager import QBittorrentManager
from proxy_manager import ProxyManager
from scheduler import Scheduler
import threading

from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Read settings from environment
qb_host = os.getenv('QBITTORRENT_HOST', 'localhost')
qb_port = int(os.getenv('QBITTORRENT_PORT', '7070'))
qb_user = os.getenv('QBITTORRENT_USERNAME')
qb_pass = os.getenv('QBITTORRENT_PASSWORD')

app = Flask(__name__)

# Initialize managers
proxy_manager = ProxyManager()
qb_manager = QBittorrentManager(
    host=qb_host, 
    port=qb_port,
    username=qb_user,
    password=qb_pass
)
scheduler = Scheduler(proxy_manager, qb_manager)

# Load proxies from JSON cache file
proxy_manager.load_proxies()

@app.route("/")
def index():
    current_proxy = qb_manager.get_current_proxy()
    return render_template("index.html", current_proxy=current_proxy)

@app.route("/proxies")
def get_proxies():
    proxies = proxy_manager.proxies
    last_update = proxy_manager.last_update_timestamp
    return jsonify(proxies=proxies, last_update=last_update)

@app.route("/set_proxy/<proxy>")
def set_proxy_route(proxy):
    success = qb_manager.set_proxy(proxy)
    status = "success" if success else "failure"
    return jsonify({"status": status, "proxy": proxy})

@app.route("/update_proxies")
def update_proxies():
    threading.Thread(target=proxy_manager.update_proxies).start()  # Update proxies in the background
    return jsonify({"status": "success"})

@app.route("/retest_proxy/<proxy>")
def retest_proxy(proxy):
    threading.Thread(target=proxy_manager.test_proxy, args=(proxy,)).start()  # Test proxy in the background
    status = proxy_manager.proxies.get(proxy, {}).get('status', 'Unknown')
    last_checked = proxy_manager.proxies.get(proxy, {}).get('last_checked', 'Never')
    return jsonify({"proxy": proxy, "status": status, "last_checked": last_checked})

@app.route("/qb_connection_status")
def qb_connection_status():
    status = qb_manager.test_current_proxy_connection()
    return jsonify({"status": status})

@app.route("/update_status")
def update_status():
    status = proxy_manager.get_status()
    return jsonify({"status": status})

@app.route("/progress")
def progress():
    return jsonify(proxy_manager.get_progress())

@app.route("/current_proxy")
def current_proxy():
    return jsonify({"current_proxy": qb_manager.get_current_proxy()})

if __name__ == "__main__":
    # Start the scheduler in a separate thread
    scheduler_thread = threading.Thread(target=scheduler.run_continuously)
    scheduler_thread.start()

    # Start the server and load the page
    app.run(host="0.0.0.0", port=4141)
