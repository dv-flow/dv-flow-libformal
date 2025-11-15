##################
DV Flow LibFormal
##################

LibFormal is a DV-Flow library that provides tasks for running formal tools.
This library currently provides a task for running SymbiYosys in Bounded Model Checking (BMC) mode.

.. contents::
    :depth: 2


Task: BMC
=========
The BMC task runs SymbiYosys on the provided Verilog/SystemVerilog sources using mode bmc.
It generates a <top>.sby configuration with an [options] section containing mode bmc and depth <depth>,
then invokes sby.

Example
-------

.. code-block:: yaml

    package:
      name: formal_example

      tasks:
        - name: rtl
          uses: std.FileSet
          with:
            type: systemVerilogSource
            include: "*.sv"

        - name: bmc
          uses: formal.sby.BMC
          with:
            top: [top]
            depth: 20  # optional; default is 20
          needs: [rtl]

Consumes
--------

* systemVerilogSource
* verilogSource

Produces
--------

* formalDir

Parameters
----------

* top - [Required] Name of the top module (string or single-element list)
* depth - [Optional] Maximum bound for BMC search; default 20
