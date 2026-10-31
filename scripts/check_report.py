"""Check a board report (the record run_comfy.py --calibrate prints) against the measured data.

Nothing in the record is trusted: the measured run is looked up again from data/measured.json, the warm seconds and
the ratio are recomputed from runs_s, and the VRAM must fit the GPU name. A report is
  accept  - listed on the site as is
  hold    - a person looks at it first (unknown GPU, odd ratio, far from other reports of the same GPU)
  reject  - cannot be used (not a record, unknown workflow, numbers that do not add up)

  python scripts/check_report.py issue.md [--accepted reports.json] [--json]
  (issue.md: the issue body as GitHub renders an issue form, or a bare JSON record)
"""
import argparse
import json
import pathlib
import re
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import calib  # noqa: E402
from pick import vram_class  # noqa: E402

# VRAM sizes sold under each name (desktop and laptop). Only used to catch a record whose VRAM does not fit the name.
KNOWN_VRAM = {
    "rtx 3050": (4, 6, 8), "rtx 3060": (6, 8, 12), "rtx 3060 ti": (8,), "rtx 3070": (8,), "rtx 3070 ti": (8,),
    "rtx 3080": (8, 10, 12, 16), "rtx 3080 ti": (12, 16), "rtx 3090": (24,), "rtx 3090 ti": (24,),
    "rtx 4050": (6,), "rtx 4060": (8,), "rtx 4060 ti": (8, 16), "rtx 4070": (8, 12), "rtx 4070 super": (12,),
    "rtx 4070 ti": (12,), "rtx 4070 ti super": (16,), "rtx 4080": (12, 16), "rtx 4080 super": (16,), "rtx 4090": (16, 24),
    "rtx 5050": (8,), "rtx 5060": (8,), "rtx 5060 ti": (8, 16), "rtx 5070": (8, 12), "rtx 5070 ti": (12, 16),
    "rtx 5080": (16,), "rtx 5090": (24, 32),
}
FASTER_THAN_TEST_CARD = ("rtx 4090", "rtx 5090")  # ratio well under 1 is believable only for these
KEYS = ("model", "workflow", "runs_s", "gpu", "vram_gb")
TOL = 0.02  # seconds; the record rounds to 0.01


def gpu_key(name):
    s = re.sub(r"\b(nvidia|geforce|laptop gpu|laptop|gpu)\b", " ", (name or "").lower())
    s = re.sub(r"\s+", " ", s).strip()
    m = re.search(r"rtx\s*(\d{4})(\s*ti)?(\s*super)?", s)
    if not m:
        return None, "laptop" in (name or "").lower()
    return "rtx " + m.group(1) + (" ti" if m.group(2) else "") + (" super" if m.group(3) else ""), "laptop" in (name or "").lower()


def parse_issue(text):
    """(record dict or None, fields) from an issue-form body or a bare JSON record."""
    fields = {}
    for head, body in re.findall(r"^###\s+(.+?)\s*\n(.*?)(?=^###\s|\Z)", text, re.S | re.M):
        body = body.strip()
        fields[head.strip()] = None if body in ("_No response_", "") else body
    raw = fields.get("Record", text)
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        rec = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        rec = None
    return (rec if isinstance(rec, dict) else None), fields


