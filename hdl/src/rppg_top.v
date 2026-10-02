// Phase 2 fabric block: camera adapter, ROI accumulator, and an APB target
// with a UART transmitter. One instance goes into the reference design's
// TOP SmartDesign (see libero/build.tcl).
//
// APB: shares the MSS FIC_0 master with the LCD's apb3_if. That block
// decodes only PADDR[11:0], so this one claims PADDR[12] and hides those
// cycles from it. Registers, from 0x30001000:
//
//   0x00 SUM_R      R  red sum over the ROI, last complete frame
//   0x04 SUM_G      R
//   0x08 SUM_B      R
//   0x0C COUNT      R  pixels summed
//   0x10 FRAME      R  frame counter
//   0x14 TIMESTAMP  R  microseconds at the end of that frame (free-running)
//   0x18 GEOMETRY   R  [9:0] lines and [26:16] pixels per line, last frame
//   0x1C ROI_X      RW [10:0] x0, [26:16] x1 (x1 exclusive); used from the
//   0x20 ROI_Y      RW [9:0] y0, [25:16] y1         next frame on
//   0x24 UART       W  [7:0] byte to send; R [0] busy, [1] host seen
//
// Host seen: the RX pin (PC -> PIC32 -> FPGA) has carried a start bit since
// reset. The PIC32 relays FPGA bytes only after the PC sends it '&', and a
// byte that arrives before then overruns its UART, which then stops
// receiving for good. So the firmware stays quiet until the PC has sent '&'
// and then any byte, which the PIC32 relays here.
//
// Results update at each VSYNC rise and hold for a whole frame. There is no
// interrupt line: the MSS fabric interrupts and GPIO_0 sit inside the
// System Builder block, which Libero 2026.1 cannot regenerate without an
// older FCCC core. The Cortex-M3 polls FRAME from a timer interrupt instead.
module rppg_top (
    input  wire        clk,
    input  wire        rst_n,

    // Camera pins
    input  wire        cam_pclk_i,
    input  wire        cam_href_i,
    input  wire        cam_vsync_i,
    input  wire [7:0]  cam_data_i,

    // To line_write_read
    output wire        lcd_pclk_o,
    output wire        lcd_href_o,
    output wire        lcd_vsync_o,
    output wire [7:0]  lcd_data_o,

    // APB from the MSS FIC_0 master
    input  wire        psel_i,
    input  wire        penable_i,
    input  wire        pwrite_i,
    input  wire [31:0] paddr_i,
    input  wire [31:0] pwdata_i,
    output reg  [31:0] prdata_o,
    // PSEL for apb3_if; its PREADY and PSLVERR stay wired to the master,
    // since both blocks are always ready and never fail.
    output wire        lcd_psel_o,

    input  wire        uart_rx_i,
    output wire        uart_tx_o
);

    localparam XW = 11, YW = 10;

    // ROI registers; the defaults are a 160 x 120 box in the middle.
    reg [XW-1:0] roi_x0, roi_x1;
    reg [YW-1:0] roi_y0, roi_y1;
    // Copies used for the current frame, so a frame never mixes two ROIs.
    reg [XW-1:0] act_x0, act_x1;
    reg [YW-1:0] act_y0, act_y1;

    wire          frame_tick, pix_valid;
    wire [XW-1:0] pix_x, line_pixels;
    wire [YW-1:0] pix_y, frame_lines;
    wire [7:0]    pix_r, pix_g, pix_b;

    cam_bus #(.XW(XW), .YW(YW)) u_cam (
        .clk(clk), .rst_n(rst_n),
        .pclk_i(cam_pclk_i), .href_i(cam_href_i),
        .vsync_i(cam_vsync_i), .data_i(cam_data_i),
        .pclk_o(lcd_pclk_o), .href_o(lcd_href_o),
        .vsync_o(lcd_vsync_o), .data_o(lcd_data_o),
        .roi_x0(act_x0), .roi_x1(act_x1), .roi_y0(act_y0), .roi_y1(act_y1),
        .frame_tick(frame_tick), .pix_valid(pix_valid),
        .pix_x(pix_x), .pix_y(pix_y),
        .pix_r(pix_r), .pix_g(pix_g), .pix_b(pix_b),
        .frame_lines(frame_lines), .line_pixels(line_pixels)
    );

    wire [31:0] sum_r, sum_g, sum_b, pix_count, frame_count;

    // A VSYNC rise ends one frame and starts the next in the same cycle.
    roi_accumulator #(.CW(8), .XW(XW), .YW(YW)) u_acc (
        .clk(clk), .rst_n(rst_n),
        .frame_start(frame_tick), .frame_end(frame_tick),
        .pix_valid(pix_valid), .pix_x(pix_x), .pix_y(pix_y),
        .pix_r(pix_r), .pix_g(pix_g), .pix_b(pix_b),
        .roi_x0(act_x0), .roi_x1(act_x1), .roi_y0(act_y0), .roi_y1(act_y1),
        .sum_r(sum_r), .sum_g(sum_g), .sum_b(sum_b), .pix_count(pix_count),
        .frame_count(frame_count), .frame_irq()
    );

    // Microsecond counter from the 100 MHz clock. The clock comes from the
    // on-chip RC oscillator, so expect an error of a percent or so.
    reg [6:0]  us_div;
    reg [31:0] us_now, timestamp;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            us_div <= 0; us_now <= 0; timestamp <= 0;
            act_x0 <= 240; act_x1 <= 400; act_y0 <= 180; act_y1 <= 300;
        end else begin
            if (us_div == 99) begin
                us_div <= 0;
                us_now <= us_now + 1'b1;
            end else
                us_div <= us_div + 1'b1;

            if (frame_tick) begin
                timestamp <= us_now;
                act_x0 <= roi_x0; act_x1 <= roi_x1;
                act_y0 <= roi_y0; act_y1 <= roi_y1;
            end
        end
    end

    // APB target
    wire        mine   = paddr_i[12];
    wire        sel    = psel_i & mine;
    wire        wr     = sel & penable_i & pwrite_i;
    wire [3:0]  reg_ix = paddr_i[5:2];
    assign lcd_psel_o  = psel_i & ~mine;

    wire uart_busy;

    // A start bit: RX low for half a bit time, so glitches don't count.
    reg [1:0] rx_s;
    reg [7:0] rx_low;
    reg       host_seen;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rx_s <= 2'b11; rx_low <= 0; host_seen <= 1'b0;
        end else begin
            rx_s <= {rx_s[0], uart_rx_i};
            if (rx_s[1])
                rx_low <= 0;
            else if (rx_low != 8'hFF)
                rx_low <= rx_low + 1'b1;
            if (rx_low == 8'd217)       // 100 MHz / 230400 / 2
                host_seen <= 1'b1;
        end
    end
    uart_tx u_uart (
        .clk(clk), .rst_n(rst_n),
        .start(wr && reg_ix == 4'h9), .data(pwdata_i[7:0]),
        .busy(uart_busy), .tx(uart_tx_o)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            roi_x0 <= 240; roi_x1 <= 400; roi_y0 <= 180; roi_y1 <= 300;
        end else if (wr) begin
            case (reg_ix)
                4'h7: begin roi_x0 <= pwdata_i[XW-1:0]; roi_x1 <= pwdata_i[16+XW-1:16]; end
                4'h8: begin roi_y0 <= pwdata_i[YW-1:0]; roi_y1 <= pwdata_i[16+YW-1:16]; end
                default: ;
            endcase
        end
    end

    always @(*) begin
        prdata_o = 32'h0;
        if (sel) begin
            case (reg_ix)
                4'h0: prdata_o = sum_r;
                4'h1: prdata_o = sum_g;
                4'h2: prdata_o = sum_b;
                4'h3: prdata_o = pix_count;
                4'h4: prdata_o = frame_count;
                4'h5: prdata_o = timestamp;
                4'h6: prdata_o = {5'b0, line_pixels, 6'b0, frame_lines};
                4'h7: prdata_o = {5'b0, roi_x1, 5'b0, roi_x0};
                4'h8: prdata_o = {6'b0, roi_y1, 6'b0, roi_y0};
                4'h9: prdata_o = {30'b0, host_seen, uart_busy};
                default: ;
            endcase
        end
    end

endmodule
