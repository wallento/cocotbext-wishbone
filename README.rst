cocotb modules for Wishbone bus
===============================

This register contains the cocotb driver and monitor modules for the
Wishbone bus.

Install
-------

From Github
^^^^^^^^^^^

* Clone the repository::

    $ git clone https://github.com/wallento/cocotbext-wishbone.git

* Then install it with pip::

    $ python -m pip install -e cocotbext-wishbone

From pip global
^^^^^^^^^^^^^^^

To install it with pip published globally simply use pip install as usual::

    $ python -m pip install cocotbext-wishbone

How to use it
-------------

Driver
^^^^^^

As an example we will instanciate a Wishbone master cocotb driver to read and
write on our DUT wishbone slave.
First import this ::

  from cocotbext.wishbone.driver import WishboneMaster
  from cocotbext.wishbone.driver import WBOp

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

Monitor instantiation works similarly to Driver instantiation. First import
right module ::

  from cocotbext.wishbone.monitor import WishboneSlave

Then instantiate the object with right signals names ::

  wbm = WishboneSlave(dut, "io_wbm", dut.clock,
                   width=16,   # size of data bus
                   signals_dict={"cyc":  "cyc_o",
                               "stb":  "stb_o",
                               "we":   "we_o",
                               "adr":  "adr_o",
                               "datwr":"dat_o",
                               "datrd":"dat_i",
                               "ack":  "ack_i" })

WishboneSlave is a monitor, then it's mainly passive class. It will supervise
the wishbone signal and records transaction in a list named _recvQ.
Each time the monitor detect a transaction on the bus, the transaction is append
to the _recvQ.

A transaction is a list of WBRes object wich contain some signals values read on
the bus ::

    @public
    class WBRes():
    ...
        def __init__(...):
            self.ack        = ack
            self.sel        = sel
            self.adr        = adr
            self.datrd      = datrd
            self.datwr      = datwr
            self.waitStall  = waitStall
            self.waitAck    = waitAck
            self.waitIdle   = waitIdle

At the end of simulation if we want to display adr, datr and datwr value
occured on the bus we will do following for example ::
    
      for transaction in wbm._recvQ:
        wbm.log.info(f"{[f'@{hex(v.adr)}r{hex(v.datrd)}w{hex(0 if v.datwr is None else v.datwr)}' for v in transaction]}")
    
We can also register a callback function that will be called each time a
transaction occured::

  def simple_callback(transaction):
      print(transaction)

  wbm.add_callback(simple_callback)

But be aware that if a callback is registered, the _recvQ will not be populated.

Projects using this module
--------------------------

Here some project that use this module. Can be usefull to have examples:

- [ChisArmadeus](https://github.com/Martoni/ChisArmadeus): Usefull chisel components for Armadeus boards. It use cocotb for
  testing. An example is given for op6ul wrapper test [here](https://github.com/Martoni/ChisArmadeus/tree/master/cocotb/op6sp)

- [wbGPIO](https://github.com/Martoni/wbGPIO): General purpose input output
  wishbone slave written in Chisel. Cocotb testbench is available [here](https://github.com/Martoni/wbGPIO/tree/master/cocotb/gpio)
