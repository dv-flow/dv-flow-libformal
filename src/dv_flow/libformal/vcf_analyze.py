import os
import logging
from typing import List
from dv_flow.mgr import TaskDataResult, TaskRunCtxt, FileSet

_log = logging.getLogger("formal.vcf.Analyze")


async def Analyze(ctxt: TaskRunCtxt, input) -> TaskDataResult:
    """Compile HDL + SVA sources with vlogan for VC Formal."""
    status = 0
    markers = []
    output = []

    files: List[str] = []
    incdirs: List[str] = []
    defines: List[str] = []
    has_sv = False

    for fs in input.inputs:
        if getattr(fs, 'type', None) != 'std.FileSet':
            continue

        ftype = getattr(fs, 'filetype', None)

        if ftype in ('verilogSource', 'systemVerilogSource'):
            has_sv = has_sv or (ftype == 'systemVerilogSource')
            for f in fs.files:
                path = os.path.join(fs.basedir, f)
                files.append(path)
            for inc in getattr(fs, 'incdirs', []):
                d = os.path.join(fs.basedir, inc)
                if d not in incdirs:
                    incdirs.append(d)
            defines.extend(getattr(fs, 'defines', []))

        elif ftype in ('verilogInclude', 'systemVerilogInclude'):
            has_sv = has_sv or (ftype == 'systemVerilogInclude')
            for inc in getattr(fs, 'incdirs', []):
                d = os.path.join(fs.basedir, inc)
                if d not in incdirs:
                    incdirs.append(d)
            defines.extend(getattr(fs, 'defines', []))

        elif ftype == 'verilogIncDir':
            if fs.basedir.strip():
                if fs.basedir not in incdirs:
                    incdirs.append(fs.basedir)

    for inc in getattr(input.params, 'incdirs', []):
        if inc.strip() and inc not in incdirs:
            incdirs.append(inc)
    defines.extend(getattr(input.params, 'defines', []))

    files = list(dict.fromkeys(files))
    incdirs = list(dict.fromkeys(incdirs))
    defines = list(dict.fromkeys(defines))

    if not files:
        markers.append({'severity': 'error', 'msg': 'No source files provided'})
        return TaskDataResult(status=1, output=[], changed=False, markers=markers)

    work_lib = getattr(input.params, 'work_lib', 'work') or 'work'
    work_dir = os.path.join(input.rundir, work_lib)
    os.makedirs(work_dir, exist_ok=True)

    setup_path = os.path.join(input.rundir, 'synopsys_sim.setup')
    with open(setup_path, 'w') as fp:
        fp.write(f"{work_lib}: {work_dir}\n")

    cmd = ['vlogan', '-full64', '-work', work_lib]

    if has_sv:
        cmd.append('-sverilog')

    for inc in incdirs:
        cmd.append(f'+incdir+{inc}')
    for d in defines:
        cmd.append(f'+define+{d}')

    extra_args = getattr(input.params, 'args', []) or []
    cmd.extend(extra_args)

    cmd.extend(files)

    ffile = os.path.join(input.rundir, 'vlogan.f')
    with open(ffile, 'w') as fp:
        for elem in cmd[1:]:
            fp.write(f"{elem}\n")

    _log.info("Running vlogan with %d files, %d incdirs", len(files), len(incdirs))
    status = await ctxt.exec(cmd, logfile="vlogan.log")

    if status != 0:
        markers.append({'severity': 'error', 'msg': 'vlogan compilation failed; see vlogan.log'})
    else:
        markers.append({'severity': 'info', 'msg': f'vlogan compiled {len(files)} files'})

    output.append(FileSet(
        src=input.name,
        filetype="formalLib",
        basedir=input.rundir,
    ))

    return TaskDataResult(
        status=status,
        output=output,
        changed=True,
        markers=markers,
    )
