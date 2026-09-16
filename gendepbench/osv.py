import json
from pathlib import Path
import requests

from .utils import sha256_json, now_iso


class OSVClient:
    def __init__(self, cfg, cache_dir="evidence_cache"):
        self.url = cfg.get("osv_url", "https://api.osv.dev/v1/query")
        self.timeout = int(cfg.get("timeout_seconds", 20))
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": cfg.get("user_agent",
                                  "GenDepBench/1.0 (dependency-security-research)")
        })

    def query(self, ecosystem, name, version):
        payload = {"package": {"name": name, "ecosystem": ecosystem},
                   "version": version}
        key = sha256_json(payload)
        path = self.cache / f"osv_{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        try:
            r = self.session.post(self.url, json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            data["_status"] = "ok"
        except requests.RequestException as exc:
            data = {"_status": "error", "_error": str(exc), "vulns": []}
        data["_payload"] = payload
        data["_retrieved_at"] = now_iso()
        data["_evidence_hash"] = sha256_json(data)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return data

    @staticmethod
    def findings(data):
        if not data or data.get("_status") == "error":
            return []
        return data.get("vulns", []) or []

    @staticmethod
    def status(data):
        if not data:
            return "empty"
        return data.get("_status", "unknown")