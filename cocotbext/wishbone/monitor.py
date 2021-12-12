
import cocotb
from itertools import repeat
from cocotb_bus.monitors    import BusMonitor
from cocotb.triggers    import RisingEdge
from cocotb.result      import TestFailure
from cocotb.decorators  import public  
try:
    from Queue import Queue # Python 2.x
except ImportError:
    from queue import Queue


class WBAux():
    """Wishbone Auxiliary Wrapper Class, wrap meta informations on bus transaction (internal only)
    """
    def __init__(self, sel=0xf, adr=0, datwr=None, waitStall=0, waitIdle=0, tsStb=0):
        self.adr        = adr
        self.datwr      = datwr        
        self.sel        = sel
        self.waitStall  = waitStall
        self.ts         = tsStb
        self.waitIdle   = waitIdle

@public
class WBRes():
    """Wishbone Result Wrapper Class. What's happend on the bus plus meta information on timing
    """
    def __init__(self, ack=0, sel=0xf, adr=0, datrd=None, datwr=None,
                 waitIdle=0, waitStall=0, waitAck=0):
        self.ack        = ack
        self.sel        = sel
        self.adr        = adr
        self.datrd      = datrd
        self.datwr      = datwr
        self.waitStall  = waitStall
        self.waitAck    = waitAck
        self.waitIdle   = waitIdle

    def to_dict(self):
        return {
         "ack"      :self.ack,
         "sel"      :self.sel,
         "adr"      :self.adr,
         "datrd"    :self.datrd,
         "datwr"    :self.datwr,
         "waitStall":self.waitStall,
         "waitAck"  :self.waitAck,
         "waitIdle" :self.waitIdle}


class Wishbone(BusMonitor):
    """Wishbone
    """
    
    _signals = ["cyc", "stb", "we", "adr", "datwr", "datrd", "ack"]
    _optional_signals = ["sel", "err", "stall", "rty"]
    replyTypes = {1 : "ack", 2 : "err", 3 : "rty"}  

    def __init__(self, entity, name, clock, signals_dict=None, **kwargs):
        if signals_dict is not None:
            self._signals=signals_dict
        self._width = kwargs.pop('width', 32)
        BusMonitor.__init__(self, entity, name, clock, **kwargs)
        # Drive some sensible defaults (setimmediatevalue to avoid x asserts)
        self.bus.ack.setimmediatevalue(0)
        self.bus.datrd.setimmediatevalue(0)
        if hasattr(self.bus, "err"):        
            self.bus.err.setimmediatevalue(0)
        if hasattr(self.bus, "stall"): 
            self.bus.stall.setimmediatevalue(0)
        if hasattr(self.bus, "rty"):        
            self.bus.rty.setimmediatevalue(0)    


