---
name: vram16-measured
description: Pick and run a local generative AI model (image, video, voice, music, LLM) that is proven to fit the user's own GPU and system RAM, using only real measurements from vram16.ullu-egg.com (RTX 5080 16GB, 380+ measured runs, plus 8GB/12GB-class runs under a VRAM cap; workflows re-rendered pixel-identical). Use when the user wants to generate images/video/audio locally, asks "will X run on my GPU / my RTX 4060 / 8GB / 12GB", "which model for my PC", or wants ComfyUI to make something without the cloud.
---

# Measured local generation

You answer with **measured numbers only**. Every number comes from a run on an RTX 5080 (16GB VRAM, 64GB RAM, Windows, ComfyUI portable), some of them with VRAM capped to 7GiB / 11GiB to act as an 8GB / 12GB card. Never invent a time or VRAM figure. If nothing was measured for the user's case, say "not measured" and link https://vram16.ullu-egg.com/en/ — do not say it will or won't run.

## Steps

1. Work out the task code from the request:
   `t2i` text→image · `edit` image edit · `rmbg` background removal · `upscale` · `t2v` text→video · `i2v` image→video · `av` video with audio · `tts` speech · `clone` voice clone · `song` song · `t2m` music · `sep` stem split · `asr` speech→text · `chat`/`code`/`reasoning` local LLM
2. Run the picker. On the user's own PC it reads the GPU (nvidia-smi) and system RAM itself:
   ```
   python scripts/pick.py --task t2i [--commercial] [--comfy-dir <ComfyUI folder>]
   ```
   - Asking for another PC (e.g. "I'm buying an RTX 4060 with 32GB"): add `--vram 8 --gpu-name "RTX 4060" --ram 32`.
   - Add `--commercial` if the user will sell or publish the output. Non-commercial models are then excluded and listed as skipped.
   - Add `--comfy-dir` when ComfyUI is installed: it reports which weight files the chosen workflow still needs.
