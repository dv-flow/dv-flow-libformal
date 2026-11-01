
from dv_flow.mgr import TaskDataInput, TaskDataOutput, TaskDataResult, TaskRunCtxt, FileSet

import os, shutil, asyncio

async def _run_sby(ctxt : TaskRunCtxt, input : TaskDataInput, mode : str) -> TaskDataResult:
    """Shared SymbiYosys runner. `mode` selects the proof mode: 'bmc' (prove the
    assert/assume properties up to `depth`) or 'cover' (find a trace reaching every
    cover() statement within `depth`; FAILS if any cover is unreachable)."""
    # Gather SV/V sources, defines, include dirs
    sources = []
    incdirs = []
    defines = []
    for fs in getattr(input, 'inputs', []):
        try:
            ftype = fs.filetype
        except Exception:
            ftype = None
        if getattr(fs, 'type', None) == 'std.FileSet':
            if ftype in ('systemVerilogSource','verilogSource'):
                for f in fs.files:
                    sources.append(os.path.join(fs.basedir, f))
                incdirs.extend([os.path.join(fs.basedir, i) for i in getattr(fs,'incdirs',[])])
                defines.extend(getattr(fs,'defines',[]))
            elif ftype in ('verilogInclude','systemVerilogInclude','verilogIncDir'):
                incdirs.extend([os.path.join(fs.basedir, i) for i in getattr(fs,'incdirs',[])])
                defines.extend(getattr(fs,'defines',[]))
        # allow defines/incdirs from other datasets
        if getattr(fs,'defines',None):
            defines.extend(fs.defines)
        if getattr(fs,'incdirs',None):
            incdirs.extend([d for d in fs.incdirs if len(d.strip())>0])
    # Deduplicate
    sources = list(dict.fromkeys(sources))
    incdirs = list(dict.fromkeys(incdirs))
    defines = list(dict.fromkeys(defines))

    # Determine top
    top = None
    if hasattr(input, 'params') and hasattr(input.params, 'top') and input.params.top:
        # top may be list
        if isinstance(input.params.top, (list, tuple)):
            top = input.params.top[0]
        else:
            top = input.params.top
    if top is None:
        return TaskDataResult(status=1, output=[], changed=False, markers=[{'severity':'error','msg':'Top module not specified'}])

    rundir = input.rundir
    os.makedirs(rundir, exist_ok=True)
    # Remove existing <top> dir under rundir if present
    top_dir = os.path.join(rundir, top)
    if os.path.isdir(top_dir):
        shutil.rmtree(top_dir)

    # Write SBY file
    sby_path = os.path.join(rundir, f"{top}.sby")
    with open(sby_path, 'w') as fp:
        depth = 20
        if hasattr(input, 'params') and hasattr(input.params, 'depth') and getattr(input.params, 'depth') is not None:
            try:
                depth = int(input.params.depth)
            except Exception:
                pass
        fp.write('[options]\n')
        fp.write(f'mode {mode}\n')
        fp.write(f'depth {depth}\n\n')
        fp.write('[engines]\n')
        fp.write('smtbmc boolector\n\n')
        fp.write('[script]\n')
        fp.write('read_verilog -sv')
        for inc in incdirs:
            fp.write(f' -I{inc}')
        for d in defines:
            fp.write(f' -D{d}')
        for s in sources:
            fp.write(f' {s}')
        fp.write('\n')
        fp.write(f'prep -top {top}\n')

    # Run sby via TaskRunCtxt.exec
    status = await ctxt.exec(['sby', f'{top}.sby'], cwd=rundir, logfile=f'{top}.log')
    markers = []
    if status != 0:
        markers.append({'severity':'error','msg':f'sby ({mode}) failed; see log', 'logfile':f'{top}.log'})
    else:
        markers.append({'severity':'info','msg':f'sby ({mode}) completed', 'logfile':f'{top}.log'})

    output = [FileSet(src=input.name, filetype='formalDir', basedir=rundir)]
    return TaskDataResult(status=status, output=output, changed=True, markers=markers)


def _sby_verdict(workdir : str):
    """The sby verdict from <workdir>/status ('PASS 0 0', 'FAIL ...',
    'ERROR ...', 'UNKNOWN ...', 'TIMEOUT ...'); 'ERROR' when sby wrote none
    (it never got as far as running an engine)."""
    try:
        with open(os.path.join(workdir, 'status')) as fp:
            words = fp.read().split()
        return words[0].upper() if words else 'ERROR'
    except OSError:
        return 'ERROR'


async def BMC(ctxt : TaskRunCtxt, input : TaskDataInput) -> TaskDataResult:
    """Bounded model check: prove the assert/assume properties hold up to `depth`."""
    return await _run_sby(ctxt, input, 'bmc')


async def Cover(ctxt : TaskRunCtxt, input : TaskDataInput) -> TaskDataResult:
    """Cover: find, within `depth`, a trace reaching every cover() statement. FAILS if
    any cover is unreachable -- the standard non-vacuity / reachability check that
    complements BMC (which checks asserts but ignores covers)."""
    return await _run_sby(ctxt, input, 'cover')


_MODES = ('bmc', 'cover', 'prove')


async def Case(ctxt : TaskRunCtxt, input : TaskDataInput) -> TaskDataResult:
    """Run one SymbiYosys proof as a TEST CASE: the sby verdict becomes a
    formal.FormalResult (a std.TestResult; see formal_result.py), and the
    task itself succeeds whatever the verdict, so one failing proof never
    aborts a suite -- the suite's runner is the gate, exactly as for a
    simulation case.

    `mode` is the sby mode: bmc (asserts up to depth), cover (every cover()
    reachable within depth -- the non-vacuity check) or prove (unbounded, by
    k-induction). Only PASS passes; FAIL, UNKNOWN (an inconclusive proof),
    TIMEOUT and ERROR do not.
    """
    import time
    mode = (getattr(input.params, 'mode', '') or 'bmc').lower()
    if mode not in _MODES:
        return TaskDataResult(status=1, markers=[{'severity':'error',
            'msg':"formal.sby.Case: mode '%s' is not one of %s" % (mode, ', '.join(_MODES))}])

    t0 = time.time()
    run = await _run_sby(ctxt, input, mode)
    walltime = time.time() - t0

    top = input.params.top
    if isinstance(top, (list, tuple)):
        top = top[0] if top else ''
    verdict = _sby_verdict(os.path.join(input.rundir, top)) if top else 'ERROR'
    passed = (verdict == 'PASS')
    status = {'PASS':'pass', 'FAIL':'fail', 'TIMEOUT':'timeout'}.get(verdict, 'error')

    name = getattr(input.params, 'name', '') or input.name
    from dv_flow.libformal.formal_result import mk_formal_result
    workdir = os.path.join(input.rundir, top) if top else input.rundir
    tr = mk_formal_result(
        ctxt, name=name, task=input.name, rundir=input.rundir, mode=mode,
        top=top or '', verdict=verdict,
        log_path=os.path.join(input.rundir, '%s.log' % top) if top else '',
        workdir=workdir, depth_goal=int(getattr(input.params, 'depth', 0) or 0),
        walltime_s=walltime)
    tr.src = name  # distinct per case -> no dedup when a report gathers cases

    if not passed:
        ctxt.info("Case '%s': sby %s on %s returned %s; see %s.log" % (
            name, mode, top, verdict, top))

    # A setup error (no top) already returned above; everything sby itself
    # reports is a verdict, carried as data.
    return TaskDataResult(status=0, changed=True, output=run.output + [tr],
                          markers=[m for m in run.markers
                                   if (m.get('severity') if isinstance(m, dict) else None) != 'error'])
