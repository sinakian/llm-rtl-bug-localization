SIM ?= icarus
TOPLEVEL_LANG ?= verilog

PWD=$(shell pwd)
VERILOG_SOURCES = $(PWD)/../src/fifo.v $(PWD)/dump.v

TOPLEVEL = fifo
MODULE = test_fifo

include $(shell cocotb-config --makefiles)/Makefile.sim
