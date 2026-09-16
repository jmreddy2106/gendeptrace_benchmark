import sys, yaml, json, copy, os, argparse
from pathlib import Path
sys.path.insert(0, ".")

from gendepbench.evaluation import evaluate


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--outdir", default="results")
    p.add_argument("--config", default="configs/default.yaml")
    p.add_argument("--benchmark", default="data/benchmark.jsonl")
    a = p.parse_args()

    base = yaml.safe_load(Path(a.config).read_text())
    weight_grid = base["sensitivity"]["weight_grid"]
    threshold_grid = base["sensitivity"]["threshold_grid"]

    sens_dir = os.path.join(a.outdir, "sensitivity")
    os.makedirs(sens_dir, exist_ok=True)
    generation = os.path.join(a.outdir, "generation.jsonl")

    summary = []
    for wi, weights in enumerate(weight_grid):
        for ti, thresholds in enumerate(threshold_grid):
            cfg = copy.deepcopy(base)
            cfg["risk"]["weights"] = weights
            cfg["risk"]["thresholds"] = thresholds
            out = os.path.join(sens_dir, f"gdt_w{wi}_t{ti}.jsonl")
            rows = evaluate(a.benchmark, generation, out, "GDT", cfg)
            summary.append({
                "weight_index": wi,
                "threshold_index": ti,
                "weights": weights,
                "thresholds": thresholds,
                "blocked": sum(r["blocked_count"] for r in rows),
                "review": sum(r["review_count"] for r in rows),
                "allowed": sum(r["allow_count"] for r in rows),
            })

    Path(os.path.join(sens_dir, "summary.json")).write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()