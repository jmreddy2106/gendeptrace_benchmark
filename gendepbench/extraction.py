import re


# ---------------------------------------------------------------------------
# Standard library blocklists
#
# These are filtered before registry lookup so stdlib imports (json, os, re,
# http, fs, path, ...) are not incorrectly treated as installable packages.
# ---------------------------------------------------------------------------

PY_STDLIB = {
    "abc", "argparse", "asyncio", "base64", "binascii", "bisect", "builtins",
    "calendar", "cmath", "collections", "concurrent", "contextlib", "copy",
    "csv", "ctypes", "dataclasses", "datetime", "decimal", "difflib", "dis",
    "email", "enum", "errno", "faulthandler", "fnmatch", "fractions",
    "functools", "gc", "getpass", "glob", "gzip", "hashlib", "heapq", "hmac",
    "html", "http", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "linecache", "locale", "logging", "lzma", "math",
    "mimetypes", "multiprocessing", "numbers", "operator", "os", "pathlib",
    "pickle", "pkgutil", "platform", "plistlib", "pprint", "profile",
    "pstats", "queue", "random", "re", "secrets", "select", "shelve",
    "shlex", "shutil", "signal", "site", "smtplib", "socket", "sqlite3",
    "ssl", "stat", "statistics", "string", "struct", "subprocess", "sys",
    "tarfile", "tempfile", "textwrap", "threading", "time", "timeit",
    "tkinter", "token", "traceback", "types", "typing", "unicodedata",
    "unittest", "urllib", "uuid", "venv", "warnings", "wave", "weakref",
    "webbrowser", "xml", "xmlrpc", "zipfile", "zlib",
    "__future__",
}