3. Show the user the top 2–3 picks as: model, setting, **seconds and peak VRAM as measured**, licence (commercial yes/no), the `basis` line, and the source article URL. Also show anything in `skipped` that the user asked about by name (a STOPPED line is a real failure, not a guess).
4. If the user wants to generate now and every file is present, run the measured workflow unchanged except the prompt and seed:
   ```
   python scripts/run_comfy.py --workflow <workflow URL from the picker> --prompt "..." [--seed 1]
   ```
   ComfyUI must be running (default http://127.0.0.1:8188). Report the output file name and the seconds it took on this PC next to the measured seconds.
5. **Your PC's own seconds (calibration).** The measured seconds are the test PC's. If the user has ComfyUI running and asks "how long on my PC", or the picker prints a `--calibrate` line, run that line once (3 images of a measured workflow whose files are all present, about a minute):
   ```
   python scripts/run_comfy.py --workflow <URL the picker printed> --calibrate
   ```
   It stores this PC's speed against the measured run in `~/.vram16-measured/calibration.json` (local only). From then on, the picker adds `on YOUR PC:` to each pick. Read it to the user this way:
   - `measured on YOUR PC` = this exact setting was run here. Quote it as a fact.
   - `≈ a–b s (ESTIMATE …)` = scaled from the user's other run(s). Say "about", and give the range. The ratio differs by precision (fp8/bf16/fp4) and model family, so calibrating with two different models gives an honest range.
   - On an 8GB/12GB card the reference is the run measured with VRAM capped to that class, so the ratio is compute speed only (offloading is already in both).
   - A ratio is never carried across tasks (an image run says nothing about an LLM) or to another GPU (`--gpu-name` turns it off).
   - The run prints a record the user *may* share. Nothing is sent; do not post it anywhere unless the user asks.
6. If files are missing, list them with the download page from the article. Do not download multi-GB weights without the user's OK.

## How to read the numbers (tell the user)

- **Seconds are the average of the 2nd and 3rd image, after the model is loaded.** The 1st image includes loading and is often 2–3× slower (shown as `1st run incl. loading` when measured). If the user's first try is slow, that is expected — run it again before judging.
- **8GB / 12GB class** (`basis: measured with VRAM capped…`): *whether it runs* carries over to a real card of that size. *Times* do not: they are at RTX 5080 compute speed, and an RTX 4060 has about 1/3 of its cores and bandwidth, so say "expect several times longer". In those tests ComfyUI's dynamic VRAM was off, so the article verdict line ("1024×1024 in about 2 s") is the 16GB result, not the user's.
- `EXTRAPOLATED` means only that the 16GB run peaked under the user's VRAM. Say it plainly; it is not a measurement at their size.
- **System RAM matters on small cards.** What does not fit in VRAM is kept in system RAM. A `TIGHT` line means loading added that much RAM in the test; on a 16GB or 32GB PC, tell the user to close the browser first or pick the next model. FLUX.1 dev (all-in-one fp8) stopped at the 8GB level because RAM ran short, not VRAM. Video is the same: Wan 2.2 TI2V 5B ran at the 8GB level (720p too, with the VAE switching to tiled decode by itself) but added about 29GB of system RAM, so on a 32GB PC say it is TIGHT. Both its text-to-video and its image-to-video (1280×704, 5 s) were measured below 16GB, with the same RAM rise; other video models were not, so for them say "not measured".
- Settings with **fp4 / nvfp4** are only fast on RTX 50 series cards; the picker leaves them out on older cards. Do not recommend them to an RTX 40/30 user.
- A model with `give_up` in the data has a documented failure (e.g. "the official setup does not run as is"). Mention it.

## Requests in Japanese (or any language)

The picker prints English. Answer in the user's language and explain these words, never leave them raw:

| picker word | say (Japanese) |
|---|---|
| `measured with VRAM capped to the 8GB class` | 8GB 相当に絞って実際に動かした結果（動く・動かないはそのまま当てはまる。秒数は 5080 の速さ） |
| `EXTRAPOLATED` | 推定。16GB で測った最大の VRAM が、あなたの枠に収まっていただけで、その大きさでは測っていない |
| `TIGHT` | メインメモリがぎりぎり。ブラウザなどを閉じてから |
| `STOPPED` | 実際に止まった（推測ではない） |
| `not measured` | 測っていない。動くとも動かないとも言わない |

- **`article verdict (on 16GB)` is the 16GB result.** If its seconds differ from the pick line (e.g. "about 2 s" vs 5.18 s), quote the pick line and say the verdict is for 16GB.
- **Laptop GPUs** (「ノート」「Laptop」): pass the name with `Laptop` (e.g. `--gpu-name "RTX 4060 Laptop"`). Laptops were not measured and run at lower power than the desktop card, so say "slower still" — no number.
- **Commercial**: a monetized YouTube channel, ads on a blog, or client work is revenue-generating, so use `--commercial`. Say the licence quote is from the article and the final check is the user's.
- **Style** (アニメ調, 実写, etc.): the data cannot filter by style. You may quote the article summary (e.g. Animagine XL 4.0 "built for anime art"), but never say a style model runs at a size where it was not measured.
- **"FLUX"** usually means FLUX.1 dev. If `--commercial` drops it and FLUX.2 klein appears instead, say they are different models with different licences.
- Other picker phrases: `Plenty` 余裕あり · `Good enough` 十分 · `1st run incl. loading` 読み込みを含む 1 枚目 · `workflow: none published` 配布の手順なし（記事を見て組む） · `fp4 settings left out` RTX 50 以外では速くならないので外した · `NOTE: this workflow is set to …` 配布の手順は別の大きさなので、潜在（空の動画・画像）のノードの幅と高さを書き換える.
- Match the request's length: if the user wants a 5 s video and a pick is a 2 s clip, say so.

## Rules

- Always cite the article. The data is refreshed from the site; newer measurements win over your memory.
- Licences come from the article, which quotes the licence text. Do not "correct" them from memory (models are often relicensed between versions).
