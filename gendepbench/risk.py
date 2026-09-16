def clamp(x):
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


def compute_dtes(factors, weights):
    total = 0.0
    for k, w in weights.items():
        total += clamp(factors.get(k, 0.0)) * float(w)
    return clamp(total)


def factor_hallucination(package_exists):
    return 0.0 if package_exists else 1.0


def _severity_score(vuln):
    best = 0.0
    for s in vuln.get("severity", []) or []:
        try:
            best = max(best, float(s.get("score", 0.0)))
        except (TypeError, ValueError):
            pass
    return best


def factor_vulnerability(vulns):
    if not vulns:
        return 0.0
    max_sev = max((_severity_score(v) for v in vulns), default=0.0)
    if max_sev > 0:
        return clamp(max_sev / 10.0)
    # No severity score available: use count-based fallback.
    return clamp(min(1.0, len(vulns) / 5.0))


def factor_unpinned(version):
    if not version:
        return 1.0
    v = str(version).strip()
    exact = v[0].isdigit() and all(ch not in v for ch in "<>~^*,")
    if v.startswith("==") or exact:
        return 0.0
    return 0.5


def package_health_risk(evidence):
    if not evidence.get("package_exists"):
        return 1.0
    risk = 0.0
    if not evidence.get("project_url"):
        risk += 0.4
    if evidence.get("license") in (None, "", "UNKNOWN"):
        risk += 0.2
    if not evidence.get("summary"):
        risk += 0.1
    return clamp(risk)


def provenance_risk(evidence, source_verified):
    if not source_verified:
        return 1.0
    if not evidence.get("evidence_hash"):
        return 0.5
    return 0.0