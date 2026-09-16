import argparse
from pathlib import Path
import yaml
from .benchmark import build
from .generation import run_generation
from .evaluation import evaluate
from .statistics import summarize, paired_tests
from .utils import read_jsonl


def main():
    p = argparse.ArgumentParser("GenDepBench")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--config", default="configs/default.yaml")
    b.add_argument("--tasks", type=int, default=300)
    b.add_argument("--seed", type=int, default=20260812)
    b.add_argument("--out", default="data/benchmark.jsonl")

    g = sub.add_parser("generate")
    g.add_argument("--benchmark", default="data/benchmark.jsonl")
    g.add_argument("--out", default="results/generation.jsonl")
    g.add_argument("--model", default="synthetic")
    g.add_argument("--limit", type=int)
    g.add_argument("--max-input-tokens", type=int, default=1536)
    g.add_argument("--max-new-tokens", type=int, default=256)
    g.add_argument("--temperature", type=float, default=0.2)
    g.add_argument("--top-p", type=float, default=0.9)

    e = sub.add_parser("evaluate")
    e.add_argument("--config", default="configs/default.yaml")
    e.add_argument("--benchmark", default="data/benchmark.jsonl")
    e.add_argument("--generation", default="results/generation.jsonl")
    e.add_argument("--out", required=True)
    e.add_argument("--system",
                   choices=["B0", "B1", "B2", "B3", "B4", "GDT"],
                   required=True)
    e.add_argument("--limit", type=int)
    e.add_argument("--timing", action="store_true")

    a = sub.add_parser("analyze")
    a.add_argument("--input", nargs="+", required=True)
    a.add_argument("--outdir", default="results")

    args = p.parse_args()

    if args.cmd == "build":
        print(build(args.config, args.out, args.tasks, args.seed))
    elif args.cmd == "generate":
        run_generation(args.benchmark, args.out, args.model, args.limit,
                       max_input_tokens=args.max_input_tokens,
                       max_new_tokens=args.max_new_tokens,
                       temperature=args.temperature, top_p=args.top_p)
    elif args.cmd == "evaluate":
        cfg = yaml.safe_load(Path(args.config).read_text())
        evaluate(args.benchmark, args.generation, args.out, args.system, cfg,
                 args.limit, timing=args.timing)
    elif args.cmd == "analyze":
        import pandas as pd
        frames = [pd.DataFrame(list(read_jsonl(x))) for x in args.input]
        df = pd.concat(frames, ignore_index=True)
        outdir = Path(args.outdir); outdir.mkdir(exist_ok=True)
        s = summarize(df)
        s.to_csv(outdir / "experiment_summary.csv", index=False)
        tests = paired_tests(df, "blocked_count")
        tests.to_csv(outdir / "statistical_tests.csv", index=False)
        cols = ["task_id", "scenario", "ecosystem", "model_id", "system",
                "dependency_count", "blocked_count", "review_count",
                "allow_count", "traceability_coverage",
                "generation_latency_seconds", "target_vulnerabilities"]
        df[[c for c in cols if c in df.columns]].to_csv(
            outdir / "task_level_metrics.csv", index=False)
        print(s.to_string(index=False))
        print(tests.to_string(index=False))


if __name__ == "__main__":
    main()