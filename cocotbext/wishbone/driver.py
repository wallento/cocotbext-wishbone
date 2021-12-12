

import cocotb
from cocotb.triggers import RisingEdge, Event
from cocotb_bus.drivers import BusDriver
from cocotb.result import TestFailure
from cocotb.binary import BinaryValue
from cocotb.decorators import public


def is_sequence(arg):
    return (not hasattr(arg, "strip") and
            hasattr(arg, "__getitem__") or
            hasattr(arg, "__iter__"))


class WBAux():
    """
    Wishbone Auxiliary Wrapper Class

    wrap meta informations on bus transaction (internal only)
    """
    def __init__(self, sel=None, adr=0, datwr=None, waitStall=0, waitIdle=0, tsStb=0):
        self.sel        = sel
        self.adr        = adr
        self.datwr      = datwr
        self.waitIdle   = waitIdle
        self.waitStall  = waitStall
        self.ts         = tsStb


@public
class WBOp():
    """
    Wishbone Operations Wrapper Class

    an attempt to wrap em tidy

    Args:
        adr: address of the operation
        dat: data to write, None indicates a read cycle
        idle: number of clock cycles between asserting cyc and stb
        sel: the selection mask for the operation
        acktimeout: number of maximum clock cycles before asserting ack
    """
    def __init__(self, adr=0, dat=None, idle=0, sel=None, acktimeout=0):
        self.adr    = adr
        self.dat    = dat
        self.sel    = sel
        self.idle   = idle
        self.acktimeout = acktimeout


@public
class WBRes():
    """
    Wishbone Result Wrapper Class.

    What's happend on the bus plus meta information on timing
    """

    def __init__(self, ack=0, sel=None, adr=0, datrd=None, datwr=None, waitIdle=0, waitStall=0, waitAck=0):
        self.ack        = ack
        self.sel        = sel
        self.adr        = adr
        self.datrd      = datrd
        self.datwr      = datwr
        self.waitStall  = waitStall
        self.waitAck    = waitAck
        self.waitIdle   = waitIdle


# TODO: Use of pipelined operations
class Wishbone(BusDriver):
    """
    Wishbone
    """
    _signals = ["cyc", "stb", "we", "adr", "datwr", "datrd", "ack"]
    _optional_signals = ["sel", "err", "stall", "rty"]

    def __init__(self, entity, name, clock, width=32, signals_dict=None, **kwargs):
        if signals_dict is not None:
            self._signals=signals_dict
        BusDriver.__init__(self, entity, name, clock, **kwargs)
        # Drive some sensible defaults (setimmediatevalue to avoid x asserts)
        self._width = width
        self.bus.cyc.setimmediatevalue(0)
        self.bus.stb.setimmediatevalue(0)
        self.bus.we.setimmediatevalue(0)
        self.bus.adr.setimmediatevalue(0)
        self.bus.datwr.setimmediatevalue(0)

        if hasattr(self.bus, "sel"):
            v = self.bus.sel.value
            v.binstr = "1" * len(self.bus.sel)
            self.bus.sel.value = v


