import schedule
import threading
import time
import logging
from proxy_manager import ProxyManager
from qbittorrent_manager import QBittorrentManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Scheduler:
    def __init__(self, proxy_manager, qb_manager):
        self.proxy_manager = proxy_manager
        self.qb_manager = qb_manager
        self.setup_tasks()

    def setup_tasks(self):
        schedule.every().day.at("20:00").do(self.update_and_test_proxies)  # 8 PM Central
        schedule.every(20).minutes.do(self.retest_proxies)
        schedule.every(5).minutes.do(self.test_qbittorrent_connection)

    def update_and_test_proxies(self):
        logging.info("Starting scheduled proxy update and testing.")
        self.proxy_manager.update_proxies()
        logging.info("Completed proxy update and testing.")

    def retest_proxies(self):
        logging.info("Retesting proxies based on last checked timestamps.")
        for proxy, details in self.proxy_manager.proxies.items():
            last_checked = details.get("last_checked")
            if last_checked:
                last_checked_time = time.strptime(last_checked, '%Y-%m-%d %H:%M:%S')
                if time.time() - time.mktime(last_checked_time) > 1200:  # 20 minutes in seconds
                    self.proxy_manager.test_proxy(proxy)

    def test_qbittorrent_connection(self):
        logging.info("Testing qBittorrent connection.")
        status = self.qb_manager.test_current_proxy_connection()
        logging.info(f"qBittorrent connection status: {status}")

    def run_continuously(self):
        def run():
            while True:
                schedule.run_pending()
                time.sleep(1)
        threading.Thread(target=run, daemon=True).start()
