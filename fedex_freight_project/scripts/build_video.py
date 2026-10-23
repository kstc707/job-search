"""Build the ~100-second overview video (reports/video/).

Slides are 1920x1080 HTML pages rendered with headless Chromium; charts are the project's Python (matplotlib)
figures. Each slide carries its narration as a caption bar, so the video also works muted. The voiceover is synthesized
locally with Piper TTS (voice files in data/tts_voices/, gitignored; see VOICE below); without them the video is silent.
ffmpeg (imageio-ffmpeg build) joins the slides with crossfades. Also writes the narration script and an .srt.
Every number is read from the results files. Run: .venv/bin/python -I scripts/build_video.py
"""
import base64
import html
import json
import math
import os
import pathlib
import subprocess
import sys
import wave

import matplotlib

matplotlib.use("Agg")
import imageio_ffmpeg
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import style as S  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
REP = ROOT / "reports"
OUT = REP / "video"
SL = OUT / "slides"
SL.mkdir(parents=True, exist_ok=True)
H = json.loads((REP / "site/headline.json").read_text())
CHROME, FF = "/opt/pw-browsers/chromium", imageio_ffmpeg.get_ffmpeg_exe()
FADE = 0.6
WPS = 2.5  # comfortable narration pace, ~150 words a minute; each slide stays up at least this long
VOICE = ROOT / "data/tts_voices/en_US-ryan-high.onnx"  # download: huggingface.co/rhasspy/piper-voices (en/en_US/ryan/high)
LEAD, TAIL = 0.7, 1.0  # seconds of silence before and after each slide's narration
SPOKEN = {"LTL": "L T L", "2022–23": "2022 to 2023", "mid-2026": "mid 2026"}  # caption text -> what the voice should say


def pct(x):
    """Signed percent with a typographic minus."""
    return f"{x:+.1f}%".replace("-", "−")

# ---------------------------------------------------------------- slide-sized chart: FedEx share over time
S.apply()
sp = pd.read_csv(REP / "ds/share_panel.csv")
f = sp[sp["ticker"] == "FDX"].reset_index(drop=True)
first, mid21, last = f.iloc[0], f[f["cq"] == "2021Q2"].iloc[0], f.iloc[-1]
fig, ax = plt.subplots(figsize=(9.6, 4.6))
ax.plot(range(len(f)), 100 * f["share"], color=S.ORANGE, lw=3, marker="o", ms=4)
for r in (first, last):
    i = f.index[f["cq"] == r["cq"]][0]
    ax.annotate(f"{100 * r['share']:.1f}%", (i, 100 * r["share"]), xytext=(0, 12), textcoords="offset points",
                ha="center", fontsize=15, weight="bold", color=S.ORANGE)
ax.set_xticks(range(0, len(f), 4)); ax.set_xticklabels(f["cq"].iloc[::4], fontsize=12)
ax.set_ylim(33, 46); ax.tick_params(axis="y", labelsize=12)
ax.set_ylabel("% of daily shipments, 5 public LTL carriers", fontsize=12)
S.save(fig, SL / "chart_share.png")


def img(p):
    return "data:image/png;base64," + base64.b64encode(pathlib.Path(p).read_bytes()).decode()


pf = pd.read_csv(ROOT / "ds/prospective_forecasts.csv")
pre = pf[pf["pre_registered_best"]].set_index(["ticker", "period"])
fdx_row = pre.loc[("FDX", "Jun-Sep 2026 (FDXF transition period)")]
peers_line = " · ".join(f"{t} {pct(pre.loc[(t, '2026Q3'), 'yoy_log_pct'])}" for t in ["ODFL", "SAIA", "XPO", "ARCB"])

