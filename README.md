# vram16-measured — an agent skill that only recommends what was actually measured

日本語の説明: [README.ja.md](README.ja.md)

Ask your AI agent (Claude Code, Codex, Cursor and other tools that read `SKILL.md`) to *"make a product photo on my PC"* or *"will FLUX run on my RTX 4060?"*.
Instead of guessing, it reads your GPU and system RAM, picks from **real runs measured by [vram16.ullu-egg.com](https://vram16.ullu-egg.com/en/)**, and can run the exact ComfyUI workflow that was measured.

## What it knows

- **45 models, 383 measured runs** on an RTX 5080 16GB (image, edit, upscale, video, speech, music, local LLM) — seconds, peak VRAM, licence, failures
- **8GB- and 12GB-class runs** for popular image models and one video model (Wan 2.2 TI2V 5B, 5 s: text-to-video at 832×480 and 1280×704, image-to-video at 1280×704), measured with VRAM capped to 7GiB / 11GiB ([how](https://vram16.ullu-egg.com/en/feature/small-gpu-2026-10/)). It tells you when *system RAM*, not VRAM, is what stops you
- **76 workflows** (ComfyUI API format) that were re-rendered pixel-identical before publishing
- Licences quoted from the licence text, so a "research only" model is never offered for commercial work

## What it will not do

- Invent a number. If nothing was measured for your card, it says *not measured*.
- Recommend fp4 settings on cards that cannot run them fast (anything before RTX 50).
- Download multi-GB weights without asking.

## Example (RTX 4060 8GB, 16GB RAM, text→image)

```
$ python scripts/pick.py --task t2i --vram 8 --gpu-name "RTX 4060" --ram 16 --top 3
1. Z-Image Turbo — int8 1024×1024: 5.18 s, 1st run incl. loading 14.95 s, peak VRAM 7.2 GB | commercial: yes (Apache License 2.0)
   basis: measured with VRAM capped to the 8GB class (runs or not carries over; times are at RTX 5080 speed, a real card is slower)
   system RAM: TIGHT: loading added 9.5GB of system RAM in the test; you have 16.0GB. Close other apps, or pick another
   ...
   skipped: FLUX.1 dev fp8: STOPPED at the 8GB level — stopped while loading: system RAM rose by about 32.0GB ...
```

## Your PC's own seconds

The measured seconds are from the test PC. Run one measured workflow three times on your PC and the picker will tell you every other pick in *your* seconds:

```
python scripts/run_comfy.py --workflow https://vram16.ullu-egg.com/workflows/sd3.5-large-turbo_1024.json --calibrate
python scripts/pick.py --task t2i
   ...
   on YOUR PC: ≈ 2.3–2.6 s  (ESTIMATE from your run(s) of HiDream-O1 Image Dev, Stable Diffusion 3.5; speed ×1.06–×1.22 vs the measured runs)
```

The ratio stays on your PC (`~/.vram16-measured/calibration.json`). It is only used for the same task and the same GPU. On an 8GB/12GB card it is taken against the run measured with VRAM capped to your class, so it measures compute speed, not offloading.

## Install

Copy this folder into your agent's skills folder (for Claude Code: `~/.claude/skills/vram16-measured/`). Python 3.9+ only; no packages needed. `run_comfy.py` needs a running ComfyUI.

## How the numbers were taken

Generation time is the average of the 2nd and 3rd image after the model is loaded (the prompt changes each time, so the text encoder runs again). The 1st image including loading is reported separately. Details: [How we measure](https://vram16.ullu-egg.com/en/about/).

## Licence

Code: MIT. Data (`data/measured.json`): CC BY 4.0 — credit "vram16.ullu-egg.com".
