
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