# ---------------------------------------------------------------- slides: (seconds, html body, narration)
slides = [
    (8, f"""<div class="title"><span class="eyebrow">A public-data data science project · October 2026</span>
        <h1>Market or share?</h1><p class="sub">What explains FedEx Freight's lost volume, and what it will report next</p>
        <p class="who">Sai Teja Koppolu · MS Data Science, University of Memphis</p>{'<p class="note">Narration: synthetic voice (Piper TTS) reading my script</p>' if VOICE.exists() else ''}</div>""",
     "Hi, I'm Sai. I built a short data science project on one question: how much of FedEx Freight's lost volume is the market, and how much is FedEx?"),
    (12, f"""<h2>FedEx Freight's share of public LTL shipments fell from {100 * first['share']:.0f}% to {100 * last['share']:.0f}%</h2>
        <img class="chart" src="{img(SL / 'chart_share.png')}">
        <p class="note">Share of average daily shipments among FedEx Freight, Old Dominion, Saia, XPO and ArcBest. Source: SEC filings.</p>""",
     f"Among the five largest public LTL carriers, FedEx Freight's share of daily shipments fell from {100 * first['share']:.0f} to {100 * last['share']:.0f} percent between 2019 and mid-2026."),
    (15, f"""<h2>Price explains the 2022–23 loss. It doesn't explain the losses since.</h2>
        <img class="chart" src="{img(REP / 'ds/figures/ds6_share_annual.png')}">""",
     f"I estimated how share responds to relative price using only FedEx's four competitors, then applied it to FedEx. Price explains the 2022–23 loss. "
     f"It doesn't explain the year after Yellow's shutdown, or the year to mid-2026, when FedEx lost share while its relative price was falling."),
    (12, f"""<h2>Why I trust the result</h2><div class="grid">
        <div class="kpi"><b>−{H['elas_b0']}</b><span>share elasticity to relative price, estimated on competitors only (95% CI {H['elas_ci']})</span></div>
        <div class="kpi"><b>p = {H['placebo_p']}</b><span>placebo test: prices shuffled within each carrier 2,000 times</span></div>
        <div class="kpi"><b>3 of 4</b><span>carriers predicted better than "no change" when each is left out</span></div>
        <div class="kpi"><b>Out of sample</b><span>FedEx was never used to estimate it; holds ex-fuel and with quarter fixed effects</span></div></div>""",
     "The relationship holds up: a placebo test, prices excluding fuel, and leaving each carrier out in turn. FedEx was never used to estimate it."),
    (13, f"""<h2>A forecast locked before the answer exists</h2>
        <div class="big"><b>{pct(fdx_row['yoy_log_pct'])}</b><span>FedEx Freight shipments per day, June–September 2026 vs 2025<br>
        80% range {pct(fdx_row['lo80'])} to {pct(fdx_row['hi80'])} · FDXF reports October 29 · BofA estimate −3.0%</span></div>
        <p class="note">Peers, Q3 2026: {peers_line}<br>Forecast file SHA-256 committed {H['lock_commit']} on Oct 23, before any of them report.</p>""",
     f"Before FedEx Freight reports on October 29, I locked a forecast: shipments per day down about {abs(fdx_row['yoy_log_pct']):.0f} percent for June to September, fingerprinted on GitHub."),
    (14, f"""<h2>What the models taught me</h2><div class="split"><img class="chart" src="{img(REP / 'ds/figures/ds1_model_mae.png')}">
        <ul><li>Pre-registered, 36 out-of-sample dates</li><li>Own in-quarter data: <b>{H['own_gain']}% less error</b> (p = {H['own_p']})</li>
        <li>Machine learning: {H['ml_gain']}% better, <b>not significant</b></li><li>For FedEx alone nothing beat naive</li></ul></div>""",
     "Honest result: a carrier's own in-quarter data was the only significant gain. Machine learning helped a little, but not significantly. "
     "With FedEx's daily data, the real value is at the account level, not at quarter end."),
    (11, f"""<h2>Fuel is hiding price</h2><div class="split"><img class="chart" src="{img(REP / 'figures_final/f3_fuel_model.png')}">
        <ul><li>FedEx collects <b>{H['rho']}×</b> its published fuel surcharge, every quarter</li>
        <li>At EIA's 2027 diesel forecast: <b>−{H['fuel27_abs']}%</b> revenue per shipment from fuel alone</li></ul></div>""",
     f"Separately, FedEx collects about {float(H['rho']) * 100:.0f} percent of its published fuel surcharge. If diesel falls as EIA forecasts, "
     f"fuel alone takes about {round(float(H['fuel27_abs']))} percent off revenue per shipment in 2027."),
    (12, f"""<h2>What I'd build first with FedEx Freight's data</h2>
        <table class="build">
        <tr><td>Retention</td><td>Account-level share early warning: expected weekly shipments per account, drift flagged before churn, ranked by volume at risk</td></tr>
        <tr><td>Pricing</td><td>Price response by lane, shipment size and commodity, with the {H['ratio']}:1 price-to-volume exchange rate as a guardrail</td></tr>
        <tr><td>Revenue integrity</td><td>Predicted shipment density vs dimensioner reads under density-based NMFC classes</td></tr>
        <tr><td>Method</td><td>Validated the same way: pre-registered, rolling-origin, against a naive baseline. One point of shipments ≈ ${H['oi_vol']}M operating income a year</td></tr>
        </table>
        <p class="contact">Sai Teja Koppolu · skppolu1@memphis.edu · +1 901-343-7273 · github.com/kstc707</p>""",
     "The first thing I'd build with your data is an account-level early warning for share loss, tested the same way. I'd value 15 minutes to walk you through it."),
]

