from pathlib import Path

from .registries import RegistryClient
from .osv import OSVClient
from .extraction import extract_dependencies
from .risk import (
    compute_dtes, factor_hallucination, factor_vulnerability,
    factor_unpinned, package_health_risk, provenance_risk,
)
from .policy import decide
from .provenance import make_adar, make_gdpg
from .sbom import make_cyclonedx
from .timing import StageTimer
from .utils import read_jsonl, write_jsonl


def _factor_vector(dep, evidence, vulns, version):
    return {
        "hallucination": factor_hallucination(bool(evidence.get("package_exists"))),
        "vulnerability": factor_vulnerability(vulns),
        "transitive": 0.0,
        "health":        package_health_risk(evidence),
        "provenance":    provenance_risk(evidence, bool(evidence.get("project_url"))),
        "unpinned":      factor_unpinned(version),
    }


def _score_and_decide(system, factors, weights, evidence, policy_cfg, thresholds):
    if system == "B0":
        return 0.0, "ALLOW", ["raw_generation_baseline"]
    if system == "B1":
        return 0.0, "ALLOW", ["post_build_sbom_baseline"]
    if system == "B2":
        s = factors["vulnerability"] * weights["vulnerability"]
        return s, ("BLOCK" if s >= thresholds["block"] else "ALLOW"), \
               ["post_build_vulnerability_scan"]
    if system == "B3":
        s = (factors["vulnerability"] * weights["vulnerability"] +
             factors["provenance"] * weights["provenance"])
        d = "BLOCK" if s >= thresholds["block"] else \
            ("REVIEW" if s >= thresholds["review"] else "ALLOW")
        return s, d, ["post_build_provenance_baseline"]
    if system == "B4":
        # Registry-existence-only control: block iff package missing.
        pe = evidence.get("package_exists")
        s = 0.0
        if pe is False:
            return s, "BLOCK", ["registry_only_package_missing"]
        if pe is None:
            return s, "REVIEW", ["registry_only_registry_error"]
        return s, "ALLOW", ["registry_only_package_exists"]
    # GDT
    s = compute_dtes(factors, weights)
    d, reasons = decide(s, evidence, policy_cfg)
    return s, d, reasons


def evaluate(benchmark_path, generation_path, out_path, system, cfg,
             limit=None, cache_dir="evidence_cache", timing=False):

    tasks = {x["task_id"]: x for x in read_jsonl(benchmark_path)}
    gens = list(read_jsonl(generation_path))

    reg = RegistryClient(cfg["apis"], cache_dir)
    osv = OSVClient(cfg["apis"], cache_dir)

    weights = cfg["risk"]["weights"]
    thresholds = cfg["risk"]["thresholds"]
    policy_cfg = {
        "block_unresolved": cfg["policy"].get("block_unresolved", True),
        "block_threshold": thresholds["block"],
        "review_threshold": thresholds["review"],
        "review_on_registry_error": cfg["policy"].get("review_on_registry_error", True),
    }

    timer = StageTimer()
    rows = []

    for i, generation in enumerate(gens):
        if limit is not None and i >= limit:
            break
        task_id = generation["task_id"]
        if task_id not in tasks:
            raise KeyError(f"Task ID {task_id} not in benchmark")
        task = tasks[task_id]

        with timer.stage("extraction"):
            deps = extract_dependencies(generation["output"], task["ecosystem"])

        target = task["target_package"]
        if not any(d["name"].lower() == target.lower() for d in deps):
            deps.append({
                "name": target,
                "requested_version": task.get("target_version"),
                "source": "benchmark_target_not_emitted",
            })

        dep_records = []
        for dep in deps:
            version = dep.get("requested_version")
            with timer.stage("registry"):
                evidence = reg.resolve(task["ecosystem"], dep["name"], version)
            osv_data = {}
            if evidence.get("package_exists") and evidence.get("resolved_version"):
                with timer.stage("osv"):
                    osv_data = osv.query(task["ecosystem"], dep["name"],
                                         evidence.get("resolved_version"))
            vulns = osv.findings(osv_data)
            factors = _factor_vector(dep, evidence, vulns, version)
            with timer.stage("policy"):
                score, decision, reasons = _score_and_decide(
                    system, factors, weights, evidence, policy_cfg, thresholds)

            record = {
                "dependency": dep,
                "evidence": evidence,
                "osv": osv_data,
                "vulnerabilities": vulns,
                "factors": factors,
                "risk_score": score,
                "decision": decision,
                "reasons": reasons,
            }
            if system == "GDT":
                record["adar"] = make_adar(task, generation, dep, evidence,
                                           osv_data, score, decision)
            dep_records.append(record)

        sbom = make_cyclonedx(task, generation, dep_records)
        gdpg = make_gdpg(task, generation, dep_records) if system == "GDT" else None

        target_records = [r for r in dep_records
                          if r["dependency"]["name"].lower() == target.lower()]

        versioned = [r for r in target_records
                     if r["dependency"].get("requested_version")]
        pool = versioned or target_records
        target_evidence = max(
            pool, key=lambda r: len(r.get("vulnerabilities", []))) if pool else None

        target_pkg_exists = any(
            r["evidence"].get("package_exists") for r in target_records)
        target_ver_exists = any(
            r["evidence"].get("version_exists") for r in target_records)
        target_vuln_ids = set()
        for r in target_records:
            for v in r.get("vulnerabilities", []):
                if v.get("id"):
                    target_vuln_ids.add(v["id"])
        target_vulns = len(target_vuln_ids)
        target_max_risk = max((r.get("risk_score", 0.0) for r in target_records),
                              default=0.0)
        t_blocked = sum(1 for r in target_records if r["decision"] == "BLOCK")
        t_review = sum(1 for r in target_records if r["decision"] == "REVIEW")
        t_allowed = sum(1 for r in target_records if r["decision"] == "ALLOW")

        rows.append({
            "task_id": task["task_id"],
            "scenario": task["scenario"],
            "ecosystem": task["ecosystem"],
            "model_id": generation.get("model_id", "unknown"),
            "system": system,
            "target_package": target,
            "expected_decision": task.get("expected_decision"),
            "target_package_exists": target_pkg_exists,
            "target_version_exists": target_ver_exists,
            "target_vulnerabilities": target_vulns,
            "target_max_risk": target_max_risk,
            "target_blocked_count": t_blocked,
            "target_review_count": t_review,
            "target_allowed_count": t_allowed,
            "target_evidence": target_evidence,
            "dependency_count": len(dep_records),
            "blocked_count": sum(r["decision"] == "BLOCK" for r in dep_records),
            "review_count": sum(r["decision"] == "REVIEW" for r in dep_records),
            "allow_count": sum(r["decision"] == "ALLOW" for r in dep_records),
            "traceability_coverage": 1.0 if (system == "GDT" and dep_records) else 0.0,
            "generation_latency_seconds": generation.get("latency_seconds"),
            "sbom_components": len(sbom["components"]),
            "sbom": sbom,
            "gdpg": gdpg,
            "dependency_records": dep_records,
        })

    write_jsonl(out_path, rows)

    if timing:
        Path(out_path).with_suffix(".timing.json").write_text(
            __import__("json").dumps(timer.snapshot(), indent=2),
            encoding="utf-8")

    return rows