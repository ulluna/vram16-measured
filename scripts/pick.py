"""Pick a generative model + setting for this PC, using only runs measured by vram16.ullu-egg.com.

  python pick.py --task t2i [--vram auto|8|12|16] [--gpu-name "RTX 4060"] [--ram auto|32]
                 [--commercial] [--comfy-dir PATH] [--top 5] [--json]

Never guesses: if no measured run fits, it says so.
"""
import argparse
import ctypes
import json
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # also under python -I
import calib

DATA = pathlib.Path(__file__).resolve().parent.parent / "data" / "measured.json"
RAM_HEADROOM_GB = 8  # Windows, browser and the ComfyUI process itself, before the model is loaded


def gpu_info():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
        name, mib = [s.strip() for s in out[0].split(",")]
        return name, round(int(mib) / 1024, 1)
    except Exception:
        return None, None


def system_ram_gb():
    try:
        if os.name == "nt":
            class MS(ctypes.Structure):
                _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
            m = MS()
            m.len = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.total / 1024 ** 3)
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3)
    except Exception:
        return None


def is_blackwell(name):
    """Hardware FP4 (nvfp4) is only fast on RTX 50 series / Blackwell."""
    return bool(name and re.search(r"RTX\s*50\d\d|Blackwell|RTX PRO \d000", name, re.I))


def vram_class(vram):
    """Card VRAM (as nvidia-smi reports it) → the class the capped runs were measured for."""
    if vram is None:
        return None
    if vram >= 15.5:
        return 16
    if vram >= 11.5:
        return 12
    if vram >= 7.5:
        return 8
    return 0


def pixels(size):
    try:
        w, h = size.replace("x", "×").split("×")[:2]
        return int(w.strip()) * int(h.split()[0].strip())
    except Exception:
        return None


def tokens(s):
    return {w for w in re.split(r"[^a-z0-9]+", (s or "").lower().replace("×", "x")) if w}


def other_mode(run, task):
    """A model that does both text-to-video and image-to-video: a run labelled T2V does not answer an i2v request."""
    t = tokens(run.get("setting")) | tokens(run.get("size"))
    return (task == "i2v" and "t2v" in t) or (task == "t2v" and "i2v" in t)


def label_size(label):
    m = re.search(r"(\d{3,4})\s*[x×]\s*(\d{3,4})", label or "")
    return f"{m.group(1)}×{m.group(2)}" if m else None


def match_workflow(model, run):
    """Workflow named in the run, else the one whose label/filename shares the most words with the run."""
    if run.get("workflow_label"):
        for w in model["workflows"]:
            if w["label"] == run["workflow_label"]:
                return w
    want = tokens(run.get("setting")) | tokens(run.get("size"))
    best, score = None, 0
    for w in model["workflows"]:
        s = len(want & (tokens(w["label"]) | tokens(w["url"].rsplit("/", 1)[-1])))
        if s > score:
            best, score = w, s
    return best


def missing_files(names, comfy_dir):
    if not comfy_dir or names is None:
        return None
    models = pathlib.Path(comfy_dir) / "models"
    have = {p.name for p in models.rglob("*") if p.is_file()}
    return [n for n in names if n not in have]


def part_only(run):
    # e.g. LightVAE "decode only": a part of a pipeline, not something that makes a video by itself
    return bool(re.search(r"\b(decode|encode)r?\s+only\b", run.get("setting", ""), re.I))


def fp4(run):
    return "fp4" in f'{run.get("setting", "")} {run.get("quant", "")}'.lower()


def ram_check(run, ram):
    add = run.get("ram_add_gb")
    if ram is None or add is None:
        return None
    if add + RAM_HEADROOM_GB > ram:
        return f"TIGHT: loading added {add}GB of system RAM in the test; you have {ram}GB. Close other apps, or pick another"
    return f"ok ({add}GB of system RAM added in the test; you have {ram}GB)"


