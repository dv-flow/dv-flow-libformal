
from dv_flow.mgr import TaskDataInput, TaskDataOutput, TaskDataResult, TaskRunCtxt, FileSet

import os, shutil, asyncio

async def BMC(ctxt : TaskRunCtxt, input : TaskDataInput) -> TaskDataResult:
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
        fp.write('mode bmc\n')
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
        markers.append({'severity':'error','msg':'sby failed; see log', 'logfile':f'{top}.log'})
    else:
        markers.append({'severity':'info','msg':'sby completed', 'logfile':f'{top}.log'})

    output = [FileSet(src=input.name, filetype='formalDir', basedir=rundir)]
    return TaskDataResult(status=status, output=output, changed=True, markers=markers)