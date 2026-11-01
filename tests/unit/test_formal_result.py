"""formal.FormalResult from captured SymbiYosys outputs (no sby needed)."""
import os

import pytest

from dv_flow.mgr import PackageLoader, TaskGraphBuilder
from dv_flow.mgr.results import api as R
from dv_flow.mgr.results.convert import to_node
from dv_flow.mgr.task_run_ctxt import TaskRunCtxt
from dv_flow.mgr.type_match import is_a
from dv_flow.libformal.formal_result import mk_formal_result, parse_sby_log
from dv_flow.libformal.vcf_run import vcf_formal_result

RUNS = os.path.join(os.path.dirname(__file__), "data", "sby_runs")


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    pkg = PackageLoader().load_rgy(["std", "formal", "formal.sby"])
    b = TaskGraphBuilder(pkg, str(tmp_path_factory.mktemp("fr")))
    ctxt = TaskRunCtxt(runner=b, ctxt=None, rundir=str(tmp_path_factory.mktemp("rd")))
    return pkg, b, ctxt


def _mk(env, run, top, mode, verdict):
    _, _, ctxt = env
    d = os.path.join(RUNS, run)
    return mk_formal_result(ctxt, name=run, task="p." + run, rundir=d, mode=mode, top=top,
                            verdict=verdict, log_path=os.path.join(d, top + ".log"),
                            workdir=os.path.join(d, top), depth_goal=20)


def test_parse_cex():
    p = parse_sby_log(os.path.join(RUNS, "cex", "counter_bad.log"))
    assert p["depth"] == 14 and p["done"] == "FAIL" and p["rc"] == 2
    (a,) = p["asserts"]
    assert (a["file"], a["line"], a["log_line"]) == ("counter_bad.sv", 14, 8)
    assert p["traces"] == ["engine_0/trace.vcd"]
    assert p["engine"] == "smtbmc boolector"


def test_parse_cover():
    p = parse_sby_log(os.path.join(RUNS, "cover_unreached", "counter_nocov.log"))
    assert [(c["reached"], c["line"]) for c in p["covers"]] == [(True, 18), (False, 20)]
    assert p["covers"][0]["step"] == 3


def test_pass(env):
    pkg, b, _ = env
    r = _mk(env, "pass", "counter_ok", "bmc", "PASS")
    assert r.type == "formal.FormalResult"
    assert is_a(r.type, "std.Result", lambda n: b._findType(pkg, n))
    assert is_a(r.type, "std.TestResult", lambda n: b._findType(pkg, n))
    assert (r.status, r.passed) == ("pass", True)
    assert r.metrics["depth"]["value"] == 19.0 and r.metrics["proven"]["value"] == 1.0
    assert r.attrs["engine"] == "smtbmc boolector" and r.attrs["mode"] == "bmc"
    assert [c["status"] for c in r.checks] == ["pass"]
    roles = [a.attributes[0] for a in r.artifacts]
    assert roles == ["role=log"]


def test_cex(env):
    r = _mk(env, "cex", "counter_bad", "bmc", "FAIL")
    assert r.status == "fail"
    assert r.msg == "assertion failed at counter_bad.sv:14 in step 14"
    assert r.checks[0]["name"] == "assertions" and r.checks[0]["status"] == "fail"
    d = r.diagnostics[0]
    assert d["loc"]["line"] == 8 and d["src_loc"] == {"path": "counter_bad.sv", "line": 14}
    waves = [a for a in r.artifacts if "role=waves" in a.attributes]
    assert len(waves) == 1 and waves[0].files == ["trace.vcd"]


def test_unknown_is_error_with_proof_check(env):
    r = _mk(env, "unknown", "counter_ind", "prove", "UNKNOWN")
    assert r.status == "error"
    assert {c["name"]: c["status"] for c in r.checks} == {"assertions": "pass", "proof": "error"}
    assert r.metrics["unknown"]["value"] == 1.0
    assert "inconclusive" in r.msg


def test_cover_unreached(env):
    r = _mk(env, "cover_unreached", "counter_nocov", "cover", "FAIL")
    assert r.status == "fail"
    assert r.metrics["covered"]["value"] == 1.0 and r.metrics["unreached"]["value"] == 1.0
    assert r.checks[0]["name"] == "covers" and r.checks[0]["status"] == "fail"
    assert r.msg.startswith("1 cover statement(s) not reached, first at counter_nocov.sv:20")


@pytest.mark.parametrize("run,top,mode,verdict", [
    ("pass", "counter_ok", "bmc", "PASS"), ("cex", "counter_bad", "bmc", "FAIL"),
    ("unknown", "counter_ind", "prove", "UNKNOWN"),
    ("cover_unreached", "counter_nocov", "cover", "FAIL"),
    ("cex", "counter_bad", "bmc", "TIMEOUT"), ("pass", "counter_ok", "bmc", "ERROR")])
def test_checks_never_disagree_with_verdict(env, run, top, mode, verdict):
    r = _mk(env, run, top, mode, verdict)
    again = R.finish({"status": {"PASS": "pass", "FAIL": "fail", "TIMEOUT": "timeout"}.get(verdict, "error"),
                      "checks": [dict(c) for c in r.checks]})
    assert again["status"] == r.status
    if r.status != "pass":
        assert any(c["status"] != "pass" for c in r.checks)


def test_converts_to_a_valid_node(env):
    pkg, b, _ = env
    n = to_node(_mk(env, "cex", "counter_bad", "bmc", "FAIL"), lambda t: b._findType(pkg, t))
    assert n.types == ["formal.FormalResult", "std.TestResult", "std.Result"]
    assert n.artifacts[1].role == "waves"


def test_vcf_result(env, tmp_path):
    _, _, ctxt = env
    log = tmp_path / "vcf.log"
    log.write_text("[p1] proven\n[p2] falsified\n")
    import types
    inp = types.SimpleNamespace(name="p.prove", rundir=str(tmp_path),
                                params=types.SimpleNamespace(top="dma", proof_mode="all"))
    from dv_flow.libformal.vcf_run import _parse_counts
    counts, _ = _parse_counts(str(log))
    r = vcf_formal_result(ctxt, inp, counts, 0, str(log))
    assert r.status == "fail" and r.metrics["failed"]["value"] == 1.0
    r = vcf_formal_result(ctxt, inp, {"proven": 2}, 0, str(log))
    assert r.status == "pass"
    r = vcf_formal_result(ctxt, inp, {}, 3, str(log))
    assert r.status == "error"
