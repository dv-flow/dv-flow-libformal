"""formal.FormalResult: a formal run's verdict in the std.Result shape.

`parse_sby_log` reads what SymbiYosys prints (the `<top>.log` dfm captures,
or `<top>/logfile.txt`); `mk_formal_result` turns it, with the sby verdict,
into a `formal.FormalResult` (a `std.TestResult`, so a proof is a test case
to std suites, the run record and its JUnit/CTRF renderings).

  attrs    engine, mode, top
  metrics  depth (the last step checked), proven, failed, unknown, covered,
           unreached
  checks   assertions (bmc/prove), covers (cover), proof (inconclusive or
           crashed runs)
  roles    log, waves (each counterexample / cover trace)

Properties are reported as diagnostics (a failed assertion or an
unreached cover, with the log line and the source location), not as child
nodes: a proof is one case, and children would make the run record count
its properties as tests.
"""
import os
import re
from typing import Any, Dict, List

_STEP_RE = re.compile(r"Checking (?:assertions|cover reachability) in step (\d+)")
_ASSERT_RE = re.compile(r"Assert failed in (\S+): (\S+?):(\d+)\.(\d+)(?:-\S+)?(?: \((.*)\))?\s*$")
_COVER_RE = re.compile(r"(Reached|Unreached) cover statement at (\S+?):(\d+)\.(\d+)(?:-\S+)?"
                       r"(?: \(([^)]*)\))?(?: in step (\d+))?")
_TRACE_RE = re.compile(r"Writing trace to VCD file: (\S+)")
_DONE_RE = re.compile(r"DONE \((\w+), rc=(\d+)\)")
_ENGINE_RE = re.compile(r"engine_\d+: (smtbmc|abc|aiger|btor)\b ?(\S*)")


def parse_sby_log(path: str) -> Dict[str, Any]:
    """What a sby log says: the deepest step checked, the failed assertions,
    the reached/unreached covers, the traces (relative to the sby workdir),
    the engine and the DONE verdict. Missing file -> empty results."""
    res = {"depth": None, "asserts": [], "covers": [], "traces": [],
           "engine": "", "done": None, "rc": None}
    if not os.path.isfile(path):
        return res
    with open(path, errors="replace") as fp:
        for lineno, line in enumerate(fp, 1):
            m = _STEP_RE.search(line)
            if m:
                res["depth"] = max(res["depth"] or 0, int(m.group(1)))
            m = _ASSERT_RE.search(line)
            if m and "summary:" not in line:
                res["asserts"].append({"module": m.group(1), "file": m.group(2),
                                       "line": int(m.group(3)), "witness": m.group(5) or "",
                                       "log_line": lineno})
                continue
            m = _COVER_RE.search(line)
            if m:
                res["covers"].append({"reached": m.group(1) == "Reached", "file": m.group(2),
                                      "line": int(m.group(3)), "witness": m.group(5) or "",
                                      "step": int(m.group(6)) if m.group(6) else None,
                                      "log_line": lineno})
                continue
            m = _TRACE_RE.search(line)
            if m:
                res["traces"].append(m.group(1))
            m = _DONE_RE.search(line)
            if m:
                res["done"], res["rc"] = m.group(1).upper(), int(m.group(2))
            if not res["engine"]:
                m = _ENGINE_RE.search(line)
                if m:
                    res["engine"] = " ".join(x for x in m.groups() if x)
    return res


_STATUS = {"PASS": "pass", "FAIL": "fail", "TIMEOUT": "timeout"}


def verdict_status(verdict: str) -> str:
    """sby verdict -> Result status (UNKNOWN and ERROR have no clean verdict)."""
    return _STATUS.get((verdict or "").upper(), "error")


