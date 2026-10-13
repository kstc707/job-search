# %% [markdown]
# # Day-1 feasibility spike (Kaggle, GPU T4 x2, Internet ON)
#
# Answers the four questions the whole plan depends on:
# 1. Does each Gemma 4 size load on 2x T4, and at what decode / prefill speed?
# 2. What are the exact thinking markers in Gemma 4's chat template?
# 3. How is thinking switched off in the template (which kwarg)?
# 4. Does budget forcing (thinkbudget/budget.py) produce sane output?
#
# Run each cell top to bottom and paste `feasibility.json` plus the printed template snippets back.
# Weekly GPU quota is limited: the build takes ~15 min, and each model ~10 min.

# %%
import json, os, re, subprocess, sys, time, urllib.request

# VERIFY these repo ids on huggingface.co before running. Use a Q4_K_M quant for all sizes.
MODELS = {
    "E4B":     ("unsloth/gemma-4-E4B-it-GGUF",     "*Q4_K_M*.gguf"),
    "26B-A4B": ("unsloth/gemma-4-26B-A4B-it-GGUF", "*Q4_K_M*.gguf"),
    "31B":     ("unsloth/gemma-4-31B-it-GGUF",     "*Q4_K_M*.gguf"),
}
CTX = 32768
PORT = 8080
BASE = f"http://127.0.0.1:{PORT}"
WORK = "/kaggle/working"

# %%  Build llama.cpp for T4 (compute capability 7.5).
if not os.path.exists("/kaggle/temp/llama.cpp/build/bin/llama-server"):
    subprocess.run("git clone --depth 1 https://github.com/ggml-org/llama.cpp /kaggle/temp/llama.cpp", shell=True, check=True)
    subprocess.run(
        "cd /kaggle/temp/llama.cpp && cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=75 "
        "-DLLAMA_CURL=OFF && cmake --build build -j --target llama-server",
        shell=True, check=True,
    )
SERVER = "/kaggle/temp/llama.cpp/build/bin/llama-server"

# %%
from huggingface_hub import snapshot_download


def post(path, payload, timeout=900):
    req = urllib.request.Request(BASE + path, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def start_server(gguf):
    proc = subprocess.Popen(
        [SERVER, "-m", gguf, "-ngl", "99", "-c", str(CTX), "--port", str(PORT), "--jinja",
         "--split-mode", "layer", "-fa", "on"],
        stdout=open(f"{WORK}/server.log", "w"), stderr=subprocess.STDOUT,
    )
    for _ in range(600):
        try:
            if get("/health").get("status") == "ok":
                return proc
        except Exception:
            pass
        if proc.poll() is not None:
            raise RuntimeError(open(f"{WORK}/server.log").read()[-3000:])
        time.sleep(2)
    raise TimeoutError("server did not become healthy")


# %%
MESSAGES = [
    {"role": "system", "content": "You are a coding agent. Reply with exactly one tool call as JSON."},
    {"role": "user", "content": "Find where `parse_header` is defined in the repo. Tools: grep(pattern), read(path)."},
]
FILLER = "def f_{i}(x):\n    return x + {i}\n\n"
results = {}

for name, (repo, pattern) in MODELS.items():
    path = snapshot_download(repo, allow_patterns=[pattern], local_dir=f"/kaggle/temp/{name}")
    gguf = sorted(os.path.join(dp, f) for dp, _, fs in os.walk(path) for f in fs if f.endswith(".gguf"))[0]
    proc = start_server(gguf)
    try:
        r = {"gguf": os.path.basename(gguf)}
        # Template: rendered with and without the likely thinking switches.
        for label, kwargs in [("default", {}), ("think_on", {"enable_thinking": True}),
                              ("think_off", {"enable_thinking": False})]:
            try:
                r[f"template_{label}"] = post("/apply-template", {"messages": MESSAGES, "chat_template_kwargs": kwargs})["prompt"]
            except Exception as e:
                r[f"template_{label}"] = f"ERROR {e}"
        props = get("/props")
        tmpl = props.get("chat_template", "")
        r["template_think_lines"] = [l for l in tmpl.splitlines() if re.search(r"think|thought|reason", l, re.I)][:40]

        # Free generation, so we can see the raw thinking markers the model emits.
        out = post("/completion", {"prompt": r["template_think_on"], "n_predict": 512, "temperature": 0.6, "seed": 0})
        r["sample_output"] = out["content"]
        r["decode_tok_s"] = out["timings"]["predicted_per_second"]

        # Prefill speed at agent-like context length (~8k tokens).
        long_prompt = "".join(FILLER.format(i=i) for i in range(700)) + "\n# Summarize the functions above in one line.\n"
        out = post("/completion", {"prompt": long_prompt, "n_predict": 16, "cache_prompt": False})
        r["prefill_tokens"] = out["timings"]["prompt_n"]
        r["prefill_tok_s"] = out["timings"]["prompt_per_second"]
        r["vram"] = subprocess.run("nvidia-smi --query-gpu=memory.used --format=csv,noheader", shell=True,
                                   capture_output=True, text=True).stdout.strip().splitlines()
        results[name] = r
        print(name, {k: v for k, v in r.items() if not k.startswith("template") and k != "sample_output"})
        print("--- sample output ---\n", r["sample_output"][:1500])
    except Exception as e:
        results[name] = {"error": repr(e), "log_tail": open(f"{WORK}/server.log").read()[-2000:]}
        print(name, "FAILED", e)
    finally:
        proc.terminate(); proc.wait()

json.dump(results, open(f"{WORK}/feasibility.json", "w"), indent=2)

# %% [markdown]
# ## After the run
# - Copy the thinking start/end markers from `sample_output` and the template lines into
#   `thinkbudget.budget.ThinkMarkers`.
# - Decision rule: a model is usable for the sweep if decode is >= 8 tok/s and prefill is >= 300 tok/s
#   at 8k tokens. If 31B misses this, it runs on a subset only, plus main-track submissions.
