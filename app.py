import atexit
import os
from typing import Any, Dict

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from proxy_service import ProxyService
from settings_store import SecureSettingsStore

load_dotenv()

app = Flask(__name__)

settings_store = SecureSettingsStore(data_dir="data")
proxy_service = ProxyService(settings_store=settings_store, sources_file="sources.txt", data_dir="data")
proxy_service.start()


def _json_payload() -> Dict[str, Any]:
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    return {}


@app.errorhandler(Exception)
def api_error_handler(exc: Exception):
    if request.path.startswith("/api/"):
        if isinstance(exc, HTTPException):
            return jsonify({"ok": False, "message": exc.description}), exc.code
        return jsonify({"ok": False, "message": str(exc)}), 500
    raise exc


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    snapshot = proxy_service.get_snapshot()
    ok, current_proxy = proxy_service.current_qb_proxy()
    snapshot["qbittorrent_current_proxy"] = current_proxy
    snapshot["qbittorrent_status"] = "ok" if ok else "error"
    return jsonify(snapshot)


@app.post("/api/settings")
def api_save_settings():
    ok, saved, message = proxy_service.update_settings(_json_payload())
    status_code = 200 if ok else 400
    return jsonify({"ok": ok, "message": message, "settings": saved}), status_code


@app.post("/api/run-now")
def api_run_now():
    ok, message = proxy_service.run_now()
    status_code = 200 if ok else 409
    return jsonify({"ok": ok, "message": message}), status_code


@app.post("/api/scan/stop")
def api_stop_scan():
    ok, message = proxy_service.stop_scan()
    status_code = 200 if ok else 409
    return jsonify({"ok": ok, "message": message}), status_code


@app.post("/api/scan/resume")
def api_resume_scan():
    ok, message = proxy_service.resume_scan()
    status_code = 200 if ok else 409
    return jsonify({"ok": ok, "message": message}), status_code


@app.post("/api/scan/restart")
def api_restart_scan():
    ok, message = proxy_service.restart_scan_from_top()
    status_code = 200 if ok else 409
    return jsonify({"ok": ok, "message": message}), status_code


@app.post("/api/scan/clear-refetch")
def api_clear_refetch_scan():
    ok, message = proxy_service.clear_cache_and_refetch()
    status_code = 200 if ok else 409
    return jsonify({"ok": ok, "message": message}), status_code


@app.post("/api/proxy/apply")
def api_apply_proxy():
    payload = _json_payload()
    proxy = str(payload.get("proxy", "")).strip()
    if not proxy:
        return jsonify({"ok": False, "message": "Missing proxy value"}), 400

    ok, message = proxy_service.apply_proxy(proxy)
    status_code = 200 if ok else 400
    return jsonify({"ok": ok, "message": message}), status_code


@app.post("/api/proxy/apply-best")
def api_apply_best_proxy():
    ok, message = proxy_service.apply_best_proxy()
    status_code = 200 if ok else 400
    return jsonify({"ok": ok, "message": message}), status_code


@app.post("/api/qb/test")
def api_test_qb_connection():
    ok, details = proxy_service.test_qb_connection()
    status_code = 200 if ok else 400
    return jsonify({"ok": ok, **details}), status_code


@app.get("/api/health")
def api_health():
    return jsonify({"ok": True})


@atexit.register
def _shutdown() -> None:
    proxy_service.stop()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7272"))
    app.run(host="0.0.0.0", port=port, threaded=True)
