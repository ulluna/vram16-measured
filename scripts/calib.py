"""Your PC vs the measured RTX 5080: a speed ratio from your own runs of measured workflows.

The ratio is stored locally (nothing is sent). pick.py reads it to say "on your PC ≈ N s" next to each measured time.
File: ~/.vram16-measured/calibration.json (override with VRAM16_CALIB or --calib-file).
"""
import datetime
import json
import os
import pathlib
import statistics

WARMING = 1.5  # a run slower than 1.5× the fastest warm run is still warming up (seen: SD3.5 Turbo 6.17 s then 3.13 s)


def path(override=None):
    return pathlib.Path(override or os.environ.get("VRAM16_CALIB") or pathlib.Path.home() / ".vram16-measured" / "calibration.json")


def load(override=None):
    p = path(override)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"points": []}


def warm_seconds(times):
    """Same idea as the site (runs after the 1st), minus runs that were plainly still warming up."""
    warm = [t for t in times[1:] if isinstance(t, (int, float))]
    if not warm:
        return None
    fast = min(warm)
    return round(statistics.mean([t for t in warm if t <= fast * WARMING]), 2)


def measured_run_for(data, url, cls=None):
    """The measured run that a published workflow URL reproduces. On an 8GB/12GB card, the run with VRAM capped
    to that class (same offloading as the user's card, so the ratio is compute speed only); else the 16GB run."""
    from pick import match_workflow  # same folder
    for m in data["models"]:
        wf = next((w for w in m["workflows"] if w["url"] == url), None)
        if not wf:
            continue
        if cls in (8, 12):
            cap = [r for r in m.get("capped_runs", []) if r.get("vram_class_gb") == cls and r.get("result") == "ok"
                   and r.get("workflow_label") == wf["label"]]
            if cap:
                return m, dict(cap[0], capped=True)
        ok = [r for r in m["runs"] if r.get("result") == "ok" and isinstance(r.get("time_s"), (int, float))]
        mine = [r for r in ok if match_workflow(m, r) is wf]
        # A workflow fixed at 1280×704 must not be compared with the 832×480 run (the ratio would be ~3x off)
        from pick import label_size
        size = label_size(wf["label"])
        same = [r for r in mine if size and label_size(r.get("size")) == size]
        mine = same or mine
        return m, (min(mine, key=lambda r: r["time_s"]) if mine else None)
    return None, None


def record(data, url, times, gpu, vram, override=None):
    from pick import vram_class
    m, run = measured_run_for(data, url, vram_class(vram))
    warm = warm_seconds(times)
    if not run or warm is None:
        return None
    point = {"model": m["name"], "tasks": m["tasks"], "setting": run.get("setting"), "size": run.get("size"), "workflow": url,
             "measured_s": run["time_s"], "measured_capped_gb": run.get("vram_class_gb") if run.get("capped") else None, "yours_s": warm, "runs_s": times, "ratio": round(warm / run["time_s"], 2),
             "gpu": gpu, "vram_gb": vram, "date": datetime.date.today().isoformat()}
    c = load(override)
    c["points"] = [p for p in c["points"] if not (p["workflow"] == url and p.get("gpu") == gpu)] + [point]
    p = path(override)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    return point


def ratio_for(gpu, task, override=None):
    """(low, high, points) of the speed ratio on this GPU for this task, or None. Several points give a range, not
    one number: the ratio differs by architecture and precision (fp8 / bf16 / fp4). Never carried across tasks:
    an image run says nothing about an LLM (other engine, bound by memory bandwidth instead of compute)."""
    pts = [p for p in load(override)["points"] if p.get("gpu") == gpu and task in p.get("tasks", [])]
    if not pts:
        return None
    rs = [p["ratio"] for p in pts]
    return min(rs), max(rs), pts


def share_record(point, comfy_version=None):
    """What a user could paste into a public report. Printed only; nothing is sent."""
    keep = ("model", "setting", "size", "workflow", "measured_s", "yours_s", "runs_s", "gpu", "vram_gb", "date")
    rec = {k: point[k] for k in keep}
    rec["comfyui"] = comfy_version
    return rec
