// Testbench for rppg_top: a small camera frame through the whole block.
// Run with:
//   iverilog -o tb hdl/sim/tb_rppg_top.v hdl/src/rppg_top.v hdl/src/cam_bus.v \
//     hdl/src/roi_accumulator.v hdl/src/uart_tx.v && vvp tb
//
// The camera model changes HREF and DATA on PCLK's falling edge, like the
// OV7725, with PCLK at 24 MHz against a 100 MHz system clock. A model of
// WRITE_LSRAM's sampling checks what the LCD path sees.
`timescale 1ns/1ps
module tb_rppg_top;
    localparam W = 24, H = 12;                 // frame size in pixels
    localparam X0 = 8, X1 = 14, Y0 = 4, Y1 = 8; // ROI
    localparam B = 4;                          // border width in cam_bus

    reg clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    reg pclk = 0, href = 0, vsync = 0, rx = 1;
    reg [7:0] data = 0;
    always #20.833 pclk = ~pclk;

    reg psel = 0, penable = 0, pwrite = 0;
    reg [31:0] paddr = 0, pwdata = 0;
    wire [31:0] prdata;
    wire lcd_pclk, lcd_href, lcd_vsync, lcd_psel, tx;
    wire [7:0] lcd_data;

    rppg_top dut (
        .clk(clk), .rst_n(rst_n),
        .cam_pclk_i(pclk), .cam_href_i(href), .cam_vsync_i(vsync), .cam_data_i(data),
        .lcd_pclk_o(lcd_pclk), .lcd_href_o(lcd_href), .lcd_vsync_o(lcd_vsync),
        .lcd_data_o(lcd_data),
        .psel_i(psel), .penable_i(penable), .pwrite_i(pwrite),
        .paddr_i(paddr), .pwdata_i(pwdata), .prdata_o(prdata), .lcd_psel_o(lcd_psel),
        .uart_rx_i(rx), .uart_tx_o(tx)
    );

    // Pixel (x, y) is R = x, G = y, B = x + y, in RGB565 fields.
    function [15:0] pixel(input integer x, input integer y);
        pixel = {x[4:0], y[5:0], x[4:0] + y[4:0]};
    endfunction

    integer errors = 0;
    task check(input cond, input [8*48-1:0] what);
        if (!cond) begin
            $display("FAIL: %0s", what);
            errors = errors + 1;
        end
    endtask

    // APB transfers, as the MSS issues them.
    task apb_write(input [31:0] a, input [31:0] d);
        begin
            @(posedge clk) begin psel <= 1; paddr <= a; pwdata <= d; pwrite <= 1; end
            @(posedge clk) penable <= 1;
            @(posedge clk) begin psel <= 0; penable <= 0; pwrite <= 0; end
        end
    endtask
    reg [31:0] rd;
    task apb_read(input [31:0] a);
        begin
            @(posedge clk) begin psel <= 1; paddr <= a; pwrite <= 0; end
            @(posedge clk) penable <= 1;
            @(posedge clk) begin rd = prdata; psel <= 0; penable <= 0; end
        end
    endtask

    // One camera frame: VSYNC for 3 lines' time, then H lines of W pixels.
    task send_frame;
        integer x, y;
        reg [15:0] p;
        begin
            @(negedge pclk) vsync <= 1;
            repeat (3 * 2 * W) @(negedge pclk);
            vsync <= 0;
            repeat (20) @(negedge pclk);
            for (y = 0; y < H; y = y + 1) begin
                for (x = 0; x < W; x = x + 1) begin
                    p = pixel(x, y);
                    @(negedge pclk) begin href <= 1; data <= p[15:8]; end
                    @(negedge pclk) data <= p[7:0];
                end
                @(negedge pclk) begin href <= 0; data <= 8'hxx; end
                repeat (10) @(negedge pclk);
            end
        end
    endtask

    // Model of the LCD path: two input flops, then WRITE_LSRAM's edge detect.
    reg [1:0] l_pclk, l_href, l_vsync;
    reg [7:0] l_data1, l_data2;
    reg       l_dly, l_dly1;
    integer   l_byte, l_line;
    reg       l_href_d;
    reg [7:0] seen [0:H-1][0:2*W-1];
    always @(posedge clk) begin
        l_pclk  <= {l_pclk[0], lcd_pclk};
        l_href  <= {l_href[0], lcd_href};
        l_vsync <= {l_vsync[0], lcd_vsync};
        l_data1 <= lcd_data; l_data2 <= l_data1;
        l_dly <= l_pclk[1]; l_dly1 <= l_dly;
        l_href_d <= l_href[1];
        if (l_vsync[1]) begin
            l_line = 0; l_byte = 0;
        end else begin
            if (!l_href[1]) l_byte = 0;
            else if (l_dly && !l_dly1) begin
                if (l_line < H && l_byte < 2 * W) seen[l_line][l_byte] = l_data2;
                l_byte = l_byte + 1;
            end
            if (l_href_d && !l_href[1]) l_line = l_line + 1;
        end
    end

    // UART receiver for one byte at 230400 baud.
    reg [7:0] rx_byte;
    task uart_receive;
        integer i;
        begin
            @(negedge tx);
            #(4340 * 1.5);
            for (i = 0; i < 8; i = i + 1) begin
                rx_byte[i] = tx;
                #4340;
            end
            check(tx === 1'b1, "UART stop bit");
        end
    endtask

    integer x, y, exp_r, exp_g, exp_b, exp_n;
    reg [15:0] p, got;
    reg in_roi, in_box;

    initial begin
        #100 rst_n = 1;

        // Defaults, then the test ROI.
        apb_read(32'h3000101C);
        check(rd == {16'd400, 16'd240}, "default ROI_X");
        apb_write(32'h3000101C, (X1 << 16) | X0);
        apb_write(32'h30001020, (Y1 << 16) | Y0);

        // PSEL reaches apb3_if only below 0x1000.
        @(posedge clk) begin psel <= 1; paddr <= 32'h3000070C; end
        @(posedge clk) check(lcd_psel === 1'b1, "apb3_if selected at 0x70C");
        @(posedge clk) begin paddr <= 32'h30001000; end
        @(posedge clk) check(lcd_psel === 1'b0, "apb3_if not selected at 0x1000");
        psel <= 0;

        send_frame;   // the ROI takes effect at this frame's VSYNC
        send_frame;   // the second VSYNC latches the first frame's sums
        @(negedge pclk) vsync <= 1;
        repeat (10) @(posedge clk);

        exp_r = 0; exp_g = 0; exp_b = 0; exp_n = 0;
        for (y = Y0; y < Y1; y = y + 1)
            for (x = X0; x < X1; x = x + 1) begin
                p = pixel(x, y);
                exp_r = exp_r + {p[15:11], 3'b0};
                exp_g = exp_g + {p[10:5], 2'b0};
                exp_b = exp_b + {p[4:0], 3'b0};
                exp_n = exp_n + 1;
            end
        apb_read(32'h30001000); check(rd == exp_r, "SUM_R");
        apb_read(32'h30001004); check(rd == exp_g, "SUM_G");
        apb_read(32'h30001008); check(rd == exp_b, "SUM_B");
        apb_read(32'h3000100C); check(rd == exp_n, "COUNT");
        apb_read(32'h30001010); check(rd == 3, "FRAME");
        apb_read(32'h30001018); check(rd == ((W << 16) | H), "GEOMETRY");
        apb_read(32'h30001014); check(rd > 0, "TIMESTAMP");

        // The LCD path sees the image, with a green border around the ROI.
        for (y = 0; y < H; y = y + 1)
            for (x = 0; x < W; x = x + 1) begin
                in_roi = x >= X0 && x < X1 && y >= Y0 && y < Y1;
                in_box = x >= X0 - B && x < X1 + B && y >= Y0 - B && y < Y1 + B;
                p = (in_box && !in_roi) ? 16'h07E0 : pixel(x, y);
                got = {seen[y][2 * x], seen[y][2 * x + 1]};
                if (got !== p) begin
                    $display("FAIL: LCD pixel (%0d,%0d) = %h, expected %h", x, y, got, p);
                    errors = errors + 1;
                end
            end

        // Host detection: a 100 ns glitch doesn't count, a start bit does.
        apb_read(32'h30001024); check(rd == 0, "no host after reset");
        rx = 0; #100 rx = 1; #3000;
        apb_read(32'h30001024); check(rd == 0, "RX glitch ignored");
        rx = 0; #4340 rx = 1; #100;
        apb_read(32'h30001024); check(rd == 2, "host seen after a start bit");

        // UART
        fork
            apb_write(32'h30001024, 32'hA5);
            uart_receive;
        join
        check(rx_byte == 8'hA5, "UART byte");
        #3000;
        apb_read(32'h30001024); check(rd == 2, "UART idle after the byte");

        if (errors == 0) $display("PASS");
        else $display("%0d errors", errors);
        $finish;
    end
endmodule
