import sys, json, os, argparse
from pathlib import Path
sys.path.insert(0, ".")

from gendepbench.utils import read_jsonl, write_jsonl
from gendepbench.extraction import extract_dependencies
from gendepbench.baselines import run_all_real_tools


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--outdir", default="results")
    p.add_argument("--benchmark", default="data/benchmark.jsonl")
    a = p.parse_args()

    tasks = {x["task_id"]: x for x in read_jsonl(a.benchmark)}
    gen_path = os.path.join(a.outdir, "generation.jsonl")
    gens = list(read_jsonl(gen_path))

    rows = []
    for g in gens:
        task = tasks[g["task_id"]]
        deps = extract_dependencies(g["output"], task["ecosystem"])
        tools = run_all_real_tools(deps, task["ecosystem"])
        rows.append({
            "task_id": task["task_id"],
            "ecosystem": task["ecosystem"],
            "scenario": task["scenario"],
            "deps": deps,
            "tools": tools,
        })

    out = os.path.join(a.outdir, "real_tools.jsonl")
    write_jsonl(out, rows)

    available = set()
    for r in rows:
        for k, v in r["tools"].items():
            if v.get("status") == "ok":
                available.add(k)
    print(f"Ran real tools: {sorted(available)}")


if __name__ == "__main__":
    main()