import glob, sys, os, argparse
import pandas as pd
sys.path.insert(0, ".")
from gendepbench.utils import read_jsonl
from gendepbench.statistics import summarize, paired_tests


def analyze(outdir):
    files = sorted(
        [f for f in glob.glob(os.path.join(outdir, "B*.jsonl"))
         if "sensitivity" not in f]
        + glob.glob(os.path.join(outdir, "GDT*.jsonl"))
    )
    if not files:
        raise SystemExit(f"No evaluation files found in {outdir}")

    df = pd.concat([pd.DataFrame(list(read_jsonl(f))) for f in files],
                   ignore_index=True)
    df.to_json(os.path.join(outdir, "all_evaluations.jsonl"),
               orient="records", lines=True)

    s = summarize(df)
    s.to_csv(os.path.join(outdir, "experiment_summary.csv"), index=False)

    tests = paired_tests(df, "blocked_count")
    tests.to_csv(os.path.join(outdir, "statistical_tests.csv"), index=False)

    cols = ["task_id", "scenario", "ecosystem", "model_id", "system",
            "dependency_count", "blocked_count", "review_count", "allow_count",
            "traceability_coverage", "generation_latency_seconds",
            "target_vulnerabilities"]
    df[[c for c in cols if c in df.columns]].to_csv(
        os.path.join(outdir, "task_level_metrics.csv"), index=False)

    print(f"\n=== Summary for {outdir} ===")
    print(s.to_string(index=False))
    print(f"\n=== Statistical tests for {outdir} ===")
    print(tests.to_string(index=False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--outdir", default="results")
    a = p.parse_args()
    analyze(a.outdir)


if __name__ == "__main__":
    main()