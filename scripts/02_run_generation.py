import argparse, sys, os
sys.path.insert(0, ".")
from gendepbench.generation import run_generation

p = argparse.ArgumentParser()
p.add_argument("--model", default="synthetic")
p.add_argument("--outdir", default="results")
p.add_argument("--limit", type=int)
p.add_argument("--benchmark", default="data/benchmark.jsonl")
p.add_argument("--max-input-tokens", type=int, default=1536)
p.add_argument("--max-new-tokens", type=int, default=256)
p.add_argument("--temperature", type=float, default=0.2)
p.add_argument("--top-p", type=float, default=0.9)
a = p.parse_args()

os.makedirs(a.outdir, exist_ok=True)
out = os.path.join(a.outdir, "generation.jsonl")

run_generation(
    a.benchmark, out, a.model, a.limit,
    max_input_tokens=a.max_input_tokens,
    max_new_tokens=a.max_new_tokens,
    temperature=a.temperature,
    top_p=a.top_p,
)