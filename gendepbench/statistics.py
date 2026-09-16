import math
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon


def summarize(df):
    g = df.groupby("system")
    out = g.agg(
        tasks=("task_id", "nunique"),
        dependency_claims=("dependency_count", "sum"),
        blocked=("blocked_count", "sum"),
        review=("review_count", "sum"),
        allowed=("allow_count", "sum"),
        traceability=("traceability_coverage", "mean"),
        latency_mean=("generation_latency_seconds", "mean"),
        latency_median=("generation_latency_seconds", "median"),
        vuln_targets=("target_vulnerabilities", "sum"),
    ).reset_index()
    return out


def _pair(df, other, gdt, metric):
    a = df[df.system == other].set_index("task_id")[metric]
    b = df[df.system == gdt].set_index("task_id")[metric]
    common = a.index.intersection(b.index)
    if len(common) < 2:
        return None
    x = a.loc[common].to_numpy()
    y = b.loc[common].to_numpy()
    diff = y - x
    if np.allclose(diff, 0):
        return {"n": len(common), "median_delta": 0.0,
                "wilcoxon_stat": None, "p_value": 1.0,
                "all_identical": True}
    stat, p = wilcoxon(x, y, zero_method="wilcox", alternative="two-sided")
    return {"n": len(common), "median_delta": float(np.median(diff)),
            "wilcoxon_stat": float(stat), "p_value": float(p),
            "all_identical": False}


def paired_tests(df, metric="blocked_count"):
    rows = []
    systems = sorted(set(df.system) - {"GDT"})
    for other in systems:
        r = _pair(df, other, "GDT", metric)
        if r is None:
            continue
        rows.append({
            "metric": metric,
            "comparison": f"GDT_vs_{other}",
            "n": r["n"],
            "median_delta": r["median_delta"],
            "wilcoxon_stat": r["wilcoxon_stat"],
            "p_value": r["p_value"],
            "all_identical": r["all_identical"],
            "note": ("B0-B3 all identical by construction" 
                     if r["all_identical"] else ""),
        })
    return pd.DataFrame(rows)