def check(rec, fields, data, accepted=()):
    out = {"verdict": "accept", "reasons": [], "row": None}

    def say(level, why):
        out["reasons"].append(f"{level}: {why}")
        if level == "reject" or (level == "hold" and out["verdict"] == "accept"):
            out["verdict"] = level

    if rec is None:
        say("reject", "no JSON record found")
        return out
    missing = [k for k in KEYS if k not in rec]
    if missing:
        say("reject", "missing " + ", ".join(missing))
        return out
    runs = rec["runs_s"]
    if not (isinstance(runs, list) and 2 <= len(runs) <= 20 and all(isinstance(t, (int, float)) and 0 < t < 7200 for t in runs)):
        say("reject", "runs_s must be 2-20 positive seconds (the 1st run loads the model, so one run is not enough)")
        return out
    vram = rec["vram_gb"]
    if not isinstance(vram, (int, float)) or not 2 <= vram <= 96:
        say("reject", "vram_gb is not a GPU memory size")
        return out

    # the measured run is looked up again; the record's measured_s is only compared
    m, run = calib.measured_run_for(data, rec["workflow"], vram_class(vram))
    if not run:
        say("reject", "workflow is not one of the measured ones (or its measured run failed)")
        return out
    if isinstance(rec.get("measured_s"), (int, float)) and abs(rec["measured_s"] - run["time_s"]) > TOL:
        say("hold", f"record says measured {rec['measured_s']} s, data says {run['time_s']} s (old skill data or edited)")
    warm = calib.warm_seconds(runs)
    if isinstance(rec.get("yours_s"), (int, float)) and abs(rec["yours_s"] - warm) > TOL:
        say("reject", f"yours_s {rec['yours_s']} does not follow from runs_s (warm {warm})")
        return out
    ratio = round(warm / run["time_s"], 2)

    key, laptop_name = gpu_key(rec["gpu"])
    laptop = laptop_name or (fields.get("Laptop or desktop?") == "Laptop")
    if key is None:
        say("hold", f"GPU name not recognised: {rec['gpu']!r} (AMD/Intel/older cards are welcome; a person files them)")
    elif key not in KNOWN_VRAM:
        say("hold", f"{key} is not in the VRAM table yet")
    elif not any(abs(vram - v) <= 1.0 for v in KNOWN_VRAM[key]):
        say("reject", f"{vram} GB does not fit {key} (sold with {', '.join(map(str, KNOWN_VRAM[key]))} GB)")
        return out
    if ratio < 0.5 and key not in FASTER_THAN_TEST_CARD:
        say("hold", f"{ratio}x the test card's time, i.e. more than twice as fast as an RTX 5080")
    if ratio > 40:
        say("hold", f"{ratio}x the test card's time; check it was not paging to disk")
    if fields.get("Laptop or desktop?") == "Not sure":
        say("hold", "laptop or desktop not known")

    same = [a["ratio"] for a in accepted if a.get("gpu_key") == key and a.get("workflow") == rec["workflow"]
            and a.get("laptop") == laptop]
    if len(same) >= 2:
        med = statistics.median(same)
        if not med / 2 <= ratio <= med * 2:
            say("hold", f"far from the other {len(same)} reports of this GPU (median ratio {med})")

    ram = fields.get("System RAM (GB)")
    out["row"] = {"model": m["name"], "setting": run.get("setting"), "size": run.get("size"), "workflow": rec["workflow"],
                  "gpu": rec["gpu"], "gpu_key": key, "laptop": laptop, "vram_gb": vram,
                  "ram_gb": float(ram) if ram and re.fullmatch(r"\d+(\.\d+)?", ram) else None,
                  "yours_s": warm, "first_s": runs[0], "measured_s": run["time_s"],
                  "measured_capped_gb": run.get("vram_class_gb") if run.get("capped") else None, "ratio": ratio,
                  "date": rec.get("date"), "comfyui": rec.get("comfyui")}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("report", help="issue body (markdown) or a JSON record")
    ap.add_argument("--data", default=str(HERE.parent / "data" / "measured.json"))
    ap.add_argument("--accepted", help="JSON list of rows already accepted (to compare with the same GPU)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    data = json.loads(pathlib.Path(a.data).read_text(encoding="utf-8"))
    accepted = json.loads(pathlib.Path(a.accepted).read_text(encoding="utf-8")) if a.accepted else []
    rec, fields = parse_issue(pathlib.Path(a.report).read_text(encoding="utf-8"))
    res = check(rec, fields, data, accepted)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return
    print(res["verdict"].upper())
    for r in res["reasons"]:
        print("  " + r)
    if res["row"]:
        r = res["row"]
        print(f"  {r['gpu']} ({r['vram_gb']} GB{', laptop' if r['laptop'] else ''}): {r['model']} {r['setting']} "
              f"{r['yours_s']} s (1st {r['first_s']} s) = {r['ratio']}x the measured {r['measured_s']} s"
              + (f" [capped to {r['measured_capped_gb']} GB]" if r["measured_capped_gb"] else ""))


if __name__ == "__main__":
    main()
