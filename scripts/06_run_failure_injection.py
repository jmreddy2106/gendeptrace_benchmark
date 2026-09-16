import sys, json, argparse, os
from unittest.mock import patch
sys.path.insert(0, ".")

import yaml
from gendepbench.evaluation import evaluate
from gendepbench import registries, osv


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--outdir", default="results")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument("--benchmark", default="data/benchmark.jsonl")
    a = p.parse_args()

    cfg = yaml.safe_load(open(a.config))
    generation = os.path.join(a.outdir, "generation.jsonl")

    with patch.object(registries.RegistryClient, "resolve",
                      return_value={
                          "package_exists": None, "version_exists": None,
                          "exists": False, "status": "registry_error",
                          "requested_version": None, "resolved_version": None,
                          "project_url": None, "retrieved_at": "n/a",
                      }):
        rows = evaluate(a.benchmark, generation,
                        os.path.join(a.outdir, "failure_registry.jsonl"),
                        "GDT", cfg, limit=50)

    decisions = {}
    for r in rows:
        for dr in r["dependency_records"]:
            decisions[dr["decision"]] = decisions.get(dr["decision"], 0) + 1
    print("Registry failure -> decisions:", decisions)
    assert decisions.get("ALLOW", 0) == 0, \
        "Registry failures must not ALLOW"

    with patch.object(osv.OSVClient, "query",
                      return_value={"_status": "error", "vulns": []}):
        rows = evaluate(a.benchmark, generation,
                        os.path.join(a.outdir, "failure_osv.jsonl"),
                        "GDT", cfg, limit=50)

    decisions = {}
    for r in rows:
        for dr in r["dependency_records"]:
            decisions[dr["decision"]] = decisions.get(dr["decision"], 0) + 1
    print("OSV failure -> decisions:", decisions)
    print("Failure-injection tests passed.")


if __name__ == "__main__":
    main()