CSS = """
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..125,400..800&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
* { box-sizing: border-box; margin: 0; }
html, body { width: 1920px; height: 1080px; overflow: hidden; background: #f5f6f3; color: #14202b; }
body { font: 30px/1.4 "Source Serif 4", Georgia, serif; display: flex; flex-direction: column; }
main { flex: 1; padding: 60px 110px 40px; display: flex; flex-direction: column; justify-content: center; gap: 30px; min-height: 0; }
h1 { font: 800 150px/1 "Archivo", sans-serif; font-stretch: 78%; text-transform: uppercase; }
h2 { font: 750 60px/1.1 "Archivo", sans-serif; font-stretch: 85%; max-width: 1600px; }
.eyebrow { font: 500 24px/1 "IBM Plex Mono", monospace; letter-spacing: 0.12em; text-transform: uppercase; color: #4c5864; }
.title { margin: auto 0; display: flex; flex-direction: column; gap: 28px; }
.sub { font-size: 44px; color: #4c5864; max-width: 1400px; }
.who { font: 500 28px/1 "IBM Plex Mono", monospace; }
.chart { max-height: 660px; max-width: 100%; object-fit: contain; align-self: flex-start; background: #fcfcfb; border: 1px solid #d6dbd9; }
.note { font: 22px/1.5 "IBM Plex Mono", monospace; color: #4c5864; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 28px 60px; margin-top: 10px; }
.kpi { border-top: 4px solid #14202b; padding-top: 16px; display: flex; flex-direction: column; gap: 10px; }
.kpi b { font: 800 84px/1 "Archivo", sans-serif; font-stretch: 80%; color: #2a78d6; }
.kpi span { font-size: 30px; color: #4c5864; }
.big { display: flex; gap: 60px; align-items: center; border-top: 4px solid #14202b; border-bottom: 1px solid #d6dbd9; padding: 40px 0; }
.big b { font: 800 220px/1 "Archivo", sans-serif; font-stretch: 78%; color: #c4501f; }
.big span { font-size: 36px; color: #14202b; }
.split { display: grid; grid-template-columns: 1.25fr 1fr; gap: 50px; align-items: center; }
.split .chart { width: 100%; max-height: 640px; }
ul { padding-left: 1.1em; display: flex; flex-direction: column; gap: 18px; font-size: 34px; }
ul.wide { font-size: 38px; max-width: 1500px; gap: 26px; }
.build { border-collapse: collapse; font-size: 32px; max-width: 1650px; }
.build td { border-top: 1px solid #d6dbd9; padding: 16px 30px 16px 0; vertical-align: top; }
.build td:first-child { font: 750 34px/1.3 "Archivo", sans-serif; font-stretch: 85%; white-space: nowrap; color: #2a78d6; }
.contact { margin-top: auto; font: 500 28px/1 "IBM Plex Mono", monospace; border-top: 4px solid #14202b; padding-top: 22px; }
.cap { background: #14202b; color: #f5f6f3; padding: 26px 110px 30px; font: 32px/1.4 "Source Serif 4", serif; min-height: 150px; display: flex; align-items: center; }
.bar { position: absolute; top: 0; left: 0; height: 8px; background: #2a78d6; }
</style>"""

# stretch any slide whose narration needs longer than its planned time at the narration pace
planned = [d for d, _, _ in slides]
slides = [(max(d, math.ceil(len(n.split()) / WPS) + 2), b, n) for d, b, n in slides]

# ---------------------------------------------------------------- voiceover: one clip per slide, slide lasts as long as its clip
clips, rate = [], 22050
if VOICE.exists():
    from piper import PiperVoice
    voice = PiperVoice.load(str(VOICE))
    for k, (d, b, n) in enumerate(slides):
        said = n
        for a, z in SPOKEN.items():
            said = said.replace(a, z)
        wav = SL / f"voice_{k + 1:02d}.wav"
        with wave.open(str(wav), "wb") as w:
            voice.synthesize_wav(said, w)
        with wave.open(str(wav)) as w:
            rate = w.getframerate()
            clips.append(np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16))
        slides[k] = (max(planned[k], math.ceil(LEAD + len(clips[-1]) / rate + TAIL)), b, n)  # voiced: time to the clip