class WishboneSlave(Wishbone):
    """Wishbone slave
    """
    
    def bitSeqGen(self, tupleGen):
        while True: 
            [highCnt, lowCnt] = next(tupleGen)
            #make sure there's at least one low cycle in here            
            if lowCnt < 1:
                lowCnt = 1
            bits = []
            for i in range(0, highCnt):
                bits.append(1)
            for i in range(0, lowCnt):
                bits.append(0)
            for bit in bits:
                yield bit
    
    def __init__(self, entity, name, clock, **kwargs):
        datGen = kwargs.pop('datgen', None)
        ackGen = kwargs.pop('ackgen', None)
        waitAckGen = kwargs.pop('waitreplygen', None)
        waitStallGen = kwargs.pop('waitstallgen', None)
        #init instance variables
        self._acked_ops      = 0  # ack cntr. wait for equality with
                                  # number of Ops before releasing lock
        self._reply_Q        = Queue() # save datwr, sel, idle
        self._res_buf        = [] # save readdata/ack/err/rty
        self._clk_cycle_count = 0
        self._cycle          = False
        self._lastTime       = 0
        self._stallCount     = 0

        #init instance generators
        self._datGen            = repeat(int(0))
        if datGen is not None:
            self._datGen        = datGen
        self._ackGen            = repeat(int(1))
        if ackGen is not None:
            self._ackGen        = ackGen
        self._waitAckGen        = repeat(int(0))
        if waitAckGen is not None:
            self._waitAckGen    = waitAckGen
        self._waitStallGen      = repeat(int(0))
        if waitStallGen is not None:
            self._waitStallGen  = self.bitSeqGen(waitStallGen)

        Wishbone.__init__(self, entity, name, clock, **kwargs)
        cocotb.fork(self._stall())
        cocotb.fork(self._clk_cycle_counter())
        cocotb.fork(self._ack())

    async def _clk_cycle_counter(self):
        """
        """
        clkedge = RisingEdge(self.clock)
        self._clk_cycle_count = 0
        while True:
            if self._cycle:
                self._clk_cycle_count += 1
            else:
                self._clk_cycle_count = 0
            await clkedge

    async def _stall(self):
        clkedge = RisingEdge(self.clock)
        # if stall drops, keep the value for one more clock cycle
        while True:
            if hasattr(self.bus, "stall"):
                tmpStall = next(self._waitStallGen)
                self.bus.stall.value = tmpStall
                if bool(tmpStall):                                
                    self._stallCount += 1                    
                    await clkedge
                else:
                    await clkedge
                    self._stallCount = 0
            else:
                break

    async def _ack(self):
        clkedge = RisingEdge(self.clock)         
        while True:
            #set defaults
            self.bus.ack.value = 0
            self.bus.datrd.value = 0
            if hasattr(self.bus, "err"):
                self.bus.err.value = 0
            if hasattr(self.bus, "rty"):
                self.bus.rty.value = 0
            
            if not self._reply_Q.empty():
                #get next reply from queue                    
                rep = self._reply_Q.get_nowait()
                
                #wait <waitAck> clock cycles before replying
                if rep.waitAck is not None:
                    waitcnt = rep.waitAck
                    while waitcnt > 0:
                        waitcnt -= 1
                        await clkedge
                
                #check if the signal we want to assign exists and assign
                if not hasattr(self.bus, self.replyTypes[rep.ack]):                
                    raise TestFailure("Tried to assign <%s> (%u) to slave reply, but this slave does not have a <%s> line" % (self.replyTypes[rep.ack], rep.ack, self.replyTypes[rep.ack]))
                if self.replyTypes[rep.ack]    == "ack":
                    self.bus.ack.value = 1
                elif self.replyTypes[rep.ack]  == "err":
                    self.bus.err.value = 1
                elif self.replyTypes[rep.ack]  == "rty":
                    self.bus.rty.value = 1
                self.bus.datrd.value = rep.datrd
            await clkedge

    def _respond(self):
        valid = self.bus.cyc.value and self.bus.stb.value
        #if there is a stall signal, take it into account        
        if hasattr(self.bus, "stall"):
            valid = valid and not self.bus.stall.value
        
        if valid:
            #wait before replying ?    
            waitAck = next(self._waitAckGen)
            #Response: rddata/don't care        
            if not self.bus.we.value:
                rd = next(self._datGen)
            else:
                rd = 0
         
            #Response: ack/err/rty
            reply = next(self._ackGen)
            if reply not in self.replyTypes:
                raise TestFailure("Tried to assign unknown reply type (%u) to slave reply. Valid is 1-3 (ack, err, rty)" %  reply)
            
            wr = None
            if self.bus.we.value:
                wr = self.bus.datwr.value
            
            #get the time the master idled since the last operation
            #TODO: subtract our own stalltime or, if we're not pipelined, time since last ack    
            idleTime = self._clk_cycle_count - self._lastTime -1    
            _sel = self.bus.sel.value if hasattr(self.bus, "sel") else None
            res = WBRes(ack=reply, sel=_sel, adr=self.bus.adr.value, datrd=rd, datwr=wr,
                        waitIdle=idleTime, waitStall=self._stallCount, waitAck=waitAck)
            
            #add whats going to happen to the result buffer
            self._res_buf.append(res)
            #add it to the reply queue for assignment. we need to process
            # ops every cycle, so we can't do the <waitreply> delay here
            self._reply_Q.put(res)
            self._lastTime = self._clk_cycle_count

    async def _monitor_recv(self):
        clkedge = RisingEdge(self.clock)
        #respond and notify the callback function
        while True:
            try:
                if self._cycle == 1 and self.bus.cyc.value == 0:
                    self._recv(self._res_buf)
                    self._reply_Q.queue.clear()
                    self._res_buf = []
            except ValueError:
                pass

            while self.bus.stb.value.binstr != '1':
                await clkedge
            try:
                if self._cycle == 0 and self.bus.cyc.value == 1:
                    self._lastTime = self._clk_cycle_count -1
            except ValueError:
                pass

            self._respond()
            # wait for response
            while self.bus.ack.value.binstr != '1':
                if hasattr(self.bus, "err"):
                    if self.bus.err.value.binstr == '1':
                        break
                if hasattr(self.bus, "rty"):
                    if self.bus.rty.value.binstr == '1':
                        break
                await clkedge

            self._cycle = self.bus.cyc.value
            await clkedge
