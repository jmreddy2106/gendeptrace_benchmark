"""
Compare multiple evaluation runs (synthetic, LLM, etc.).

Usage:
    python scripts/09_compare_runs.py \
        --run synthetic=results/synthetic \
        --run qwen=results/llm_qwen \
        --run llama=results/llm_llama \
        --outdir results/comparison
"""
import os
import sys
import json
import argparse
import pandas as pd

sys.path.insert(0, ".")


def load_metrics(outdir):
    path = os.path.join(outdir, "task_level_metrics.csv")
    if not os.path.exists(path):
        raise SystemExit(
            f"Missing {path}\n"
            f"Run the pipeline for this directory first:\n"
            f"  LLM_DIR={outdir} LLM_MODEL=<model> bash scripts/08_full_pipeline.sh"
        )
    return pd.read_csv(path)


def compare(runs, out_dir):
    os.makedirs(out_dir, exist_ok=True)

    frames = []
    for name, path in runs.items():
        df = load_metrics(path)
        df["run"] = name
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    combined.to_csv(os.path.join(out_dir, "combined_metrics.csv"), index=False)

    # Task-level wide table: one row per (task_id, system), one column per run
    wide = combined.pivot_table(
        index=["task_id", "scenario", "ecosystem", "system"],
        columns="run",
        values=["blocked_count", "review_count", "allow_count",
                "dependency_count", "traceability_coverage"],
        aggfunc="mean",
    ).reset_index()
    wide.to_csv(os.path.join(out_dir, "combined_wide.csv"), index=False)

    # Scenario x System matrix, aggregated across tasks
    rows = []
    run_names = list(runs.keys())
    for scenario in sorted(combined["scenario"].unique()):
        for system in sorted(combined["system"].unique()):
            row = {"scenario": scenario, "system": system}
            for name in run_names:
                sub = combined[
                    (combined["run"] == name)
                    & (combined["scenario"] == scenario)
                    & (combined["system"] == system)
                ]
                row[f"{name}_tasks"] = int(sub["task_id"].nunique())
                row[f"{name}_claims"] = int(sub["dependency_count"].sum())
                row[f"{name}_block"] = int(sub["blocked_count"].sum())
                row[f"{name}_review"] = int(sub["review_count"].sum())
                row[f"{name}_allow"] = int(sub["allow_count"].sum())
            rows.append(row)

    cmp_df = pd.DataFrame(rows)
    cmp_df.to_csv(os.path.join(out_dir, "cross_run.csv"), index=False)

    summary = {
        "runs": {
            name: {
                "path": path,
                "tasks": int(load_metrics(path)["task_id"].nunique()),
                "models": sorted(
                    load_metrics(path)["model_id"].dropna().unique().tolist()
                ),
            }
            for name, path in runs.items()
        },
        "scenario_system_rows": rows,
    }
    with open(os.path.join(out_dir, "cross_run.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote {out_dir}/cross_run.csv")
    print(f"Wrote {out_dir}/cross_run.json")
    print(f"Wrote {out_dir}/combined_metrics.csv")
    print(f"Wrote {out_dir}/combined_wide.csv")
    print()
    print(cmp_df.to_string(index=False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--run", action="append", default=[],
        help="name=path (repeatable). Example: --run qwen=results/llm_qwen",
    )
    p.add_argument("--outdir", default="results/comparison")
    a = p.parse_args()

    if not a.run:
        # Sensible default when no runs are passed
        candidates = {
            "synthetic": "results/synthetic",
            "llm":       "results/llm",
            "qwen":      "results/llm_qwen",
            "llama":     "results/llm_llama",
        }
        a.run = [
            f"{name}={path}"
            for name, path in candidates.items()
            if os.path.exists(os.path.join(path, "task_level_metrics.csv"))
        ]
        if not a.run:
            raise SystemExit(
                "No runs specified and no default results found.\n"
                "Pass --run name=path explicitly."
            )
        print(f"No --run given; using defaults: {a.run}\n")

    runs = {}
    for spec in a.run:
        if "=" not in spec:
            raise SystemExit(
                f"Bad --run spec {spec!r}; expected name=path"
            )
        name, path = spec.split("=", 1)
        runs[name] = path

    compare(runs, a.outdir)


if __name__ == "__main__":
    main()
