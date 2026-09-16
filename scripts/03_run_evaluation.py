import argparse, sys, yaml, os
sys.path.insert(0, ".")
from gendepbench.evaluation import evaluate

p = argparse.ArgumentParser()
p.add_argument("--system", choices=["B0", "B1", "B2", "B3", "B4", "GDT"],
               required=True)
p.add_argument("--outdir", default="results")
p.add_argument("--benchmark", default="data/benchmark.jsonl")
p.add_argument("--config", default="configs/default.yaml")
p.add_argument("--limit", type=int)
p.add_argument("--timing", action="store_true")
a = p.parse_args()

os.makedirs(a.outdir, exist_ok=True)
generation = os.path.join(a.outdir, "generation.jsonl")
out = os.path.join(a.outdir, f"{a.system}.jsonl")
cfg = yaml.safe_load(open(a.config, encoding="utf-8"))

rows = evaluate(a.benchmark, generation, out, a.system, cfg, a.limit,
                timing=a.timing)
print("Wrote", len(rows), "records to", out)