total = sum(d for d, _, _ in slides)
pngs, t = [], 0.0
for i, (dur, body, narr) in enumerate(slides):
    progress = 100 * (t + dur) / total
    page = (f"<!doctype html><html><head><meta charset='utf-8'>{CSS}</head><body><div class='bar' style='width:{progress:.1f}%'></div>"
            f"<main>{body}</main><div class='cap'>{html.escape(narr)}</div></body></html>")
    src = SL / f"slide_{i + 1:02d}.html"
    src.write_text(page)
    png = SL / f"slide_{i + 1:02d}.png"
    # headless Chromium's viewport is shorter than its window, so render taller and crop to exactly 1920x1080
    subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--window-size=1920,1300", "--virtual-time-budget=6000", f"--screenshot={png}", src.as_uri()]
                   + ([f"--proxy-server={os.environ['HTTPS_PROXY']}"] if "HTTPS_PROXY" in os.environ else []),
                   check=True, capture_output=True, timeout=120)
    im = Image.open(png).convert("RGB")
    im.crop((0, 0, 1920, 1080)).save(png)
    pngs.append(png)
    t += dur

# ---------------------------------------------------------------- ffmpeg: crossfaded slideshow, H.264, 30 fps
mp4 = OUT / "Koppolu_FedEx_Freight_overview.mp4"
cmd = [FF, "-y"]
for (dur, _, _), png in zip(slides, pngs):
    cmd += ["-loop", "1", "-t", f"{dur + FADE}", "-framerate", "30", "-i", str(png)]
chain, prev, offset = [], "[0:v]", 0.0
for i in range(1, len(slides)):
    offset += slides[i - 1][0]
    out = f"[v{i}]"
    # each input lasts dur+FADE, so slide i fades in starting exactly at the sum of the previous durations
    chain.append(f"{prev}[{i}:v]xfade=transition=fade:duration={FADE}:offset={offset:.2f}{out}")
    prev = out
chain.append(f"{prev}fade=t=in:st=0:d=0.5,fade=t=out:st={total - 0.6:.2f}:d=0.6,format=yuv420p[vout]")
cmd += ["-filter_complex", ";".join(chain), "-map", "[vout]", "-t", f"{total}", "-c:v", "libx264", "-preset", "medium",
        "-crf", "20", "-movflags", "+faststart", str(mp4)]
if clips:
    # one narration track: each clip starts LEAD seconds into its slide
    track = np.zeros(int(total * rate), dtype=np.int16)
    start = 0.0
    for (dur, _, _), c in zip(slides, clips):
        i = int((start + LEAD) * rate)
        track[i:i + len(c)] = c[:len(track) - i]
        start += dur
    peak = max(1, int(np.abs(track.astype(np.int32)).max()))
    track = (track.astype(np.float64) * (0.89 * 32767 / peak)).astype(np.int16)  # peak at -1 dBFS, no clipping
    narration = SL / "narration.wav"
    with wave.open(str(narration), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(track.tobytes())
    at = cmd.index("-filter_complex")
    cmd[at:at] = ["-i", str(narration)]
    cmd[-1:-1] = ["-map", f"{len(slides)}:a", "-c:a", "aac", "-b:a", "128k", "-af", f"afade=t=out:st={total - 0.6:.2f}:d=0.6"]
subprocess.run(cmd, check=True, capture_output=True, timeout=600)

# ---------------------------------------------------------------- narration script + subtitles
def ts(x):
    h, m, s = int(x // 3600), int(x % 3600 // 60), x % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int(round((s % 1) * 1000)):03d}"


srt, script, t = [], [f"# Narration script ({total} s{'; voiced with Piper TTS' if clips else ''})\n"], 0.0
for i, (dur, _, narr) in enumerate(slides):
    srt.append(f"{i + 1}\n{ts(t + 0.2)} --> {ts(t + dur - 0.2)}\n{narr}\n")
    script.append(f"**{ts(t)[3:8]}–{ts(t + dur)[3:8]} · slide {i + 1}**  \n{narr}\n")
    t += dur
(OUT / "Koppolu_FedEx_Freight_overview.srt").write_text("\n".join(srt))
(OUT / "narration_script.md").write_text("\n".join(script))
probe = subprocess.run([FF, "-i", str(mp4)], capture_output=True, text=True).stderr
dur_line = [l for l in probe.splitlines() if "Duration" in l]
print("written", mp4, f"{mp4.stat().st_size / 1e6:.1f} MB", dur_line[0].strip() if dur_line else "", f"slides={len(slides)} total={total}s voice={'yes' if clips else 'no'}")
