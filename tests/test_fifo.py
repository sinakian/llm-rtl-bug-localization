import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

@cocotb.test()
async def comprehensive_fifo_test(dut):
    # Start a 10ns clock
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    # Initialize inputs
    dut.rst.value = 1
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.data_in.value = 0

    # Apply Reset
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Catches Bug 5 (wrong_reset)
    assert dut.empty.value == 1, f"Expected empty=1 after reset, got {dut.empty.value}"

    # Write 8 items to completely fill the FIFO
    dut.wr_en.value = 1
    for i in range(8):
        dut.data_in.value = i + 10  # Arbitrary data: 10, 11, 12...
        await RisingEdge(dut.clk)
    dut.wr_en.value = 0

    # Catches Bug 3 (off_by_one on the full flag)
    assert dut.full.value == 1, f"Expected full=1 after 8 writes, got {dut.full.value}"

    # Read items back
    dut.rd_en.value = 1
    for i in range(8):
        await RisingEdge(dut.clk)
        # Catches Bugs 1 & 2 (operator_flip on pointers) and Bug 4 (stuck_at)
        expected_val = i + 10
        assert dut.data_out.value == expected_val, f"Read {i}: Expected {expected_val}, got {dut.data_out.value}"
    dut.rd_en.value = 0