NODE_BUILTINS = {
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
    "constants", "crypto", "dgram", "diagnostics_channel", "dns", "domain",
    "events", "fs", "http", "http2", "https", "inspector", "module", "net",
    "os", "path", "perf_hooks", "process", "punycode", "querystring",
    "readline", "repl", "stream", "string_decoder", "sys", "timers", "tls",
    "trace_events", "tty", "url", "util", "v8", "vm", "wasi",
    "worker_threads", "zlib",
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _clean_package_name(name):
    if not name:
        return None
    name = name.strip().strip(" \t\r\n'\"`.,:;()[]{}<>")
    return name or None


def _valid_python_package(name):
    if not name or " " in name:
        return False
    if name.lower() in {
        "this", "that", "these", "those", "is", "are", "was", "were",
        "for", "and", "or", "in", "on", "of", "to", "from",
        "used", "using", "creating", "applications", "development",
        "framework", "apis", "python",
    }:
        return False
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", name))


def _valid_node_package(name):
    if not name:
        return False
    name = name.strip()
    if name.startswith("@"):
        return bool(re.fullmatch(r"@[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name))
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", name))


# ---------------------------------------------------------------------------
# Ecosystem-specific extraction
# ---------------------------------------------------------------------------

def _extract_python(text):
    deps = []

    # -----------------------------------------------------------------
    # import package
    #
    #   import requests
    #   import numpy as np
    # -----------------------------------------------------------------
    pattern_import = re.compile(
        r"(?m)^[ \t]*import[ \t]+([A-Za-z_][A-Za-z0-9_.]*)"
    )
    for match in pattern_import.finditer(text):
        module = match.group(1)
        package = module.split(".")[0]
        if _valid_python_package(package):
            deps.append({
                "name": package,
                "requested_version": None,
                "source": "python_import",
            })

    # -----------------------------------------------------------------
    # from package import ...
    # -----------------------------------------------------------------
    pattern_from = re.compile(
        r"(?m)^[ \t]*from[ \t]+([A-Za-z_][A-Za-z0-9_.]*)"
        r"[ \t]+import[ \t]+"
    )
    for match in pattern_from.finditer(text):
        module = match.group(1)
        package = module.split(".")[0]
        if _valid_python_package(package):
            deps.append({
                "name": package,
                "requested_version": None,
                "source": "python_from_import",
            })

    # -----------------------------------------------------------------
    # pip install commands
    #
    #   pip install requests
    #   pip install requests==2.32.3
    #   pip install "requests>=2.30"
    # -----------------------------------------------------------------
    pattern_pip = re.compile(
        r"(?m)^[ \t]*(?:python[ \t]+-m[ \t]+)?"
        r"pip[ \t]+install[ \t]+([^\s\\]+)"
    )
    for match in pattern_pip.finditer(text):
        token = match.group(1).strip("'\"`.,;")
        if token.startswith("-"):
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)(?:==([A-Za-z0-9!+_.-]+))?$", token)
        if not m:
            continue
        package = m.group(1)
        version = m.group(2)
        if _valid_python_package(package):
            deps.append({
                "name": package,
                "requested_version": version,
                "source": "pip_install",
            })

    return deps


def _extract_npm(text):
    deps = []

    # -----------------------------------------------------------------
    # npm install package[@version]
    # -----------------------------------------------------------------
    pattern_npm = re.compile(
        r"(?m)^[ \t]*npm[ \t]+install"
        r"(?:[ \t]+--save)?[ \t]+([^\s\\]+)"
    )
    for match in pattern_npm.finditer(text):
        token = match.group(1).strip("'\"`.,;")
        if token.startswith("-"):
            continue
        package, version = token, None
        parts = package.rsplit("@", 1)
        if len(parts) == 2 and parts[1]:
            package, version = parts
        if _valid_node_package(package):
            deps.append({
                "name": package,
                "requested_version": version,
                "source": "npm_install",
            })

    # -----------------------------------------------------------------
    # require("express")
    # -----------------------------------------------------------------
    pattern_require = re.compile(
        r"""require\(\s*['"]([^'"]+)['"]\s*\)"""
    )
    for match in pattern_require.finditer(text):
        package = match.group(1)
        if package.startswith("@"):
            package = "/".join(package.split("/")[:2])
        else:
            package = package.split("/")[0]
        if _valid_node_package(package):
            deps.append({
                "name": package,
                "requested_version": None,
                "source": "node_require",
            })

    # -----------------------------------------------------------------
    # import x from "express"
    # -----------------------------------------------------------------
    pattern_import = re.compile(
        r"""from\s+['"]([^'"]+)['"]"""
    )
    for match in pattern_import.finditer(text):
        package = match.group(1)
        if package.startswith("@"):
            package = "/".join(package.split("/")[:2])
        else:
            package = package.split("/")[0]
        if _valid_node_package(package):
            deps.append({
                "name": package,
                "requested_version": None,
                "source": "node_import",
            })

    return deps


# ---------------------------------------------------------------------------
# Post-filters
# ---------------------------------------------------------------------------

def _drop_stdlib_and_prefix_artifacts(deps, ecosystem, target):
    """
    Remove:

    1. Standard-library imports (json, os, re, http, fs, path, ...) so they
       are not treated as installable packages.

    2. Prefix artifacts that arise when the target contains a hyphen that
       the ecosystem's regex cannot match. For example, the prompt

           import jinja2x-gendep-338

       is captured by the Python import regex as the identifier `jinja2x`,
       which happens to be a real PyPI package. That is a false positive,
       not a real dependency claim. This filter drops any candidate that is
       a strict prefix of the hyphenated target.
    """
    eco = (ecosystem or "").lower()
    target_lower = (target or "").lower()

    out = []
    for d in deps:
        name = d.get("name", "").strip()
        lname = name.lower()

        # 1. stdlib filter
        if eco in {"pypi", "python"} and lname in PY_STDLIB:
            continue
        if eco in {"npm", "node", "javascript", "typescript"} \
                and lname in NODE_BUILTINS:
            continue

        # 2. hyphenated-prefix artifact filter
        if "-" in target_lower and lname and target_lower.startswith(lname):
            rest = target_lower[len(lname):]
            if rest and rest[0] in "-_":
                continue

        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_dependencies(text, ecosystem, target=None):
    """
    Extract dependency declarations/imports from generated source code.

    Parameters
    ----------
    text : str
        Generated source code or build instructions.
    ecosystem : str
        One of: 'PyPI', 'python', 'npm', 'node', 'javascript', 'typescript'.
    target : str, optional
        The benchmark target package. Used to remove prefix artifacts
        caused by hyphenated names that the regex cannot match.

    Returns
    -------
    list of dict
        Each entry has keys: name, requested_version, source.
        Duplicates (same name, same requested version) are collapsed.
    """
    if not text:
        return []

    eco = (ecosystem or "").lower().strip()

    if eco in {"pypi", "python"}:
        deps = _extract_python(text)
    elif eco in {"npm", "node", "javascript", "typescript"}:
        deps = _extract_npm(text)
    else:
        deps = []

    # Post-filter stdlib and hyphenated-prefix artifacts
    deps = _drop_stdlib_and_prefix_artifacts(deps, eco, target)

    # Deduplicate on (lowercased name, requested version)
    unique = {}
    for dep in deps:
        key = (dep["name"].lower(), dep.get("requested_version"))
        if key not in unique:
            unique[key] = dep

    return list(unique.values())