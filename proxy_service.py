import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from proxy_checks import ProxyTester, normalize_proxy_line, utc_now_iso
from qbittorrent_client import QBittorrentClient
from settings_store import SecureSettingsStore, sanitize_settings


def _iso_to_epoch(value: Optional[str]) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def _default_proxy_record(now_iso: str) -> Dict[str, Any]:
    return {
        "sources": [],
        "first_seen": now_iso,
        "last_seen": now_iso,
        "last_tested": "",
        "checks": {
            "tcp_connect": False,
            "socks5_handshake": False,
            "tracker_tcp": False,
            "tracker_udp": False,
        },
        "passed": False,
        "latency_ms": None,
        "failure_reason": "never tested",
    }


def _default_source_meta(url: str, now_iso: str) -> Dict[str, Any]:
    return {
        "url": url,
        "last_fetch": now_iso,
        "fetched_count": 0,
        "valid_count": 0,
        "passing_count": 0,
        "error": "",
    }


def _default_state() -> Dict[str, Any]:
    return {
        "proxies": {},
        "sources": {},
        "service": {
            "status": "idle",
            "stage": "idle",
            "reason": "",
            "last_run_started": "",
            "last_run_finished": "",
            "next_run_at": "",
            "last_error": "",
            "progress": {"tested": 0, "total": 0},
        },
        "scan": {
            "plan": [],
            "cursor": 0,
            "total": 0,
            "paused": False,
            "last_source_refresh": "",
            "current_proxy": "",
        },
        "auto_apply": {
            "last_applied_proxy": "",
            "last_applied_at": "",
            "last_error": "",
        },
    }


