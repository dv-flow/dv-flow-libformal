import os
import sys
# Ensure local packages are importable without installation
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(_repo_root, 'src'))
sys.path.insert(0, os.path.join(_repo_root, 'packages', 'dv-flow-mgr', 'src'))
import shutil
import asyncio
import pytest
from dv_flow.mgr import TaskSetRunner, TaskGraphBuilder, PackageLoader, TaskListenerLog

has_sby = shutil.which('sby') is not None
# if has_sby:
#     try:
#         import subprocess
#         subprocess.run(['sby','-V'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
#     except Exception:
#         print("Exception")
#         has_sby = False

@pytest.mark.skipif(not has_sby, reason='sby not installed')
def test_bmc_smoke(tmpdir):
    data_dir = os.path.join(os.path.dirname(__file__), 'data', 'formal_smoke')

    runner = TaskSetRunner(os.path.join(tmpdir, 'rundir'))

    def marker_listener(marker):
        # Fail test on any error marker
        if getattr(marker, 'severity', None) and str(marker.severity).endswith('Error'):
            raise Exception(f"Marker error: {marker.msg}")

    rgy = PackageLoader(marker_listeners=[marker_listener]).load_rgy(['std', 'formal.sby'])
    builder = TaskGraphBuilder(rgy, os.path.join(tmpdir, 'rundir'))

    files = builder.mkTaskNode('std.FileSet',
                               name='files',
                               type='systemVerilogSource',
                               base=data_dir,
                               include='*.sv')

    bmc = builder.mkTaskNode('formal.sby.BMC',
                             name='bmc',
                             top=['smoke'],
                             needs=[files])

    runner.add_listener(TaskListenerLog().event)
    out = asyncio.run(runner.run(bmc))

    assert runner.status == 0

    formal_fs = None
    for fs in out.output:
        if fs.type == 'std.FileSet' and fs.filetype == 'formalDir' and fs.src == 'bmc':
            formal_fs = fs
            break

    assert formal_fs is not None
    # Expect generated sby file
    assert os.path.isfile(os.path.join(formal_fs.basedir, 'bmc', 'smoke', 'engine_0', 'logfile.txt')) or os.path.isfile(os.path.join(formal_fs.basedir, 'smoke.sby'))
    # At least the .sby config should exist
    assert os.path.isfile(os.path.join(formal_fs.basedir, 'smoke.sby'))
