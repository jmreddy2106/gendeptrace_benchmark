#!/usr/bin/env bash
# scripts/08_full_pipeline.sh
#
# Full GenDepTrace pipeline with three model runs:
#   1. Build benchmark (verified against live registries)
#   2. Synthetic run          -> results/synthetic
#   3. Qwen 2.5 1.5B run      -> results/llm_qwen
#   4. Llama 3.1 8B run       -> results/llm_llama
#   5. Real SCA tool baselines
#   6. Sensitivity + failure injection (synthetic)
#   7. Cross-run comparison
#
# Usage:
#   bash scripts/08_full_pipeline.sh
#   SKIP_SYNTHETIC=1 SKIP_LLAMA=1 bash scripts/08_full_pipeline.sh
#   SKIP_SYNTHETIC=1 SKIP_QWEN=1  bash scripts/08_full_pipeline.sh
#   FORCE_REBUILD=1 bash scripts/08_full_pipeline.sh
#
# Run under tmux:
#   tmux new -s gendep
#   bash scripts/08_full_pipeline.sh 2>&1 | tee logs/pipeline.log

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BENCHMARK="data/benchmark.jsonl"
CONFIG="configs/default.yaml"

SYNTH_DIR="${SYNTH_DIR:-results/synthetic}"
QWEN_DIR="${QWEN_DIR:-results/llm_qwen}"
LLAMA_DIR="${LLAMA_DIR:-results/llm_llama}"
COMPARE_DIR="${COMPARE_DIR:-results/comparison}"

QWEN_MODEL="${QWEN_MODEL:-Qwen/Qwen2.5-1.5B-Instruct}"
LLAMA_MODEL="${LLAMA_MODEL:-meta-llama/Llama-3.1-8B-Instruct}"

SKIP_SYNTHETIC="${SKIP_SYNTHETIC:-0}"
SKIP_QWEN="${SKIP_QWEN:-0}"
SKIP_LLAMA="${SKIP_LLAMA:-0}"
SKIP_REAL_TOOLS="${SKIP_REAL_TOOLS:-0}"
SKIP_SENSITIVITY="${SKIP_SENSITIVITY:-0}"
FORCE_REBUILD="${FORCE_REBUILD:-0}"

MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-256}"
TEMPERATURE="${TEMPERATURE:-0.2}"
TOP_P="${TOP_P:-0.9}"
LOAD_IN_4BIT="${LOAD_IN_4BIT:-0}"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log()  { printf '\n[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
rule() { printf '\n%s\n' "============================================================"; }
banner() { rule; printf '%s\n' "$*"; rule; }

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------
banner "SETUP — creating output directories"
log "CWD: $(pwd)"

for d in "$SYNTH_DIR" "$QWEN_DIR" "$LLAMA_DIR" "$COMPARE_DIR" data results logs; do
    if mkdir -p "$d"; then
        log "  [ok]  $d"
    else
        echo "[FATAL] Could not create directory: $d"
        exit 1
    fi
done

# ---------------------------------------------------------------------------
# Environment checks
# ---------------------------------------------------------------------------
log "Environment check"

if ! python -c "import requests, pandas, scipy, numpy, yaml" 2>/dev/null; then
    echo "[ERROR] Missing base Python dependencies."
    echo "        Install with: pip install -r requirements.txt"
    exit 1
fi

PYTORCH_OK=0
if python -c "import torch, transformers" 2>/dev/null; then
    PYTORCH_OK=1
    python - <<'PY'
import torch
print(f"[env] torch {torch.__version__}  cuda {torch.version.cuda}  available {torch.cuda.is_available()}")
if torch.cuda.is_available():
    n = torch.cuda.device_count()
    names = [torch.cuda.get_device_name(i) for i in range(n)]
    print(f"[env] CUDA available: {n} device(s) -> {names}")
else:
    print("[env] CUDA not available; LLM runs will use CPU")
PY
else
    echo "[env] torch/transformers not installed; LLM runs will be skipped"
fi

# ---------------------------------------------------------------------------
# HuggingFace access check
# ---------------------------------------------------------------------------
hf_access_ok() {
    local model_id="$1"
    python - "$model_id" <<'PY'
import sys
model_id = sys.argv[1]
try:
    from huggingface_hub import hf_hub_download
    from huggingface_hub import errors
    try:
        hf_hub_download(model_id, "config.json")
        print(f"[access] {model_id}: OK")
        sys.exit(0)
    except errors.GatedRepoError:
        print(f"[access] {model_id}: gated, no access")
        sys.exit(1)
    except errors.RepositoryNotFoundError:
        print(f"[access] {model_id}: not found")
        sys.exit(1)
    except Exception as e:
        print(f"[access] {model_id}: cannot verify ({e})")
        sys.exit(1)
except ImportError:
    print("[access] huggingface_hub not installed")
    sys.exit(1)
PY
}

# ---------------------------------------------------------------------------
# Run one model
# ---------------------------------------------------------------------------
run_model() {
    local label="$1"
    local model_id="$2"
    local outdir="$3"

    banner "MODEL RUN: $label ($model_id) -> $outdir"

    if [ -f "$outdir/generation.jsonl" ] && [ "$FORCE_REBUILD" != "1" ]; then
        local n
        n=$(wc -l < "$outdir/generation.jsonl")
        log "Found existing generation ($n lines); skipping generation"
    else
        log "Generating with $model_id"
        LOAD_IN_4BIT="$LOAD_IN_4BIT" python scripts/02_run_generation.py \
            --benchmark "$BENCHMARK" \
            --outdir "$outdir" \
            --model "$model_id" \
            --max-new-tokens "$MAX_NEW_TOKENS" \
            --temperature "$TEMPERATURE" \
            --top-p "$TOP_P"
    fi

    log "Evaluating systems on $label run"
    for s in B0 B1 B2 B3 B4 GDT; do
        python scripts/03_run_evaluation.py \
            --benchmark "$BENCHMARK" \
            --outdir "$outdir" \
            --config "$CONFIG" \
            --system "$s" \
            --timing
    done

    log "Analyzing $label run"
    python scripts/07_analyze.py --outdir "$outdir"
}

# ---------------------------------------------------------------------------
# 1. Benchmark
# ---------------------------------------------------------------------------
banner "STEP 1/7 — BUILD BENCHMARK"

if [ -f "$BENCHMARK" ] && [ "$FORCE_REBUILD" != "1" ]; then
    log "Benchmark already exists at $BENCHMARK (set FORCE_REBUILD=1 to rebuild)"
else
    log "Building benchmark (verifies all versions against live registries)"
    python scripts/01_build_benchmark.py
fi

# ---------------------------------------------------------------------------
# 2. Synthetic
# ---------------------------------------------------------------------------
if [ "$SKIP_SYNTHETIC" = "0" ]; then
    banner "STEP 2/7 — SYNTHETIC RUN"

    if [ -f "$SYNTH_DIR/generation.jsonl" ] && [ "$FORCE_REBUILD" != "1" ]; then
        log "Synthetic generation already exists; reusing"
    else
        python scripts/02_run_generation.py \
            --benchmark "$BENCHMARK" \
            --outdir "$SYNTH_DIR" \
            --model synthetic
    fi

    log "Evaluating all systems on synthetic run"
    for s in B0 B1 B2 B3 B4 GDT; do
        python scripts/03_run_evaluation.py \
            --benchmark "$BENCHMARK" \
            --outdir "$SYNTH_DIR" \
            --config "$CONFIG" \
            --system "$s" \
            --timing
    done

    log "Analyzing synthetic run"
    python scripts/07_analyze.py --outdir "$SYNTH_DIR"
else
    log "SKIP_SYNTHETIC=1 -> skipping synthetic run"
fi

# ---------------------------------------------------------------------------
# 3. Qwen
# ---------------------------------------------------------------------------
if [ "$SKIP_QWEN" = "0" ] && [ "$PYTORCH_OK" = "1" ]; then
    if hf_access_ok "$QWEN_MODEL"; then
        run_model "Qwen" "$QWEN_MODEL" "$QWEN_DIR"
    else
        log "Skipping Qwen: model not accessible"
    fi
else
    if [ "$PYTORCH_OK" != "1" ]; then
        log "Skipping Qwen: torch/transformers not installed"
    else
        log "SKIP_QWEN=1 -> skipping Qwen run"
    fi
fi

# ---------------------------------------------------------------------------
# 4. Llama
# ---------------------------------------------------------------------------
if [ "$SKIP_LLAMA" = "0" ] && [ "$PYTORCH_OK" = "1" ]; then
    if hf_access_ok "$LLAMA_MODEL"; then
        run_model "Llama" "$LLAMA_MODEL" "$LLAMA_DIR"
    else
        log "Skipping Llama: model not accessible."
        echo
        echo "  To enable Llama:"
        echo "    1. Request access at https://huggingface.co/$LLAMA_MODEL"
        echo "    2. Run: hf auth login"
        echo "    3. Rerun this script"
        echo
    fi
else
    if [ "$PYTORCH_OK" != "1" ]; then
        log "Skipping Llama: torch/transformers not installed"
    else
        log "SKIP_LLAMA=1 -> skipping Llama run"
    fi
fi

# ---------------------------------------------------------------------------
# 5. Real SCA tools
# ---------------------------------------------------------------------------
if [ "$SKIP_REAL_TOOLS" = "0" ]; then
    banner "STEP 5/7 — REAL SCA TOOLS"
    for d in "$SYNTH_DIR" "$QWEN_DIR" "$LLAMA_DIR"; do
        if [ -f "$d/generation.jsonl" ]; then
            log "Running real SCA tools on $d"
            python scripts/04_run_real_baselines.py --outdir "$d" || true
        fi
    done
else
    log "SKIP_REAL_TOOLS=1 -> skipping real-tool baselines"
fi

# ---------------------------------------------------------------------------
# 6. Sensitivity + failure injection
# ---------------------------------------------------------------------------
if [ "$SKIP_SENSITIVITY" = "0" ]; then
    banner "STEP 6/7 — SENSITIVITY AND FAILURE INJECTION"

    if [ -f "$SYNTH_DIR/generation.jsonl" ]; then
        log "Sensitivity analysis (synthetic)"
        python scripts/05_run_sensitivity.py --outdir "$SYNTH_DIR"

        log "Failure injection (synthetic)"
        python scripts/06_run_failure_injection.py --outdir "$SYNTH_DIR"
    else
        log "No synthetic generation; skipping"
    fi
else
    log "SKIP_SENSITIVITY=1 -> skipping"
fi

# ---------------------------------------------------------------------------
# 7. Cross-run comparison
# ---------------------------------------------------------------------------
banner "STEP 7/7 — CROSS-RUN COMPARISON"

RUNS=()
if [ -f "$SYNTH_DIR/task_level_metrics.csv" ]; then
    RUNS+=(--run "synthetic=$SYNTH_DIR")
fi
if [ -f "$QWEN_DIR/task_level_metrics.csv" ]; then
    RUNS+=(--run "qwen=$QWEN_DIR")
fi
if [ -f "$LLAMA_DIR/task_level_metrics.csv" ]; then
    RUNS+=(--run "llama=$LLAMA_DIR")
fi

if [ ${#RUNS[@]} -ge 2 ]; then
    python scripts/09_compare_runs.py "${RUNS[@]}" --outdir "$COMPARE_DIR"
else
    log "Not enough completed runs to compare (need at least 2)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
banner "PIPELINE COMPLETE"

echo
for d in "$SYNTH_DIR" "$QWEN_DIR" "$LLAMA_DIR"; do
    if [ -f "$d/generation.jsonl" ]; then
        n=$(wc -l < "$d/generation.jsonl")
        log "$d: $n generated tasks"
    else
        log "$d: no generation.jsonl (skipped or failed)"
    fi
done

echo
echo "Outputs:"
echo "  Synthetic:  $SYNTH_DIR/"
echo "  Qwen:       $QWEN_DIR/"
echo "  Llama:      $LLAMA_DIR/"
echo "  Comparison: $COMPARE_DIR/"
echo
echo "Comparison files:"
echo "  $COMPARE_DIR/cross_run.csv"
echo "  $COMPARE_DIR/cross_run.json"
echo "  $COMPARE_DIR/combined_metrics.csv"
echo