class ProxyService:
    def __init__(
        self,
        settings_store: SecureSettingsStore,
        sources_file: str = "sources.txt",
        data_dir: str = "data",
    ) -> None:
        self.settings_store = settings_store
        self.sources_file = Path(sources_file)

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / "proxy_state.json"

        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.scan_stop_event = threading.Event()
        self.scheduler_thread: Optional[threading.Thread] = None
        self.update_thread: Optional[threading.Thread] = None

        self.state: Dict[str, Any] = self._load_state()

    def start(self) -> None:
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return

        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()

        with self.lock:
            scan = self.state.get("scan", {})
            has_remaining = int(scan.get("cursor", 0)) < int(scan.get("total", 0))
            paused = bool(scan.get("paused", False))
            has_finished = bool(self.state.get("service", {}).get("last_run_finished"))

        if has_remaining and not paused:
            self.trigger_update("startup-resume", refresh_sources=False, restart_from_top=False)
        elif not has_finished:
            self.trigger_update("startup", refresh_sources=True, restart_from_top=True)

    def stop(self) -> None:
        self.stop_event.set()
        self.scan_stop_event.set()
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=3)

    def _load_state(self) -> Dict[str, Any]:
        defaults = _default_state()
        if not self.state_path.exists():
            return defaults

        try:
            loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                return defaults

            merged = _default_state()
            if isinstance(loaded.get("proxies"), dict):
                merged["proxies"] = loaded["proxies"]
            if isinstance(loaded.get("sources"), dict):
                merged["sources"] = loaded["sources"]
            if isinstance(loaded.get("service"), dict):
                merged["service"].update(loaded["service"])
            if isinstance(loaded.get("scan"), dict):
                merged["scan"].update(loaded["scan"])
            if isinstance(loaded.get("auto_apply"), dict):
                merged["auto_apply"].update(loaded["auto_apply"])

            scan_plan = merged["scan"].get("plan", [])
            if not isinstance(scan_plan, list):
                scan_plan = []
            scan_plan = [str(item).strip() for item in scan_plan if str(item).strip()]
            merged["scan"]["plan"] = scan_plan
            merged["scan"]["total"] = len(scan_plan)

            cursor = int(merged["scan"].get("cursor", 0) or 0)
            merged["scan"]["cursor"] = max(0, min(cursor, len(scan_plan)))

            if merged.get("service", {}).get("status") == "running":
                merged["service"]["status"] = "idle"
                merged["service"]["stage"] = "idle"
                merged["service"]["last_error"] = "Previous run interrupted; you can resume scan"

            return merged
        except (OSError, ValueError, json.JSONDecodeError):
            return defaults

    def _save_state_locked(self) -> None:
        temp_path = self.state_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(self.state, sort_keys=True), encoding="utf-8")
        temp_path.replace(self.state_path)

    def _load_sources(self) -> List[str]:
        if not self.sources_file.exists():
            return []

        sources: List[str] = []
        for line in self.sources_file.read_text(encoding="utf-8").splitlines():
            item = line.strip()
            if item and not item.startswith("#"):
                sources.append(item)
        return sources

    def _scheduler_loop(self) -> None:
        while not self.stop_event.wait(5):
            settings = self.settings_store.load()
            service_cfg = settings.get("service", {})
            interval = int(service_cfg.get("scan_interval_minutes", 30))
            now_epoch = time.time()

            with self.lock:
                running = self.update_thread is not None and self.update_thread.is_alive()
                scan = self.state.get("scan", {})
                paused = bool(scan.get("paused", False))
                has_remaining = int(scan.get("cursor", 0)) < int(scan.get("total", 0))
                last_finished_epoch = _iso_to_epoch(self.state.get("service", {}).get("last_run_finished"))

            if not running and not paused and has_remaining:
                self.trigger_update("scheduled-resume", refresh_sources=False, restart_from_top=False)
            elif not running and not paused and (last_finished_epoch == 0.0 or now_epoch >= last_finished_epoch + interval * 60):
                self.trigger_update("scheduled", refresh_sources=True, restart_from_top=True)

            self._auto_apply_if_due(settings)

    def trigger_update(
        self,
        reason: str = "manual",
        refresh_sources: bool = True,
        restart_from_top: bool = False,
        clear_cache: bool = False,
    ) -> Tuple[bool, str]:
        with self.lock:
            if self.update_thread and self.update_thread.is_alive():
                return False, "Scan already running"

            self.scan_stop_event.clear()
            self.update_thread = threading.Thread(
                target=self._run_update_cycle,
                args=(reason, refresh_sources, restart_from_top, clear_cache),
                daemon=True,
            )
            self.update_thread.start()
            return True, "Scan started"

    def run_now(self) -> Tuple[bool, str]:
        with self.lock:
            scan = self.state.get("scan", {})
            has_remaining = int(scan.get("cursor", 0)) < int(scan.get("total", 0))
            self.state["scan"]["paused"] = False
            self._save_state_locked()

        if has_remaining:
            return self.trigger_update("manual-resume", refresh_sources=False, restart_from_top=False)
        return self.trigger_update("manual-refresh", refresh_sources=True, restart_from_top=True)

    def stop_scan(self) -> Tuple[bool, str]:
        with self.lock:
            running = self.update_thread is not None and self.update_thread.is_alive()
            self.state["scan"]["paused"] = True

            if running:
                self.scan_stop_event.set()
                self.state["service"]["stage"] = "stopping"
                self.state["service"]["reason"] = "stop requested"
                self._save_state_locked()
                return True, "Stop requested"

            self.state["service"]["status"] = "idle"
            self.state["service"]["stage"] = "paused"
            self.state["service"]["reason"] = "paused"
            self.state["service"]["last_run_finished"] = utc_now_iso()
            self._save_state_locked()
            return True, "Scan paused"

    def resume_scan(self) -> Tuple[bool, str]:
        with self.lock:
            self.state["scan"]["paused"] = False
            scan = self.state.get("scan", {})
            has_remaining = int(scan.get("cursor", 0)) < int(scan.get("total", 0))
            self._save_state_locked()

        if has_remaining:
            return self.trigger_update("manual-resume", refresh_sources=False, restart_from_top=False)
        return self.trigger_update("manual-resume-refresh", refresh_sources=True, restart_from_top=True)

    def restart_scan_from_top(self) -> Tuple[bool, str]:
        with self.lock:
            if self.update_thread and self.update_thread.is_alive():
                return False, "Scan is running; stop it first"

            self.state["scan"]["paused"] = False
            has_plan = len(self.state["scan"].get("plan", [])) > 0
            self.state["scan"]["cursor"] = 0
            self.state["service"]["progress"] = {
                "tested": 0,
                "total": int(self.state["scan"].get("total", 0)),
            }
            self._save_state_locked()

        if has_plan:
            return self.trigger_update("manual-restart", refresh_sources=False, restart_from_top=True)
        return self.trigger_update("manual-restart-refresh", refresh_sources=True, restart_from_top=True)

    def clear_cache_and_refetch(self) -> Tuple[bool, str]:
        with self.lock:
            if self.update_thread and self.update_thread.is_alive():
                return False, "Scan is running; stop it first"

        return self.trigger_update("manual-clear-refetch", refresh_sources=True, restart_from_top=True, clear_cache=True)

    def _reset_cache_locked(self) -> None:
        defaults = _default_state()
        self.state["proxies"] = defaults["proxies"]
        self.state["sources"] = defaults["sources"]
        self.state["scan"] = defaults["scan"]
        self.state["service"]["progress"] = {"tested": 0, "total": 0}
        self.state["service"]["last_error"] = ""

    def _fetch_sources(self, source_timeout: int, now_iso: str) -> Tuple[Dict[str, Set[str]], Dict[str, Dict[str, Any]]]:
        sources = self._load_sources()
        source_meta = {url: _default_source_meta(url, now_iso) for url in sources}
        found_by_proxy: Dict[str, Set[str]] = {}

        session = requests.Session()
        for source_url in sources:
            try:
                response = session.get(source_url, timeout=source_timeout)
                response.raise_for_status()
                body = response.text

                rows = body.splitlines()
                source_meta[source_url]["fetched_count"] = len(rows)

                valid_count = 0
                for line in rows:
                    proxy = normalize_proxy_line(line)
                    if not proxy:
                        continue
                    valid_count += 1
                    found_by_proxy.setdefault(proxy, set()).add(source_url)

                source_meta[source_url]["valid_count"] = valid_count
            except requests.RequestException as exc:
                source_meta[source_url]["error"] = str(exc)

        return found_by_proxy, source_meta

    def _merge_found_proxies_locked(self, found_by_proxy: Dict[str, Set[str]], now_iso: str) -> None:
        for proxy, source_set in found_by_proxy.items():
            record = self.state["proxies"].get(proxy)
            if not record:
                record = _default_proxy_record(now_iso)

            sources_union = set(record.get("sources", [])) | source_set
            record["sources"] = sorted(sources_union)
            record["last_seen"] = now_iso
            self.state["proxies"][proxy] = record

    def _refresh_scan_plan_locked(self, found_by_proxy: Dict[str, Set[str]], restart_from_top: bool, now_iso: str) -> None:
        scan = self.state["scan"]
        current_plan = scan.get("plan", [])
        if not isinstance(current_plan, list):
            current_plan = []

        current_plan = [str(item).strip() for item in current_plan if str(item).strip()]
        found_list = sorted(found_by_proxy.keys())

        if restart_from_top or not current_plan:
            new_plan = found_list
            new_cursor = 0
        else:
            current_set = set(current_plan)
            additions = [proxy for proxy in found_list if proxy not in current_set]
            new_plan = current_plan + additions
            old_cursor = int(scan.get("cursor", 0) or 0)
            new_cursor = min(old_cursor, len(new_plan))

        scan["plan"] = new_plan
        scan["total"] = len(new_plan)
        scan["cursor"] = 0 if restart_from_top else new_cursor
        scan["paused"] = False
        scan["last_source_refresh"] = now_iso
        scan["current_proxy"] = ""
        self.state["service"]["progress"] = {
            "tested": scan["cursor"],
            "total": scan["total"],
        }

    def _ensure_scan_plan_locked(self, restart_from_top: bool) -> None:
        scan = self.state["scan"]
        plan = scan.get("plan", [])
        if not isinstance(plan, list):
            plan = []

        plan = [str(item).strip() for item in plan if str(item).strip()]
        if not plan:
            plan = sorted(self.state["proxies"].keys())

        scan["plan"] = plan
        scan["total"] = len(plan)

        cursor = int(scan.get("cursor", 0) or 0)
        if restart_from_top:
            cursor = 0
        scan["cursor"] = max(0, min(cursor, scan["total"]))
        scan["paused"] = False
        scan["current_proxy"] = ""

        self.state["service"]["progress"] = {
            "tested": scan["cursor"],
            "total": scan["total"],
        }

    def _timed_out_result(self) -> Dict[str, Any]:
        return {
            "checks": {
                "tcp_connect": False,
                "socks5_handshake": False,
                "tracker_tcp": False,
                "tracker_udp": False,
            },
            "passed": False,
            "latency_ms": None,
            "failure_reason": "check timed out",
            "checked_at": utc_now_iso(),
        }

    def _error_result(self, exc: Exception) -> Dict[str, Any]:
        return {
            "checks": {
                "tcp_connect": False,
                "socks5_handshake": False,
                "tracker_tcp": False,
                "tracker_udp": False,
            },
            "passed": False,
            "latency_ms": None,
            "failure_reason": f"internal tester error: {exc}",
            "checked_at": utc_now_iso(),
        }

    def _test_batch(
        self,
        batch: List[str],
        tester: ProxyTester,
        max_workers: int,
        timeout_seconds: int,
    ) -> Tuple[Dict[str, Dict[str, Any]], int]:
        if not batch:
            return {}, 0

        workers = max(1, min(max_workers, len(batch)))
        pool = ThreadPoolExecutor(max_workers=workers)
        try:
            futures = {pool.submit(tester.test, proxy): proxy for proxy in batch}
            batch_timeout = max(15, (timeout_seconds + 2) * 2)
            done, not_done = wait(set(futures.keys()), timeout=batch_timeout)

            results: Dict[str, Dict[str, Any]] = {}
            for future in done:
                proxy = futures[future]
                try:
                    results[proxy] = future.result()
                except Exception as exc:
                    results[proxy] = self._error_result(exc)

            timed_out_count = 0
            for future in not_done:
                proxy = futures[future]
                future.cancel()
                timed_out_count += 1
                results[proxy] = self._timed_out_result()

            return results, timed_out_count
        finally:
            # Wait for worker threads to exit to avoid descriptor/thread leaks.
            pool.shutdown(wait=True, cancel_futures=True)

    def _apply_batch_results_locked(self, batch_results: Dict[str, Dict[str, Any]], now_iso: str) -> None:
        for proxy, result in batch_results.items():
            record = self.state["proxies"].get(proxy, _default_proxy_record(now_iso))
            record["checks"] = result["checks"]
            record["passed"] = result["passed"]
            record["latency_ms"] = result["latency_ms"]
            record["failure_reason"] = result["failure_reason"]
            record["last_tested"] = result["checked_at"]
            self.state["proxies"][proxy] = record

    def _set_paused_locked(self, reason: str) -> None:
        scan = self.state["scan"]
        scan["paused"] = True
        scan["current_proxy"] = ""

        self.state["service"].update(
            {
                "status": "idle",
                "stage": "paused",
                "reason": reason,
                "last_run_finished": utc_now_iso(),
                "progress": {
                    "tested": int(scan.get("cursor", 0)),
                    "total": int(scan.get("total", 0)),
                },
            }
        )

    def _run_update_cycle(
        self,
        reason: str,
        refresh_sources: bool,
        restart_from_top: bool,
        clear_cache: bool,
    ) -> None:
        settings = self.settings_store.load()
        service_cfg = settings.get("service", {})

        source_timeout = int(service_cfg.get("source_timeout_seconds", 20))
        timeout_seconds = int(service_cfg.get("connect_timeout_seconds", 7))
        max_workers = int(service_cfg.get("max_workers", 50))

        now_iso = utc_now_iso()

        with self.lock:
            if clear_cache:
                self._reset_cache_locked()

            self.state["scan"]["paused"] = False
            self.state["service"].update(
                {
                    "status": "running",
                    "stage": "fetching" if refresh_sources else "testing",
                    "reason": reason,
                    "last_run_started": now_iso,
                    "last_error": "",
                }
            )
            self._save_state_locked()

        source_meta: Optional[Dict[str, Dict[str, Any]]] = None

        try:
            if refresh_sources:
                found_by_proxy, source_meta = self._fetch_sources(source_timeout=source_timeout, now_iso=now_iso)

                with self.lock:
                    self.state["service"]["stage"] = "merging"
                    self._merge_found_proxies_locked(found_by_proxy, now_iso)
                    self._refresh_scan_plan_locked(found_by_proxy, restart_from_top, now_iso)
                    self.state["service"]["stage"] = "testing"
                    self._save_state_locked()
            else:
                with self.lock:
                    self._ensure_scan_plan_locked(restart_from_top=restart_from_top)
                    self.state["service"]["stage"] = "testing"
                    self._save_state_locked()

            tester = ProxyTester(timeout_seconds=timeout_seconds)

            while True:
                with self.lock:
                    scan = self.state["scan"]
                    cursor = int(scan.get("cursor", 0))
                    total = int(scan.get("total", 0))

                    if cursor >= total:
                        break

                    if self.scan_stop_event.is_set():
                        self._set_paused_locked("stopped by user")
                        self._refresh_next_run(settings)
                        self._save_state_locked()
                        return

                    plan = scan.get("plan", [])
                    if not isinstance(plan, list):
                        plan = []

                    batch_size = max(1, max_workers)
                    batch = plan[cursor: cursor + batch_size]
                    scan["current_proxy"] = batch[0] if batch else ""

                if not batch:
                    break

                batch_results, timed_out = self._test_batch(
                    batch=batch,
                    tester=tester,
                    max_workers=max_workers,
                    timeout_seconds=timeout_seconds,
                )

                with self.lock:
                    self._apply_batch_results_locked(batch_results, now_iso)

                    new_cursor = int(self.state["scan"].get("cursor", 0)) + len(batch)
                    total_after = int(self.state["scan"].get("total", 0))
                    self.state["scan"]["cursor"] = min(new_cursor, total_after)
                    self.state["service"]["progress"] = {
                        "tested": int(self.state["scan"]["cursor"]),
                        "total": total_after,
                    }
                    self.state["scan"]["current_proxy"] = ""

                    if timed_out > 0:
                        self.state["service"]["last_error"] = f"Batch timeout: {timed_out} proxies marked failed"

                    self._save_state_locked()

            self._refresh_source_stats(source_meta)
            self._refresh_next_run(settings)

            with self.lock:
                total_done = int(self.state["scan"].get("total", 0))
                self.state["scan"]["cursor"] = total_done
                self.state["scan"]["paused"] = False
                self.state["scan"]["current_proxy"] = ""
                self.state["service"].update(
                    {
                        "status": "idle",
                        "stage": "idle",
                        "last_run_finished": utc_now_iso(),
                        "progress": {"tested": total_done, "total": total_done},
                    }
                )
                self._save_state_locked()

            self._auto_apply_if_due(settings)

        except Exception as exc:
            with self.lock:
                self.state["scan"]["current_proxy"] = ""
                self.state["service"].update(
                    {
                        "status": "idle",
                        "stage": "idle",
                        "last_error": str(exc),
                        "last_run_finished": utc_now_iso(),
                    }
                )
                self._refresh_next_run(settings)
                self._save_state_locked()

    def _refresh_source_stats(self, source_meta: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        with self.lock:
            if source_meta:
                for source_url, meta in source_meta.items():
                    merged_meta = _default_source_meta(source_url, meta.get("last_fetch", utc_now_iso()))
                    merged_meta.update(meta)
                    self.state["sources"][source_url] = merged_meta

            source_pass_counts: Dict[str, int] = {}
            for record in self.state["proxies"].values():
                if not record.get("passed"):
                    continue
                for source_url in record.get("sources", []):
                    source_pass_counts[source_url] = source_pass_counts.get(source_url, 0) + 1

            all_sources = set(self.state["sources"].keys()) | set(source_pass_counts.keys())
            for source_url in all_sources:
                meta = self.state["sources"].get(source_url, _default_source_meta(source_url, utc_now_iso()))
                meta["passing_count"] = source_pass_counts.get(source_url, 0)
                self.state["sources"][source_url] = meta

            self._save_state_locked()

    def _refresh_next_run(self, settings: Dict[str, Any]) -> None:
        interval = int(settings.get("service", {}).get("scan_interval_minutes", 30))
        next_run_iso = datetime.fromtimestamp(time.time() + interval * 60, tz=timezone.utc).replace(microsecond=0).isoformat()
        with self.lock:
            self.state["service"]["next_run_at"] = next_run_iso

    def _best_proxy_locked(self) -> Optional[str]:
        candidates: List[Tuple[str, Dict[str, Any]]] = [
            (proxy, record)
            for proxy, record in self.state["proxies"].items()
            if record.get("passed")
        ]
        if not candidates:
            return None

        candidates.sort(
            key=lambda item: (
                item[1].get("latency_ms") is None,
                item[1].get("latency_ms") if item[1].get("latency_ms") is not None else 10**9,
                -len(item[1].get("sources", [])),
                -_iso_to_epoch(item[1].get("last_tested")),
            )
        )
        return candidates[0][0]

    def _build_qb_client(self) -> QBittorrentClient:
        settings = self.settings_store.load()
        qb = settings.get("qbittorrent", {})
        return QBittorrentClient(
            host=str(qb.get("host", "127.0.0.1")),
            port=int(qb.get("port", 8080)),
            username=str(qb.get("username", "")),
            password=str(qb.get("password", "")),
        )

    def apply_proxy(self, proxy: str) -> Tuple[bool, str]:
        client = self._build_qb_client()

        ok, message = client.set_socks5_proxy(proxy)
        with self.lock:
            if ok:
                self.state["auto_apply"]["last_applied_proxy"] = proxy
                self.state["auto_apply"]["last_applied_at"] = utc_now_iso()
                self.state["auto_apply"]["last_error"] = ""
            else:
                self.state["auto_apply"]["last_error"] = message
            self._save_state_locked()

        return ok, message

    def apply_best_proxy(self) -> Tuple[bool, str]:
        with self.lock:
            proxy = self._best_proxy_locked()

        if not proxy:
            return False, "No fully passed proxies available"

        return self.apply_proxy(proxy)

    def _auto_apply_if_due(self, settings: Dict[str, Any]) -> None:
        auto_cfg = settings.get("auto_apply", {})
        if not auto_cfg.get("enabled", False):
            return

        interval_minutes = int(auto_cfg.get("interval_minutes", 60))
        now_epoch = time.time()

        with self.lock:
            last_applied_epoch = _iso_to_epoch(self.state["auto_apply"].get("last_applied_at"))
            running = self.update_thread is not None and self.update_thread.is_alive()
        if running:
            return

        if last_applied_epoch and now_epoch < last_applied_epoch + interval_minutes * 60:
            return

        ok, message = self.apply_best_proxy()
        if not ok:
            with self.lock:
                self.state["auto_apply"]["last_error"] = message
                self._save_state_locked()

    def current_qb_proxy(self) -> Tuple[bool, str]:
        client = self._build_qb_client()
        return client.current_proxy()

    def test_qb_connection(self) -> Tuple[bool, Dict[str, str]]:
        client = self._build_qb_client()
        return client.test_connection()

    def update_settings(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
        current = self.settings_store.load()
        updates: Dict[str, Any] = {}

        try:
            if "qbittorrent" in payload and isinstance(payload["qbittorrent"], dict):
                incoming_qb = payload["qbittorrent"]
                current_qb = current.get("qbittorrent", {})
                qb_updates: Dict[str, Any] = {}

                host = str(incoming_qb.get("host", current_qb.get("host", "127.0.0.1"))).strip()
                port = self._bounded_int(incoming_qb.get("port", current_qb.get("port", 8080)), 1, 65535)
                username = str(incoming_qb.get("username", current_qb.get("username", ""))).strip()

                password = incoming_qb.get("password")
                if isinstance(password, str):
                    qb_updates["password"] = password if password != "" else current_qb.get("password", "")

                qb_updates["host"] = host or "127.0.0.1"
                qb_updates["port"] = port
                qb_updates["username"] = username
                updates["qbittorrent"] = qb_updates

            if "service" in payload and isinstance(payload["service"], dict):
                incoming_service = payload["service"]
                current_service = current.get("service", {})
                updates["service"] = {
                    "scan_interval_minutes": self._bounded_int(
                        incoming_service.get("scan_interval_minutes", current_service.get("scan_interval_minutes", 30)),
                        1,
                        1440,
                    ),
                    "retest_after_minutes": self._bounded_int(
                        incoming_service.get("retest_after_minutes", current_service.get("retest_after_minutes", 180)),
                        1,
                        10080,
                    ),
                    "max_workers": self._bounded_int(
                        incoming_service.get("max_workers", current_service.get("max_workers", 50)),
                        1,
                        300,
                    ),
                    "connect_timeout_seconds": self._bounded_int(
                        incoming_service.get("connect_timeout_seconds", current_service.get("connect_timeout_seconds", 7)),
                        1,
                        60,
                    ),
                    "source_timeout_seconds": self._bounded_int(
                        incoming_service.get("source_timeout_seconds", current_service.get("source_timeout_seconds", 20)),
                        1,
                        120,
                    ),
                }

            if "auto_apply" in payload and isinstance(payload["auto_apply"], dict):
                incoming_auto = payload["auto_apply"]
                current_auto = current.get("auto_apply", {})
                updates["auto_apply"] = {
                    "enabled": bool(incoming_auto.get("enabled", current_auto.get("enabled", False))),
                    "interval_minutes": self._bounded_int(
                        incoming_auto.get("interval_minutes", current_auto.get("interval_minutes", 60)),
                        1,
                        1440,
                    ),
                }

            saved = self.settings_store.save(updates)
            self._refresh_next_run(saved)
            with self.lock:
                self._save_state_locked()
            return True, sanitize_settings(saved), "Settings saved"
        except ValueError as exc:
            return False, sanitize_settings(current), str(exc)

    @staticmethod
    def _bounded_int(value: Any, min_value: int, max_value: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"Expected integer value, got: {value}")

        if parsed < min_value or parsed > max_value:
            raise ValueError(f"Value out of bounds ({min_value}-{max_value}): {parsed}")
        return parsed

    def get_snapshot(self, proxy_limit: int = 300, source_limit: int = 200) -> Dict[str, Any]:
        settings = sanitize_settings(self.settings_store.load())

        with self.lock:
            state_copy = copy.deepcopy(self.state)

        proxies: List[Dict[str, Any]] = []
        for proxy, record in state_copy.get("proxies", {}).items():
            if not record.get("passed"):
                continue
            proxies.append(
                {
                    "proxy": proxy,
                    "latency_ms": record.get("latency_ms"),
                    "last_tested": record.get("last_tested", ""),
                    "sources": record.get("sources", []),
                    "checks": record.get("checks", {}),
                }
            )

        proxies.sort(
            key=lambda row: (
                row["latency_ms"] is None,
                row["latency_ms"] if row["latency_ms"] is not None else 10**9,
                -len(row["sources"]),
                -_iso_to_epoch(row["last_tested"]),
            )
        )

        source_pass_counts: Dict[str, int] = {}
        for row in proxies:
            for source_url in row.get("sources", []):
                source_pass_counts[source_url] = source_pass_counts.get(source_url, 0) + 1

        source_rows: List[Dict[str, Any]] = []
        known_source_meta = state_copy.get("sources", {})
        all_source_urls = set(known_source_meta.keys()) | set(source_pass_counts.keys())
        for url in all_source_urls:
            meta = known_source_meta.get(url, {})
            passing_count = source_pass_counts.get(url, int(meta.get("passing_count", 0)))
            if passing_count <= 0:
                continue
            source_rows.append(
                {
                    "url": url,
                    "valid_count": int(meta.get("valid_count", 0)),
                    "fetched_count": int(meta.get("fetched_count", 0)),
                    "passing_count": passing_count,
                    "last_fetch": meta.get("last_fetch", ""),
                }
            )

        source_rows.sort(key=lambda row: (-row["passing_count"], row["url"]))

        scan_state = state_copy.get("scan", {})
        cursor = int(scan_state.get("cursor", 0) or 0)
        total = int(scan_state.get("total", 0) or 0)

        return {
            "settings": settings,
            "service": state_copy.get("service", {}),
            "scan": {
                "cursor": cursor,
                "total": total,
                "remaining": max(total - cursor, 0),
                "paused": bool(scan_state.get("paused", False)),
                "current_proxy": scan_state.get("current_proxy", ""),
                "last_source_refresh": scan_state.get("last_source_refresh", ""),
            },
            "auto_apply": state_copy.get("auto_apply", {}),
            "counts": {
                "known_proxies": len(state_copy.get("proxies", {})),
                "passed_proxies": len(proxies),
                "visible_sources": len(source_rows),
            },
            "passed_proxies": proxies[:proxy_limit],
            "sources": source_rows[:source_limit],
        }
