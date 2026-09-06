module dump;
    initial begin
        $dumpfile("waveform.vcd");
        $dumpvars(0, fifo);
    end
endmodule
