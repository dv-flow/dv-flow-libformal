
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

