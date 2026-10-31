"""Queue a vram16-measured workflow (ComfyUI API format) on the user's own ComfyUI and wait for the result.

  python run_comfy.py --workflow URL_or_path [--prompt "text"] [--seed N] [--server http://127.0.0.1:8188]
                       [--repeat 3] [--calibrate]

Only the positive prompt text and the seed are changed; every other value stays as measured.
--calibrate: run it --repeat times (default 3) and store your PC's speed vs the measured run (calib.py),
so pick.py can say "on your PC ≈ N s" for every other model. Nothing is sent anywhere.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # also under python -I
import calib
from pick import gpu_info


def load(src):
    if src.startswith("http"):
        with urllib.request.urlopen(src, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    with open(src, encoding="utf-8") as f:
        return json.load(f)


def set_prompt(wf, text):
    """The positive prompt = the text input that feeds a sampler's/guider's 'positive' (falls back to the longest text)."""
    pos_ids = set()
    for node in wf.values():
        pos = (node.get("inputs") or {}).get("positive")
        if isinstance(pos, list):
            pos_ids.add(str(pos[0]))
    cands = []
    for nid, node in wf.items():
        for k, v in (node.get("inputs") or {}).items():
            if k in ("text", "prompt", "positive_prompt", "caption", "tags") and isinstance(v, str):
                cands.append((nid in pos_ids, len(v), nid, k))
    if not cands:
        return None
    cands.sort(reverse=True)
    _, _, nid, k = cands[0]
    wf[nid]["inputs"][k] = text
    return nid


def set_seed(wf, seed):
    for node in wf.values():
        for k in ("seed", "noise_seed"):
            if k in (node.get("inputs") or {}) and not isinstance(node["inputs"][k], list):
                node["inputs"][k] = seed


def call(server, path, body=None):
    req = urllib.request.Request(server + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", required=True)
    ap.add_argument("--prompt")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--calib-file")
    a = ap.parse_args()

    wf = load(a.workflow)
    if a.prompt:
        nid = set_prompt(wf, a.prompt)
        print("prompt set on node", nid)
    times, code = [], 0
    for i in range(a.repeat if a.calibrate else 1):
        if a.seed is not None or a.calibrate:
            set_seed(wf, (a.seed or 0) + i)  # a new seed each time, so ComfyUI does not return a cached result
        res = queue_once(a.server, wf, a.timeout)
        print(json.dumps(res, ensure_ascii=False))
        if res.get("status") != "success":
            return 1 if res.get("status") else 2
        times.append(res["comfy_execution_s"])
    if a.calibrate:
        return report_calibration(a.workflow, times, a.calib_file)
    return code


def queue_once(server, wf, timeout):
    t0 = time.time()
    pid = call(server, "/prompt", {"prompt": wf, "client_id": str(uuid.uuid4())})["prompt_id"]
    while time.time() - t0 < timeout:
        h = call(server, f"/history/{pid}")
        if pid in h:
            st = h[pid].get("status", {})
            files = [i["filename"] for o in h[pid].get("outputs", {}).values()
                     for key in ("images", "gifs", "videos", "audio") for i in o.get(key, [])]
            ts = {m[0]: m[1].get("timestamp") for m in st.get("messages", []) if isinstance(m, list) and len(m) == 2}
            run_s = (ts["execution_success"] - ts["execution_start"]) / 1000 if "execution_success" in ts and "execution_start" in ts else None
            return {"status": st.get("status_str"), "comfy_execution_s": run_s,
                    "wall_s": round(time.time() - t0, 2), "outputs": files}
        time.sleep(1)
    return {"status": None, "error": "timeout"}


def report_calibration(url, times, calib_file):
    if not url.startswith("http"):
        print("calibration needs the workflow URL from pick.py (to find the measured run)")
        return 1
    data = json.loads(calib_measured_json())
    gpu, vram = gpu_info()
    point = calib.record(data, url, times, gpu, vram, calib_file)
    if not point:
        print("calibration: no measured run for this workflow, or fewer than 2 runs")
        return 1
    print(f'calibration: {point["model"]} {point["setting"]} {point["size"]}: yours {point["yours_s"]} s (warm) '
          f'vs measured {point["measured_s"]} s on RTX 5080 → ×{point["ratio"]}  saved to {calib.path(calib_file)}')
    print("If you want to share it (optional, nothing was sent):")
    print(json.dumps(calib.share_record(point), ensure_ascii=False))
    return 0


def calib_measured_json():
    import pathlib
    return (pathlib.Path(__file__).resolve().parent.parent / "data" / "measured.json").read_text(encoding="utf-8")

if __name__ == "__main__":
    sys.exit(main())