def main():
    try:  # Windows consoles (cp932 etc.) cannot print some characters in the data
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--vram", default="auto")
    ap.add_argument("--gpu-name", help="override the GPU name (e.g. when asking for someone else's PC)")
    ap.add_argument("--ram", default="auto", help="system RAM in GB")
    ap.add_argument("--commercial", action="store_true")
    ap.add_argument("--comfy-dir")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--calib-file", help="speed ratio saved by run_comfy.py --calibrate (default ~/.vram16-measured/)")
    a = ap.parse_args()

    data = json.loads(DATA.read_text(encoding="utf-8"))
    gpu, vram = gpu_info() if a.vram == "auto" else (None, float(a.vram))
    gpu = a.gpu_name or gpu
    ram = system_ram_gb() if a.ram == "auto" else float(a.ram)
    cls = vram_class(vram)
    blackwell = is_blackwell(gpu) if gpu else None

    picks, skipped = [], []
    for m in data["models"]:
        if a.task not in m["tasks"]:
            continue
        if a.commercial and not m.get("commercial_ok"):
            skipped.append(f'{m["name"]}: not OK for commercial use ({m.get("license")}). Article: {m.get("commercial") or ""}')
            continue
        ok = [r for r in m["runs"] if r.get("result") == "ok" and isinstance(r.get("time_s"), (int, float))
              and not part_only(r) and not other_mode(r, a.task)]
        if blackwell is False and any(fp4(r) for r in ok):
            ok = [r for r in ok if not fp4(r)]
            skipped.append(f'{m["name"]}: fp4 settings left out (fast FP4 needs an RTX 50 series card; yours is {gpu})')
        if not ok:
            continue
        cap = []
        if cls is None or cls >= 16:
            fit, basis = ok, ("measured on the same VRAM class (16GB)" if cls else "unknown GPU")
        else:
            # 1) Runs measured with VRAM capped to this card's class: whether it runs carries over to the real card.
            cap = [r for r in m.get("capped_runs", []) if r.get("vram_class_gb") == cls and not part_only(r)
                   and not other_mode(r, a.task) and not (blackwell is False and fp4(r))]
            fit = [r for r in cap if r.get("result") == "ok"]
            for r in cap:
                if r.get("result") != "ok":
                    skipped.append(f'{m["name"]} {r.get("setting")}: STOPPED at the {cls}GB level — {r.get("note", "")} '
                                   f'(source: {data.get("capped_note", "").split("Source: ")[-1].split(" ")[0]})')
            basis = (f"measured with VRAM capped to the {cls}GB class (runs or not carries over; "
                     "times are at RTX 5080 speed, a real card is slower)")
            if not cap:
                # 2) No capped run: only runs whose peak on the 16GB card already stayed under this card. Extrapolation.
                fit = [r for r in ok if isinstance(r.get("peak_vram_gb"), (int, float)) and r["peak_vram_gb"] <= vram - 0.5]
                basis = f"EXTRAPOLATED: peak on the 16GB card stayed under {vram - 0.5:.1f}GB (not measured at your size)"
                if not fit:
                    other = [r for r in m.get("capped_runs", []) if r.get("vram_class_gb") == cls
                             and r.get("result") == "ok" and other_mode(r, a.task)]
                    skipped.append(f'{m["name"]}: not measured below 16GB (peaked at '
                                   f'{min(r.get("peak_vram_gb") or 99 for r in ok)}GB on the 16GB card; may still run with offloading)'
                                   + ("; its other mode (" + ", ".join(sorted({r.get("setting") for r in other})) +
                                      f") WAS measured and ran at the {cls}GB class, this one was not" if other else ""))
                    continue
        if not fit:
            continue
        if gpu and "laptop" in gpu.lower() and cls and cls < 16:
            basis += ("; LAPTOP GPU: it runs at lower power than the desktop card of the same name, "
                      "so expect it slower still (laptops were not measured)")
        # Prefer the most common "standard" size: smallest pixel count, then fastest.
        fit.sort(key=lambda r: (pixels(r.get("size", "")) or 0, r["time_s"]))
        std_px = pixels(fit[0].get("size", ""))
        same = [r for r in fit if pixels(r.get("size", "")) == std_px] or fit
        best = min(same, key=lambda r: r["time_s"])
        wf = match_workflow(m, best)
        picks.append({
            "model": m["name"], "fit": m.get("fit"), "fit_text": m.get("fit_text"),
            "best_run": best, "basis": basis, "measured_at_size": bool(cap) or cls is None or cls >= 16,
            "ram": ram_check(best, ram),
            "license": m.get("license"), "commercial_ok": m.get("commercial_ok"),
            "article": m["article"], "workflow": wf,
            "missing_files": missing_files(wf["needs"] if wf else None, a.comfy_dir), "give_up": m.get("give_up"),
        })
    picks.sort(key=lambda p: (not p["measured_at_size"], (p["ram"] or "").startswith("TIGHT"),
                              {"enough": 0, "tune": 1}.get(p["fit"], 2), p["best_run"]["time_s"]))
    # Your own speed: only from runs on this same GPU (never borrowed from another card).
    cal = calib.ratio_for(gpu, a.task, a.calib_file) if gpu and not a.gpu_name else None
    for p in picks:
        if cal:
            lo, hi, pts = cal
            t = p["best_run"]["time_s"]
            own = next((q for q in pts if q["model"] == p["model"] and q["setting"] == p["best_run"].get("setting")
                        and q["size"] == p["best_run"].get("size")), None)
            if own:  # this exact setting was run on this PC: report it, not an estimate
                p["yours_est_s"], p["yours_basis"] = [own["yours_s"]] * 2, f'measured on YOUR PC {own["date"]}'
            else:
                p["yours_est_s"] = [round(t * lo, 1), round(t * hi, 1)]
                p["yours_basis"] = "ESTIMATE from your run(s) of " + ", ".join(sorted({q["model"] for q in pts}))
    res = {"gpu": gpu, "calibration": ({"low": cal[0], "high": cal[1], "points": cal[2]} if cal else None), "vram_gb": vram, "vram_class_gb": cls, "system_ram_gb": ram, "task": a.task,
           "measured_on": data["measured_on"], "timing": data.get("timing"), "capped_note": data.get("capped_note"),
           "picks": picks[: a.top], "not_picked": skipped}
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return
    print(f'GPU: {gpu or "?"}  VRAM: {vram}GB (class {cls})  system RAM: {ram}GB  task: {a.task}')
    print(f'All numbers measured on {data["measured_on"]}. {data.get("timing", "")}')
    if not picks:
        print("No run measured within this VRAM. Do not guess either way; say it is unmeasured and link https://vram16.ullu-egg.com/en/")
    for i, p in enumerate(picks[: a.top], 1):
        r = p["best_run"]
        first = f', 1st run incl. loading {r["first_s"]} s' if r.get("first_s") else ""
        print(f'{i}. {p["model"]} — {r.get("setting")} {r.get("size", "")}: {r["time_s"]} s{first}, peak VRAM {r.get("peak_vram_gb")} GB'
              f' | commercial: {"yes" if p["commercial_ok"] else "NO"} ({p["license"]})')
        if p["fit_text"]:
            print(f'   article verdict (on 16GB): {p["fit_text"]}' if not (p["basis"].startswith("measured on the same")
                  or p["basis"] == "unknown GPU") else f'   {p["fit_text"]}')
        if p.get("yours_est_s"):
            lo, hi = p["yours_est_s"]
            if p["yours_basis"].startswith("measured"):
                print(f'   on YOUR PC: {lo} s  ({p["yours_basis"]})')
            else:
                print(f'   on YOUR PC: ≈ {lo if lo == hi else f"{lo}–{hi}"} s  ({p["yours_basis"]}; speed ×{cal[0]}'
                      f'{"" if cal[0] == cal[1] else f"–×{cal[1]}"} vs the measured runs)')
        print(f'   basis: {p["basis"]}  | source: {p["article"]}')
        if p["ram"]:
            print(f'   system RAM: {p["ram"]}')
        if p["workflow"]:
            print(f'   workflow: {p["workflow"]["url"]}  ({p["workflow"]["label"]})')
            wsize, rsize = label_size(p["workflow"]["label"]), label_size(p["best_run"].get("size"))
            if wsize and rsize and wsize != rsize:
                print(f'   NOTE: this workflow is set to {wsize}, not the {rsize} above. '
                      f'Change width/height in its latent (empty video/image) node to {rsize} to reproduce that run')
        else:
            print("   workflow: none published for this setting (see the article)")
        if p["missing_files"] is not None:
            print("   files: all present in your ComfyUI" if not p["missing_files"] else
                  "   missing in your ComfyUI: " + ", ".join(p["missing_files"]))
    for s in skipped[:10]:
        print("   skipped:", s)
    if picks and not cal and gpu and not a.gpu_name:
        w = next((p["workflow"] for p in picks if p["workflow"] and not (p["missing_files"] or [])), None)
        if w:
            print(f'Times above are for the test PC. To see them for YOUR PC, run once (3 images, about a minute):\n'
                  f'   python scripts/run_comfy.py --workflow {w["url"]} --calibrate')


if __name__ == "__main__":
    sys.exit(main())
