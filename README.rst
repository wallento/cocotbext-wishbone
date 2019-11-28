cocotb modules for Wishbone bus
===============================

This register contains the cocotb driver and monitor modules for the
Wishbone bus.

Install
-------

From Github
^^^^^^^^^^^

* Clone the repository::

    $ git clone https://github.com/wallento/cocomod-wishbone.git

* Then install it with pip::

    $ python -m pip install -e cocomod-wishbone

From pip global
^^^^^^^^^^^^^^^

To install it with pip published globally simply use pip install as usual::

    $ python -m pip install cocomod-wishbone

How to use it
-------------

Driver
^^^^^^

As an example we will instanciate a Wishbone master cocotb driver to read and
write on our DUT wishbone slave.
First import this ::

  from cocomod.wishbone.driver import WishboneMaster
  from cocomod.wishbone.driver import WBOp

The DUT ports naming in Verilog is following::

  input         clock,
  input  [1:0]  io_wbs_adr,
  input  [15:0] io_wbs_datwr,
  output [15:0] io_wbs_datrd,
  input         io_wbs_we,
  input         io_wbs_stb,
  output        io_wbs_ack,
  input         io_wbs_cyc,

To initialize our master we have to do this::

  self.wbs = WishboneMaster(dut, "io_wbs", dut.clock,
                            width=16,   # size of data bus
                            timeout=10) # in clock cycle number


But in actuals port name are rarely the same has seen above. It this case – for
example actuals ports names are::

  input         clock
  input  [1:0]  io_wbs_adr_i,
  input  [15:0] io_wbs_dat_i,
  output [15:0] io_wbs_dat_o,
  input         io_wbs_we_i,
  input         io_wbs_stb_i,
  output        io_wbs_ack_o,
  input         io_wbs_cyc_i,

Then we have to rename it with signals_dict arguments::

  self.wbs = WishboneMaster(dut, "io_wbs", dut.clock,
                            width=16,   # size of data bus
                            timeout=10, # in clock cycle number
                            signals_dict={"cyc":  "cyc_i",
                                        "stb":  "stb_i",
                                        "we":   "we_i",
                                        "adr":  "adr_i",
                                        "datwr":"dat_i",
                                        "datrd":"dat_o",
                                        "ack":  "ack_o" })

In the testbench, to make read/write access we have to use the method
send_cycle() with a list of special class operator named WBOp().

WBOp() accepting following arguments, all with default value::

        adr: address of the operation
        dat: data to write, None indicates a read cycle
        idle: number of clock cycles between asserting cyc and stb
        sel: the selection mask for the operation

        WBOp(adr=0, dat=None, idle=0, sel=None)

If no dat is given, a wishbone read will be done. If dat is filled, it will be a
write.

For example, to read respectively at adress 2,3,0 then 1. We will do::

    wbRes = yield rdbg.wbs.send_cycle([WBOp(2), WBOp(3), WBOp(0), WBOp(1)])

send_cycle() method return a list of Wishbone Result Wrapper Class WBRes() with
some data declared like it in driver.py::

    def __init__(self, ack=0, sel=None, adr=0, datrd=None, datwr=None, waitIdle=0, waitStall=0, waitAck=0):

If we want to print value read, we just have to read datrd value like that::

    rvalues = [wb.datrd for wb in wbRes]
    dut.log.info(f"Returned values : {rvalues}")

Which will print a log message like following::
   1560.00ns INFO     Returned values : [0000000000000000, 0000000000000000, 0000000100000001, 0000000000000000]

We can add some write operations in our send_cycle(), by adding a second value
in parameters::

  wbRes = yield rdbg.wbs.send_cycle([WBOp(3, 0xcafe), WBOp(0), WBOp(3)])

The above line will write 0xcafe at address 3, then read at address 0, then read at
address 3.

Monitor
^^^^^^^

TODO
