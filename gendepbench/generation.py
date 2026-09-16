import os
import time
from pathlib import Path

from .utils import sha256_text, now_iso, write_jsonl, read_jsonl


# ---------------------------------------------------------------------------
# Device selection
# ---------------------------------------------------------------------------
# Modern PyTorch dropped support for GPUs below compute capability 7.5
# (Turing, 2018). Tesla M10 cards are CC 5.0 (Maxwell) and will crash with
# "no kernel image is available for execution on the device" if we try to
# run on them. This helper returns True only when the GPU is usable.
def _cuda_usable():
    if os.environ.get("FORCE_CPU", "0") == "1":
        return False
    try:
        import torch
        if not torch.cuda.is_available():
            return False
        try:
            cap = torch.cuda.get_device_capability(0)
        except Exception:
            return False
        # PyTorch 2.11 builds for sm_75 and above. Anything older is unusable.
        return cap >= (7, 5)
    except Exception:
        return False


class SyntheticGenerator:
    """Deterministic generator; no LLM required."""

    def __init__(self, model_id="synthetic", **kwargs):
        self.model_id = model_id

    def generate(self, prompt):
        pkg = ""
        for line in prompt.splitlines():
            if line.startswith("Requested package: "):
                pkg = line.split(":", 1)[1].strip()
        body = f"import {pkg}\nprint({pkg}.__name__)\n" if pkg \
            else "print('no package')\n"
        body += f"\npip install {pkg}\n" if pkg else ""
        t0 = time.perf_counter()
        out = body
        elapsed = time.perf_counter() - t0
        return {
            "model_id": self.model_id,
            "model_revision": None,
            "prompt_sha256": sha256_text(prompt),
            "output_sha256": sha256_text(out),
            "prompt": prompt,
            "output": out,
            "timestamp": now_iso(),
            "latency_seconds": elapsed,
            "generation_config": {"synthetic": True},
        }


class LocalHFGenerator:
    def __init__(self, model_id, max_input_tokens=1536, max_new_tokens=256,
                 temperature=0.2, top_p=0.9, do_sample=True):
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM
        except ImportError as exc:
            raise ImportError(
                "LLM generation requires `torch` and `transformers`. "
                "Install with: pip install -r requirements-llm.txt"
            ) from exc

        self.torch = torch
        self.model_id = model_id
        self.max_input_tokens = max_input_tokens
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.do_sample = do_sample

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load tokenizer for {model_id}. "
                f"If the model is gated, run `hf auth login` first. "
                f"Original error: {exc}"
            ) from exc

        # Decide device once. If the GPU can't run modern PyTorch kernels,
        # stay on CPU rather than crashing on the first forward pass.
        self.use_cuda = _cuda_usable()

        if self.use_cuda:
            print(f"[generation] loading {model_id} on GPU (fp16)")
            self.model = AutoModelForCausalLM.from_pretrained(
                model_id, dtype=torch.float16, device_map="auto",
            )
        else:
            reason = "FORCE_CPU=1" if os.environ.get("FORCE_CPU") == "1" \
                else "no usable CUDA device"
            print(f"[generation] loading {model_id} on CPU (fp32, {reason})")
            self.model = AutoModelForCausalLM.from_pretrained(
                model_id, dtype=torch.float32,
            )
            self.model.to("cpu")

        self.model.eval()

    def generate(self, prompt):
        torch = self.torch
        inputs = self.tokenizer(
            prompt, return_tensors="pt", truncation=True,
            max_length=self.max_input_tokens,
        )
        device = next(self.model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        kwargs = {
            "max_new_tokens": self.max_new_tokens,
            "pad_token_id": self.tokenizer.eos_token_id,
        }
        if self.do_sample:
            kwargs.update({
                "do_sample": True,
                "temperature": self.temperature,
                "top_p": self.top_p,
            })
        else:
            kwargs.update({"do_sample": False})

        t0 = time.perf_counter()
        with torch.inference_mode():
            out = self.model.generate(**inputs, **kwargs)
        elapsed = time.perf_counter() - t0

        generated = self.tokenizer.decode(
            out[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )
        return {
            "model_id": self.model_id,
            "model_revision": getattr(
                self.model.config, "_name_or_path", None
            ),
            "prompt_sha256": sha256_text(prompt),
            "output_sha256": sha256_text(generated),
            "prompt": prompt,
            "output": generated,
            "timestamp": now_iso(),
            "latency_seconds": elapsed,
            "generation_config": {
                "max_input_tokens": self.max_input_tokens,
                "max_new_tokens": self.max_new_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "do_sample": self.do_sample,
                "device": "cuda" if self.use_cuda else "cpu",
            },
        }


def make_generator(model_id, **kwargs):
    if model_id == "synthetic":
        return SyntheticGenerator(model_id=model_id, **kwargs)
    return LocalHFGenerator(model_id, **kwargs)


def run_generation(benchmark_path, out_path, model_id, limit=None, **kwargs):
    gen = make_generator(model_id, **kwargs)
    rows = []
    for i, task in enumerate(read_jsonl(benchmark_path)):
        if limit is not None and i >= limit:
            break
        g = gen.generate(task["prompt"])
        g["task_id"] = task["task_id"]
        g["ecosystem"] = task["ecosystem"]
        g["scenario"] = task["scenario"]
        g["target_package"] = task["target_package"]
        g["target_version"] = task.get("target_version")
        rows.append(g)
        print(f"[{i+1}] {task['task_id']} {g['latency_seconds']:.4f}s",
              flush=True)
    write_jsonl(out_path, rows)
