"""Real SCA tool wrappers (pip-audit, npm audit, syft, grype)."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def _which(cmd):
    return shutil.which(cmd)


def run_pip_audit(deps, timeout=120):
    if not _which("pip-audit"):
        return {"status": "unavailable", "tool": "pip-audit"}
    specs = [f"{d['name']}=={d['requested_version']}"
             if d.get("requested_version") else d["name"] for d in deps]
    req_file = Path(tempfile.mkstemp(suffix=".txt")[1])
    req_file.write_text("\n".join(specs), encoding="utf-8")
    try:
        out = subprocess.run(
            ["pip-audit", "-r", str(req_file), "-f", "json"],
            capture_output=True, text=True, timeout=timeout)
        data = json.loads(out.stdout or "{}")
        return {"status": "ok", "tool": "pip-audit",
                "exit_code": out.returncode, "findings": data}
    except Exception as exc:
        return {"status": "error", "tool": "pip-audit", "error": str(exc)}
    finally:
        req_file.unlink(missing_ok=True)


def run_npm_audit(deps, timeout=120):
    if not _which("npm"):
        return {"status": "unavailable", "tool": "npm audit"}
    pkg = {"name": "gendepbench-audit", "version": "1.0.0", "dependencies": {}}
    for d in deps:
        pkg["dependencies"][d["name"]] = d.get("requested_version") or "*"
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "package.json").write_text(json.dumps(pkg),
                                               encoding="utf-8")
        try:
            subprocess.run(["npm", "install", "--package-lock-only",
                            "--no-audit", "--no-fund"],
                           cwd=td, capture_output=True, text=True,
                           timeout=timeout)
            out = subprocess.run(["npm", "audit", "--json"],
                                 cwd=td, capture_output=True, text=True,
                                 timeout=timeout)
            data = json.loads(out.stdout or "{}")
            return {"status": "ok", "tool": "npm audit",
                    "exit_code": out.returncode, "findings": data}
        except Exception as exc:
            return {"status": "error", "tool": "npm audit", "error": str(exc)}


def run_syft(deps, timeout=120):
    if not _which("syft"):
        return {"status": "unavailable", "tool": "syft"}
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "requirements.txt").write_text(
            "\n".join(f"{d['name']}=={d.get('requested_version') or '0'}"
                      for d in deps), encoding="utf-8")
        try:
            out = subprocess.run(["syft", f"dir:{td}", "-o", "json"],
                                 capture_output=True, text=True,
                                 timeout=timeout)
            data = json.loads(out.stdout or "{}")
            return {"status": "ok", "tool": "syft", "findings": data}
        except Exception as exc:
            return {"status": "error", "tool": "syft", "error": str(exc)}


def run_grype(deps, timeout=120):
    if not _which("grype"):
        return {"status": "unavailable", "tool": "grype"}
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "requirements.txt").write_text(
            "\n".join(f"{d['name']}=={d.get('requested_version') or '0'}"
                      for d in deps), encoding="utf-8")
        try:
            out = subprocess.run(["grype", f"dir:{td}", "-o", "json"],
                                 capture_output=True, text=True,
                                 timeout=timeout)
            data = json.loads(out.stdout or "{}")
            return {"status": "ok", "tool": "grype", "findings": data}
        except Exception as exc:
            return {"status": "error", "tool": "grype", "error": str(exc)}


def run_all_real_tools(deps, ecosystem):
    results = {}
    if ecosystem.lower() in {"pypi", "python"}:
        results["pip-audit"] = run_pip_audit(deps)
        results["grype"] = run_grype(deps)
    else:
        results["npm audit"] = run_npm_audit(deps)
    results["syft"] = run_syft(deps)
    return results