def mk_formal_result(ctxt, name: str, task: str, rundir: str, mode: str, top: str,
                     verdict: str, log_path: str, workdir: str, depth_goal: int = 0,
                     tool: str = "sby", walltime_s: float = None, parsed=None):
    """A `formal.FormalResult` for one proof. `verdict` is sby's (PASS, FAIL,
    UNKNOWN, TIMEOUT, ERROR); the status is derived from it alone, and the
    checks are built so that `finish()` gives the same status back."""
    from dv_flow.mgr import FileSet
    from dv_flow.mgr.results import api as R

    p = parsed if parsed is not None else parse_sby_log(log_path)
    status = verdict_status(verdict)
    reached = [c for c in p["covers"] if c["reached"]]
    unreached = [c for c in p["covers"] if not c["reached"]]
    failed = len(p["asserts"])

    metrics = {}
    if p["depth"] is not None:
        metrics["depth"] = R.metric(p["depth"], name="depth")
    if mode == "cover":
        metrics["covered"] = R.metric(len(reached), name="covered")
        metrics["unreached"] = R.metric(len(unreached), "", "lower", "Unreached")
    else:
        metrics["failed"] = R.metric(failed, name="failed")
        if status == "pass":
            metrics["proven"] = R.metric(1, name="proven")
        if verdict.upper() == "UNKNOWN":
            metrics["unknown"] = R.metric(1, name="unknown")
    if walltime_s is not None:
        metrics["walltime_s"] = R.metric(walltime_s, name="walltime_s")

    def no_worse(st):
        # a property check is a `fail`, or `pass`; never worse than the verdict
        return st if status != "pass" else "pass"

    checks = []
    if mode == "cover":
        checks.append(R.check("covers", no_worse("fail" if unreached else "pass"),
                              "unreached", "==", 0, value=len(unreached)))
    else:
        checks.append(R.check("assertions", no_worse("fail" if failed else "pass"),
                              "failed", "==", 0, value=failed))
    if status in ("error", "timeout") or (status == "fail" and not failed and not unreached):
        why = {"UNKNOWN": "inconclusive: the proof neither passed nor found a counterexample",
               "TIMEOUT": "the proof timed out",
               "ERROR": "sby reported an error (see the log)"}.get(
                   verdict.upper(), "sby verdict %s" % verdict)
        checks.append(R.check("proof", "error" if status == "error" else "fail", msg=why))

    diags = []
    for a in p["asserts"]:
        diags.append({"severity": "error", "category": "sva",
                      "msg": "assertion failed in %s (%s)" % (a["module"], a["witness"] or "assert"),
                      "loc": {"path": log_path, "line": a["log_line"]},
                      "src_loc": {"path": a["file"], "line": a["line"]}})
    for c in unreached:
        diags.append({"severity": "error", "category": "sva",
                      "msg": "cover statement not reached (%s)" % (c["witness"] or "cover"),
                      "loc": {"path": log_path, "line": c["log_line"]},
                      "src_loc": {"path": c["file"], "line": c["line"]}})

    if status == "pass":
        msg = ""
    elif failed:
        a = p["asserts"][0]
        msg = "assertion failed at %s:%d" % (a["file"], a["line"])
        if p["depth"] is not None:
            msg += " in step %d" % p["depth"]
    elif unreached:
        c = unreached[0]
        msg = "%d cover statement(s) not reached, first at %s:%d" % (len(unreached), c["file"], c["line"])
    else:
        msg = {"UNKNOWN": "inconclusive (%s)" % mode, "TIMEOUT": "timed out",
               "ERROR": "sby error"}.get(verdict.upper(), verdict)

    arts = []
    if os.path.isfile(log_path):
        arts.append(FileSet(filetype="sbyLog", basedir=os.path.dirname(log_path),
                            files=[os.path.basename(log_path)], attributes=["role=log"]))
    for t in p["traces"]:
        tp = os.path.join(workdir, t)
        if os.path.isfile(tp):
            arts.append(FileSet(filetype="vcd", basedir=os.path.dirname(tp),
                                files=[os.path.basename(tp)],
                                attributes=["role=waves", "label=%s trace" % mode]))

    res = R.mk_result(ctxt, "formal.FormalResult", name=name, task=task, rundir=rundir,
                      status=status, msg=msg, testname=top or "")
    res.attrs = {"engine": p["engine"] or tool, "mode": mode, "top": top, "verdict": verdict}
    if depth_goal:
        res.attrs["depth_goal"] = depth_goal
    res.tool = {"name": tool}
    res.metrics = metrics
    res.checks = checks
    res.diagnostics = diags
    res.artifacts = arts
    R.finish(res)
    return res
