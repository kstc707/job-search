# Gemma 4 Developer Agent: Paper Track Entry Plan

**Competition:** [Google – The Gemma 4 Developer Agent Paper Track](https://www.kaggle.com/competitions/gemma-4-developer-agent-paper)

- **Deadline: 2026-11-12 23:59 UTC.** That is also the last day to join the track. As of 2026-10-13, 30 days remain.
- **Setup:** solo, using Kaggle's free GPUs (2× T4, roughly 30 GPU-h per week).
- **Direction:** a thinking-budget study (chosen 2026-10-13).

> These facts come from public notes by another team ([usp787/Gemma4_paper_track](https://github.com/usp787/Gemma4_paper_track), read 2026-10-13), because Kaggle can't be reached from this environment. **Read the official Overview, Rules and forum on Kaggle before relying on any detail below.**

## 1. Rules that shape the plan

- **Writeup:** at most **3,000 words**. Count the title, abstract, captions and references until the host says otherwise.
  - Required sections: abstract, introduction, methods and experiments, related work.
  - Optional: a public notebook, and an arXiv-style PDF link.
- **Judging:** five criteria, each scored 0–5 and equally weighted.
  - **Novelty:** a new insight.
  - **Quality:** generality beyond the competition.
  - **Relevance:** impact on software engineering and agentic learning.
  - **Verifiability:** enough detail to see how the work was done.
  - **Clarity:** how well it's written.
- **Prizes:** Best Paper $15k, Best New Resource $10k, Best New Application $10k.
  - At most 2 writeups per team, and each can win at most one award.
- **Writing:** write the text yourself. The host said "purely LLM-generated slop will not score well", while light LLM editing is fine.
- **Code release:** winners must release their code under Apache-2.0 (or another OSI license that allows commercial use).
  - Release scripts, not competition data. Rule 2.4 forbids redistributing it.

## 2. The paper

**Working title:** *How Much Should a Local Coding Agent Think? Thinking Budgets, Model Size and Wall-Clock on Consumer GPUs*

**Why this is open:**
- **The competition's premise:** an agent that works offline on everyday hardware.
- **Forum evidence for Gemma 4 31B on an H200:**
  - Thinking takes 65–71% of agent time.
  - With thinking off, about 50% of tool calls repeat an earlier call and about 24% are malformed (with thinking on: 9% and 2%).
  - A malformed call follows a malformed call 92% of the time with thinking off.
- **What's missing:** that evidence is on/off only, for one model size, on datacenter hardware. Nobody has published:
  1. **Intermediate budgets:** what happens between off and unlimited.
  2. **Model size:** whether the effect changes with size (E4B vs. 26B-A4B MoE vs. 31B dense).
  3. **Speed vs. smarts:** which combination of model and budget resolves the most tasks **per wall-clock minute on consumer GPUs**, where thinking time is expensive.
- **Mixed external evidence makes the question real:**
  - NetConfArena: thinking helped Qwen3-8B but hurt Qwen3-32B on invalid actions.
  - "The Danger of Overthinking" (arXiv 2502.08235): more internal reasoning meant fewer resolved issues, yet o1 gained from more effort.

**Research questions:**
- **RQ1 (budget × size):** how does the resolve rate change with the thinking budget {0, 256, 1024, 4096, unlimited} for E4B, 26B-A4B and 31B?
- **RQ2 (mechanism):** does thinking help mainly by preventing malformed and repeated tool calls?
  - Measure the malformed share, the repeat share, and P(malformed | previous malformed) at each budget.
  - Check how much of the resolve gain follows those.
- **RQ3 (consumer hardware):** with a fixed wall-clock cap per task on 2× T4, which (size, budget) pair is Pareto-optimal?
- **RQ4 (cheap fix, optional):** can tool-argument rules plus a repeat-call guard recover most of thinking's gain at a budget of 0?
  - The guard tells the agent "you already ran this; here is the earlier result".
  - Thinking time is then spent only where it pays.

**Novelty risk:**
- The usp787 team listed a thinking-budget study as their fallback, and on 2026-10-12 moved toward a loop study.
- Our differentiators: the **model-size axis**, **intermediate budgets via budget forcing**, and **consumer-GPU wall-clock**.
- Check the forum weekly for overlap.

## 3. Method

- **Serving:** llama.cpp `llama-server` with Q4_K_M GGUF weights on Kaggle's 2× T4.
  - vLLM's int4 Marlin kernels need compute capability ≥ 8.0, and the T4 is 7.5.
- **Budget forcing:** `thinkbudget/budget.py`.
  - The model thinks for at most N tokens. If the thought isn't finished by then, we append a short wrap-up line and the end-of-thinking marker, then let it answer (as in the s1 paper, arXiv 2501.19393).
  - Budget 0 means thinking is switched off in the chat template.
  - Unlimited means no cap.
- **Agent:** prefer the main competition's starter harness if it can point at an OpenAI-compatible local server. Otherwise build a minimal agent.
  - Tools: `grep`, `read_file`, `edit_file`, `run_tests`, `submit`.
  - Limits: at most 40 steps and a 32k context.
- **Tasks:** about 60 of the 129 public tasks, stratified across fastapi, rich and requests. Use only tasks whose gold patch passes in our runner.
- **Generality check** (for the Quality score):
  - Submit 31B with thinking off, at 1024 and unlimited to the **main track**. Kaggle scores it on about 120 hidden tasks from private repositories.
  - This is free out-of-distribution evaluation on Kaggle's hardware. The main track requires 31B only, so join it too; its entry deadline is Nov 25.
- **Metrics:** `thinkbudget/metrics.py`.
  - Resolve rate, with paired McNemar tests and bootstrap CIs.
  - Malformed share, repeat share, and the conditional malformed rate.
  - Thinking-token share, and wall-clock per task.
  - Seeds: 2 for the main cells, 1 for ablations.

## 4. Compute budget (to fix after the feasibility spike)

- **Quota:** about 30 GPU-h per week for 4 weeks. Plan on about 90 usable hours.

| Cell | Tasks × budgets × seeds | Est. min/run | GPU-h |
|---|---|---|---|
| E4B | 60 × 5 × 2 | ~3 | 30 |
| 26B-A4B | 60 × 5 × 1 (+1 seed on 3 budgets) | ~5 | 40 |
| 31B | 30 × 3 × 1 | ~10 | 15 |
| RQ4 guard | 60 × 2 × 1 on 26B-A4B | ~4 | 8 |

- **The per-run times are guesses.** The feasibility notebook measures real decode and prefill speeds. If they're slower, cut tasks before cutting seeds.
- **Wall-clock cap:** 20 min per task. Hitting it counts as a failure, and that is part of RQ3.

## 5. Timeline

| Dates | Deliverable |
|---|---|
| **Oct 13–14** | Join **both** tracks, verify identity, accept the rules. Create and **save an empty Writeup**, since an editor save bug was reported. Turn on Internet and phone verification on Kaggle. Run `notebooks/01_feasibility_kaggle.py`. Download the main competition's data and starter code. |
| Oct 15–19 | Agent harness and test runner in a Kaggle notebook. Validate gold patches on the 60-task subset. Pilot 10 tasks on E4B at all budgets. |
| **Oct 20** | **Go/no-go.** Pass if the pilot shows the behavioural metrics moving with the budget and runs fit the time estimates. If not, drop 31B to main-track submissions only, and narrow to E4B and 26B-A4B. |
| Oct 20–Nov 1 | Sweeps, scheduled around the weekly quota reset. Main-track submissions for 31B. RQ4 guard runs. |
| Nov 1–4 | Analysis and figures: the budget × size curves, the Pareto plot, and a behaviour-vs-resolve breakdown. |
| Nov 3–6 | You write the draft (≤3,000 words) and publish the public notebook and repo. **Submit a complete v1 by Nov 6.** |
| Nov 7–11 | Revise for clarity, add citations and recheck the numbers. Get an outside reader, such as the ML course instructor. |

## 6. Related work to cite

- s1: simple test-time scaling / budget forcing (arXiv 2501.19393)
- "The Danger of Overthinking" (arXiv 2502.08235)
- NetConfArena (arXiv 2608.23179)
- SWE-bench and SWE-agent (the agent-computer interface)
- The competition forum threads with the 31B thinking on/off numbers. Cite them as observations, and re-measure them ourselves.

## 7. Open items for Sai

- [ ] Join both tracks on Kaggle and complete identity verification and phone verification.
- [ ] Run the feasibility notebook and paste back `feasibility.json`.
- [ ] Copy the main competition's Data page and starter-notebook description here, so the harness can be wired to them.
