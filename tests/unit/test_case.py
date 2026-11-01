"""formal.sby.Case: one proof as a test case -- the sby verdict as an
formal.FormalResult (a std.TestResult), and a task that succeeds whatever
the verdict."""
import os
import shutil
import asyncio
import pytest
from dv_flow.mgr import TaskSetRunner, TaskGraphBuilder, PackageLoader
from dv_flow.libformal.sby_bmc import _sby_verdict

has_sby = shutil.which('sby') is not None
DATA = os.path.join(os.path.dirname(__file__), 'data', 'formal_case')


def _run_case(tmpdir, top, mode):
    rundir = os.path.join(tmpdir, 'rundir')
    rgy = PackageLoader().load_rgy(['std', 'formal', 'formal.sby'])
    builder = TaskGraphBuilder(rgy, rundir)
    files = builder.mkTaskNode('std.FileSet', name='files',
                               type='systemVerilogSource', base=DATA,
                               include='*.sv')
    case = builder.mkTaskNode('formal.sby.Case', name='case', top=top,
                              mode=mode, needs=[files])
    # The builder lets the task create the formal.FormalResult data item.
    runner = TaskSetRunner(rundir, builder=builder)
    out = asyncio.run(runner.run(case))
    trs = [o for o in out.output if getattr(o, 'type', '') == 'formal.FormalResult']
    assert len(trs) == 1, 'a Case emits exactly one FormalResult'
    return runner.status, trs[0]


@pytest.mark.skipif(not has_sby, reason='sby not installed')
@pytest.mark.parametrize('top,mode,status,passed', [
    ('counter_ok',    'bmc',   'pass',  True),
    ('counter_ok',    'prove', 'pass',  True),
    ('counter_ok',    'cover', 'pass',  True),
    ('counter_bad',   'bmc',   'fail',  False),
    ('counter_nocov', 'cover', 'fail',  False),
    ('no_such_top',   'bmc',   'error', False),
])
def test_case_verdict(tmpdir, top, mode, status, passed):
    run_status, tr = _run_case(tmpdir, top, mode)
    # The verdict is data: the task (and so the run) succeeds either way, and
    # a suite report decides the gate.
    assert run_status == 0
    assert (tr.status, tr.passed) == (status, passed)
    assert tr.attrs.get('mode') == mode


def test_sby_verdict_reads_status_file(tmpdir):
    d = str(tmpdir)
    assert _sby_verdict(d) == 'ERROR'            # sby never got that far
    with open(os.path.join(d, 'status'), 'w') as fp:
        fp.write('UNKNOWN 0 0\n')
    assert _sby_verdict(d) == 'UNKNOWN'
