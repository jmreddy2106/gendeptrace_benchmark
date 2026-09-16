import sys
sys.path.insert(0, ".")
from gendepbench.benchmark import build

cfg = "configs/default.yaml"
manifest = build(cfg, "data/benchmark.jsonl", tasks=300, seed=20260812)
print(manifest)