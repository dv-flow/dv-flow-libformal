
# formal.sby.BMC Task

This task runs the Symbiyosys tool on the input set of source files.
- Collect Verilog and SystemVerilog files, defines, and include paths. 
  See libhdlsim/vl_sim_image_builder.py for an example of how to do this.
- The task must accept a 'top' parameter. 
- Create a <top>.sby config file
  - Options section must specify 'mode bmc' and 'depth <depth>' (default 20)
  - Engines section must specify 'smtbmc boolector'
  - Script section must contain 'read_verilog -sv' followed by source files, defines, includes.
    Then, 'prep -top <top>'

Here is an example:

```
[options]
mode bmc
depth 20

[engines]
smtbmc boolector

[script]
read_verilog -sv \
  -I/home/mballance/projects/featherweight-vip/fwvip-wb/packages/fwprotocol-defs/verilog/rtl \
  /home/mballance/projects/featherweight-vip/fwvip-wb/src/verif/formal/trial/fwvip_wb_initiator_top.sv
prep -top fwvip_wb_initiator_top
```

Specifying options to 'read_verilog':
- Include: -I<path>
- Define: -D<sym>[=<value>]
- Must be a single line

Remove the ${{rundir}}/<top> directory if it exists
Run Symbiyosys like this: sby <top>.sby


# formal.sby.Cover Task

Companion to `BMC`, identical inputs/parameters (`top`, `depth`), but the Options
section specifies `mode cover` instead of `mode bmc`. SymbiYosys then searches (up to
`depth`) for a trace that reaches every `cover()` statement in the design and FAILS if
any cover is unreachable. This is the reachability / non-vacuity check that complements
BMC: `BMC` proves the `assert`/`assume` properties hold but ignores `cover`s, while
`Cover` proves the `cover`s are reachable but ignores `assert`s. Run both for a result
that is both correct and non-vacuous.

```
[options]
mode cover
depth 20

[engines]
smtbmc boolector

[script]
read_verilog -sv ...
prep -top <top>
```

(Both tasks share the runner `dv_flow.libformal.sby_bmc._run_sby(mode=...)`.)


# formal.sby.Case Task

Runs one proof (`mode`: `bmc`, `cover` or `prove`; `top`, `depth`) as a **test
case**. The sby verdict is data: the task succeeds whatever the verdict, and it
emits a `formal.FormalResult`, which a `std.TestSuite` / `std.TestRunner` rolls
up and the run record (`rundir/out/<run-id>/results.json`) shows like any other
test.

`formal.FormalResult` (`uses: std.TestResult`, so a `std.Result`):

| field | content |
|---|---|
| `status` | `pass` (PASS), `fail` (FAIL), `timeout` (TIMEOUT), `error` (UNKNOWN -- an inconclusive proof -- or ERROR) |
| `msg` | the first failed assertion (`assertion failed at counter.sv:14 in step 14`) or unreached cover |
| `checks` | `assertions` (`failed == 0`; bmc/prove), `covers` (`unreached == 0`; cover), `proof` (why there is no clean verdict) |
| `attrs` | `engine` (`smtbmc boolector`), `mode`, `top`, `verdict`, `depth_goal` |
| `metrics` | `depth` (the last step checked), `failed`, `proven`, `unknown`, `covered`, `unreached`, `walltime_s` |
| `diagnostics` | one per failed assertion / unreached cover: `loc` is the line in `<top>.log`, `src_loc` the property's source line |
| `artifacts` | `<top>.log` (`role=log`) and each counterexample / cover trace (`role=waves`) |

Properties are diagnostics rather than child results: a proof is one test case,
and children would make the run record count its properties as tests.

`formal.vcf.Run` emits a `formal.FormalResult` too, from the proven / falsified /
inconclusive / covered / vacuous counts in `vcf.log` (`fail` on a falsified
property, `error` when vcf fails without one).
