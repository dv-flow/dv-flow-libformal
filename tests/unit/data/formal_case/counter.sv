// A mod-10 counter, three ways, for formal.sby.Case:
//   counter_ok     the assert holds (bmc and prove pass); the cover is reachable
//   counter_bad    the assert fails within the default depth
//   counter_nocov  the assert holds, but the cover can never be reached
module counter_ok(input clk);
    reg [3:0] c = 0;
    always @(posedge clk) c <= (c == 9) ? 4'd0 : c + 4'd1;
    always @(posedge clk) begin
        assert (c <= 9);
        cover (c == 9);
    end
endmodule

module counter_bad(input clk);
    reg [3:0] c = 0;
    always @(posedge clk) c <= (c == 9) ? 4'd0 : c + 4'd1;
    always @(posedge clk) assert (c < 9);
endmodule

module counter_nocov(input clk);
    reg [3:0] c = 0;
    always @(posedge clk) c <= (c == 9) ? 4'd0 : c + 4'd1;
    always @(posedge clk) begin
        assert (c <= 9);
        cover (c == 12);
    end
endmodule