class WishboneMaster(Wishbone):
    """
    Wishbone master
    """
    def __init__(self, entity, name, clock, timeout=None, width=32, **kwargs):
        sTo = ", no cycle timeout"
        if timeout is not None:
            sTo = ", cycle timeout is %u clockcycles" % timeout
        self.busy_event         = Event("%s_busy" % name)
        self._timeout           = timeout
        self.busy               = False
        self._acked_ops         = 0
        self._res_buf           = []
        self._aux_buf           = []
        self._op_cnt            = 0
        self._clk_cycle_count   = 0
        Wishbone.__init__(self, entity, name, clock, width, **kwargs)
        self.log.info("Wishbone Master created%s" % sTo)

    async def _clk_cycle_counter(self):
        """
        Cycle counter to time bus operations
        """
        clkedge = RisingEdge(self.clock)
        self._clk_cycle_count = 0
        while self.busy:
            await clkedge
            self._clk_cycle_count += 1

    async def _open_cycle(self):
        #Open new wishbone cycle
        if self.busy:
            self.log.error("Opening Cycle, but WB Driver is already busy. Someting's wrong")
            await self.busy_event.wait()
            print('\n--------\nsarasa')
        self.busy_event.clear()
        self.busy       = True
        cocotb.fork(self._read())
        cocotb.fork(self._clk_cycle_counter()) 
        self.bus.cyc.value = 1
        self._acked_ops = 0  
        self._res_buf   = [] 
        self._aux_buf   = []
        self.log.debug("Opening cycle, %u Ops" % self._op_cnt)

    async def _close_cycle(self):
        #Close current wishbone cycle  
        clkedge = RisingEdge(self.clock)
        count           = 0
        last_acked_ops  = 0
        #Wait for all Operations being acknowledged by the slave before lowering the cycle line
        #This is not mandatory by the bus standard, but a crossbar might send acks to the wrong master
        #if we don't wait. We don't want to risk that, it could hang the bus
        while self._acked_ops < self._op_cnt:
            if last_acked_ops != self._acked_ops:
                self.log.debug("Waiting for missing acks: %u/%u" % (self._acked_ops, self._op_cnt) )
            last_acked_ops = self._acked_ops    
            #check for timeout when finishing the cycle            
            count += 1
            if (not (self._timeout is None)):
                if (count > self._timeout): 
                    raise TestFailure("Timeout of %u clock cycles reached when waiting for reply from slave" % self._timeout)                
            await clkedge

        self.busy = False
        self.busy_event.set()
        self.bus.cyc.value = 0
        self.log.debug("Closing cycle")
        await clkedge

    async def _wait_stall(self):
        """Wait for stall to be low before continuing (Pipelined Wishbone)
        """
        clkedge = RisingEdge(self.clock)
        count = 0
        if hasattr(self.bus, "stall"):
            count = 0            
            while self.bus.stall.value == 1:
                await clkedge
                count += 1
                if (not (self._timeout is None)):
                    if (count > self._timeout): 
                        raise TestFailure("Timeout of %u clock cycles reached when on stall from slave" % self._timeout)                
            self.log.debug("Stalled for %u cycles" % count)
        return count

    async def _wait_ack(self):
        """Wait for ACK on the bus before continuing (Non pipelined Wishbone)
        """
        #wait for acknownledgement before continuing - Classic Wishbone without pipelining
        clkedge = RisingEdge(self.clock)
        count = 0
        if hasattr(self.bus, "stall"):
            self.bus.stb.value = 0
        if self._acktimeout == 0:
            while not self._get_reply()[0] :
                await clkedge
                count += 1
        else:
            while (not self._get_reply()[0]) and (count < self._acktimeout) :
                await clkedge
                count += 1
        if (self._acktimeout != 0) and (count >= self._acktimeout):
            raise TestFailure("Timeout of %u clock cycles reached when waiting for acknowledge" % count)

        if not hasattr(self.bus, "stall"):
            self.bus.stb.value = 0
        self._acked_ops += 1
        self.log.debug("Waited %u cycles for ackknowledge" % count)

        return count

    def _get_reply(self):
        code = 0 # 0 if no reply, 1 for ACK, 2 for ERR, 3 for RTY
        ack = self.bus.ack.value == 1
        if ack:
            code = 1
        if hasattr(self.bus, "err") and self.bus.err.value == 1:
            if ack:
                raise TestFailure("Slave raised ACK and ERR line")
            ack = True
            code = 2
        if hasattr(self.bus, "rty") and self.bus.rty.value == 1:
            if ack:
                raise TestFailure("Slave raised {} and RTY line".format("ACK" if code == 1 else "ERR"))
            ack = True
            code = 3
        return ack, code

    async def _read(self):
        """
        Reader for slave replies
        """
        count = 0
        clkedge = RisingEdge(self.clock)
        while self.busy:
            ack, reply = self._get_reply()
            # valid reply?
            if ack:
                datrd = self.bus.datrd.value
                #append reply and meta info to result buffer
                tmpRes =  WBRes(ack=reply, sel=None, adr=None, datrd=datrd, datwr=None, waitIdle=None, waitStall=None, waitAck=self._clk_cycle_count)               
                self._res_buf.append(tmpRes)
                self._acked_ops += 1
            await clkedge
            count += 1

    async def _drive(self, we, adr, datwr, sel, idle):
        """
        Drive the Wishbone Master Out Lines
        """

        clkedge = RisingEdge(self.clock)
        if self.busy:
            # insert requested idle cycles
            if idle is not None:
                idlecnt = idle
                while idlecnt > 0:
                    idlecnt -= 1
                    await clkedge
            # drive outputs    
            self.bus.stb.value = 1
            self.bus.adr.value = adr
            if hasattr(self.bus, "sel"):
                self.bus.sel.value = sel if sel is not None else BinaryValue("1" * len(self.bus.sel))
            self.bus.datwr.value = datwr
            self.bus.we.value = we
            await clkedge
            #deal with flow control (pipelined wishbone)
            stalled = await self._wait_stall()
            #append operation and meta info to auxiliary buffer
            self._aux_buf.append(WBAux(sel, adr, datwr, stalled, idle, self._clk_cycle_count))
            await self._wait_ack()
            self.bus.we.value = 0
        else:
            self.log.error("Cannot drive the Wishbone bus outside a cycle!")

    async def send_cycle(self, arg):
        """
        The main sending routine

        Args:
            list(WishboneOperations)
        """
        cnt = 0
        clkedge = RisingEdge(self.clock)
        await clkedge
        if is_sequence(arg):
            self._op_cnt = len(arg)
            if self._op_cnt < 1:
                self.log.error("List contains no operations to carry out")
            else:
                result = []
                await self._open_cycle()

                for op in arg:
                    if not isinstance(op, WBOp):
                        raise TestFailure("Sorry, argument must be a list of WBOp (Wishbone Operation) objects!")    

                    self._acktimeout = op.acktimeout

                    if op.dat is not None:
                        we  = 1
                        dat = op.dat
                    else:
                        we  = 0
                        dat = 0
                    await self._drive(we, op.adr, dat, op.sel, op.idle)
                    if op.sel is not None:
                        self.log.debug("#%3u WE: %s ADR: 0x%08x DAT: 0x%08x SEL: 0x%1x IDLE: %3u" % (cnt, we, op.adr, dat, op.sel, op.idle))
                    else:
                        self.log.debug("#%3u WE: %s ADR: 0x%08x DAT: 0x%08x SEL: None  IDLE: %3u" % (cnt, we, op.adr, dat, op.idle))
                    cnt += 1

                await self._close_cycle()

                #do pick and mix from result- and auxiliary buffer so we get all operation and meta info
                for res, aux in zip(self._res_buf, self._aux_buf):
                    res.datwr       = aux.datwr
                    res.sel         = aux.sel
                    res.adr         = aux.adr
                    res.waitIdle    = aux.waitIdle
                    res.waitStall   = aux.waitStall
                    res.waitAck    -= aux.ts
                    result.append(res)

            return result
        else:
            raise TestFailure("Sorry, argument must be a list of WBOp (Wishbone Operation) objects!")
            return None
