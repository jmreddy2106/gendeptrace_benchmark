from pathlib import Path
import json
import re
import time
import requests


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class RegistryClient:
    """
    Registry evidence client.

    Canonical evidence fields:
        package_exists : True | False | None
        version_exists : True | False | None
        status         : verified | package_not_found | version_not_found | registry_error
        resolved_version : str | None
    """

    def __init__(self, apis, cache_dir="evidence_cache"):
        self.apis = apis or {}
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = int(self.apis.get("timeout_seconds", 15))
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.apis.get(
                "user_agent", "GenDepBench/1.0 (dependency-security-research)")
        })

    def _cache_path(self, key):
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)
        return self.cache_dir / f"{safe}.json"

    def _get_json(self, url, cache_key):
        path = self._cache_path(cache_key)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8")), 200, True
            except Exception:
                pass
        try:
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 404:
                return None, 404, False
            response.raise_for_status()
            data = response.json()
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data, response.status_code, False
        except requests.RequestException as exc:
            return {"_error": str(exc)}, None, False

    # ---------------- PyPI ----------------
    def pypi(self, name, version=None):
        name = str(name).strip()
        url = f"https://pypi.org/pypi/{name}/json"
        data, status, _ = self._get_json(url, f"pypi_{name}")

        if status == 404:
            return {
                "package_exists": False, "version_exists": False,
                "exists": False, "status": "package_not_found",
                "requested_version": version, "resolved_version": None,
                "project_url": f"https://pypi.org/project/{name}/",
                "retrieved_at": _now(), "url": url,
            }
        if status is None:
            return {
                "package_exists": None, "version_exists": None,
                "exists": False, "status": "registry_error",
                "requested_version": version, "resolved_version": None,
                "project_url": None, "error": data.get("_error"),
                "retrieved_at": _now(), "url": url,
            }

        info = data.get("info", {})
        releases = data.get("releases", {})
        project_url = info.get("project_url") or info.get("home_page") \
            or f"https://pypi.org/project/{name}/"

        if not version:
            latest = info.get("version")
            return {
                "package_exists": True, "version_exists": True,
                "exists": True, "status": "verified",
                "requested_version": None, "resolved_version": latest,
                "project_url": project_url,
                "summary": info.get("summary"),
                "license": info.get("license"),
                "requires_dist": info.get("requires_dist"),
                "dependencies": {},
                "retrieved_at": _now(), "url": url,
            }

        version = str(version).strip()
        if version in releases:
            return {
                "package_exists": True, "version_exists": True,
                "exists": True, "status": "verified",
                "requested_version": version, "resolved_version": version,
                "project_url": project_url,
                "summary": info.get("summary"),
                "license": info.get("license"),
                "requires_dist": info.get("requires_dist"),
                "dependencies": {},
                "retrieved_at": _now(), "url": f"{url}?version={version}",
            }
        return {
            "package_exists": True, "version_exists": False,
            "exists": True, "status": "version_not_found",
            "requested_version": version, "resolved_version": version,
            "project_url": project_url,
            "summary": info.get("summary"),
            "license": info.get("license"),
            "requires_dist": info.get("requires_dist"),
            "dependencies": {},
            "retrieved_at": _now(), "url": f"{url}?version={version}",
        }

    # ---------------- npm ----------------
    def npm(self, name, version=None):
        name = str(name).strip()
        url = f"https://registry.npmjs.org/{name}"
        data, status, _ = self._get_json(url, f"npm_{name.replace('/', '_')}")

        if status == 404:
            return {
                "package_exists": False, "version_exists": False,
                "exists": False, "status": "package_not_found",
                "requested_version": version, "resolved_version": None,
                "project_url": f"https://www.npmjs.com/package/{name}",
                "retrieved_at": _now(), "url": url,
            }
        if status is None:
            return {
                "package_exists": None, "version_exists": None,
                "exists": False, "status": "registry_error",
                "requested_version": version, "resolved_version": None,
                "project_url": None, "error": data.get("_error"),
                "retrieved_at": _now(), "url": url,
            }

        versions = data.get("versions", {})
        dist_tags = data.get("dist-tags", {})
        project_url = f"https://www.npmjs.com/package/{name}"

        if not version:
            return {
                "package_exists": True, "version_exists": True,
                "exists": True, "status": "verified",
                "requested_version": None,
                "resolved_version": dist_tags.get("latest"),
                "project_url": project_url,
                "summary": data.get("description"),
                "license": data.get("license"),
                "requires_dist": None, "dependencies": {},
                "retrieved_at": _now(), "url": url,
            }

        version = str(version).strip()
        if version in versions:
            meta = versions[version]
            return {
                "package_exists": True, "version_exists": True,
                "exists": True, "status": "verified",
                "requested_version": version, "resolved_version": version,
                "project_url": project_url,
                "summary": data.get("description"),
                "license": (meta.get("license") if isinstance(meta, dict)
                            else data.get("license")),
                "requires_dist": None,
                "dependencies": (meta.get("dependencies", {})
                                 if isinstance(meta, dict) else {}),
                "retrieved_at": _now(), "url": f"{url}/{version}",
            }
        return {
            "package_exists": True, "version_exists": False,
            "exists": True, "status": "version_not_found",
            "requested_version": version, "resolved_version": version,
            "project_url": project_url,
            "summary": data.get("description"),
            "license": data.get("license"),
            "requires_dist": None, "dependencies": {},
            "retrieved_at": _now(), "url": f"{url}/{version}",
        }

    def resolve(self, ecosystem, name, version=None):
        eco = str(ecosystem).strip().lower()
        if eco in {"pypi", "python"}:
            return self.pypi(name, version)
        if eco in {"npm", "node", "javascript", "typescript"}:
            return self.npm(name, version)
        return {
            "package_exists": None, "version_exists": None,
            "exists": False, "status": "registry_error",
            "requested_version": version, "resolved_version": None,
            "project_url": None, "error": f"Unsupported ecosystem: {ecosystem}",
            "retrieved_at": _now(),
        }