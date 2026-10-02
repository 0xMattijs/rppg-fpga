/*
 * ov7725.c
 *
 *  Created on: 06-Jun-2019
 *      Author: I30392
 */
#include "hal.h"
#include "Hello_system.h"
#include "drivers/mss_i2c/mss_i2c.h"
#include "OV7725.h"

uint8_t rx_buff[64],tx_buff[64];

void OV7725_init()
{
	MSS_I2C_init( &g_mss_i2c0, 0x21, MSS_I2C_PCLK_DIV_256 );// Initialize MSS_I2C
	Reset();                                 // Resets all registers to default values


	// Reset all registers
	WriteReg(0x12, 0x10);

	WriteReg(0x00, 0x00);	// AGC Gain control		Default 00
	WriteReg(0x01, 0x80);	// Blue Gain setting	Default 80
	WriteReg(0x02, 0x80);	// Red Gain setting		Default 80
	WriteReg(0x03, 0x80);	// Green Gain setting	Default 80
	/*0x04 is Reserved*/
	WriteReg(0x05, 0x00);	// U/B Average level	Default 00
	WriteReg(0x06, 0x00);	// Y/Gb Average level	Default 00
	WriteReg(0x07, 0x00);	// V/R Average level	Default 00
	WriteReg(0x08, 0x00);	// Exposure values AEC-MSB	Default 00
	WriteReg(0x10, 0x40);	// Exposure values AEC-LSB	Default 40
	WriteReg(0x09, 0x01);	// Output drive capability	Default 01
	/*0x0A 0x0B is device ID*/
	WriteReg(0x0C, 0x90);	// V,H flip, MSB LSB swap, Tri-state	Default 10
	WriteReg(0x0D, 0x00);	// PLL frequency and AEC window			Default 41
	WriteReg(0x0E, 0x01);	// Frame rate control	Default 01
	WriteReg(0x0F, 0x43);	// Auto window setting on/off	Default 43
	WriteReg(0x11, 0x80);	// Internal Clock	Default 80
	WriteReg(0x12, 0x06);	// Output format selection 	Default 00
	WriteReg(0x13, 0x0F);	// Camera Auto control 	Default 8F
	WriteReg(0x14, 0x4A);	// Max AGC ceiling	Default 4A
	WriteReg(0x15, 0x00);	// Polarity and edge change of control signals	Default 00
	WriteReg(0x16, 0x00);	// Bit shift test pattern options 	Default 00
	WriteReg(0x17, 0x23);	// Horizontal frame start 	Default - 23(VGA) 3F(QVGA)
	WriteReg(0x18, 0xA3);	// Horizontal sensor size 	Default - A0(VGA) 50(QVGA)
	WriteReg(0x19, 0x07);	// Vertical frame start 	Default - 07(VGA) 03(QVGA)
	WriteReg(0x1A, 0xF0);	// Vertical sensor size 	Default - F0(VGA) 78(QVGA)
	WriteReg(0x1B, 0x40);	// Pixel Delay select 		Default - 40
	/*0x1C, 0x1D, 0x1E are reserved*/
	WriteReg(0x1F, 0x00);	// Fine AEC value 	Default - 00
	WriteReg(0x20, 0x10);	// Single frame control 	Default - 10
	/*0x21 is reserved*/
	WriteReg(0x22, 0xFF);	// Banding filter max AEC	Default - FF
	WriteReg(0x23, 0x01);	// Banding filter max step	Default - 01
	WriteReg(0x24, 0x40);	// AGC/AEC stable operating region Upper limit	Default - 75
	WriteReg(0x25, 0x10);	// AGC/AEC stable operating region Lower limit	Default - 63
	WriteReg(0x26, 0xD4);	// AGC/AEC Fast mode operating region Default - D4
	/*0x27 is reserved*/
	WriteReg(0x28, 0x00);	// Register28 Default - 00
	WriteReg(0x29, 0xA0);	// HOUT size Default - A0 VGA 50 QVGA
	WriteReg(0x2A, 0x00);	// Dummy pixel insert MSB Default - 00
	WriteReg(0x2B, 0x00);	// Dummy pixel insert LSB Default - 00
	WriteReg(0x2C, 0xF0);	// VOUT size Default - F0 VGA 78 QVGA
	WriteReg(0x2D, 0x00);	// Dummy row insert MSB Default - 00
	WriteReg(0x2E, 0x00);	// Dummy row insert LSB Default - 00
	WriteReg(0x2F, 0x00);	// Y/G channel average value Default - 00

	WriteReg(0x30, 0x80);	// Histogram AEC/AGC higher threshold  Default - 80
	WriteReg(0x31, 0x60);	// Histogram AEC/AGC higher threshold  Default - 60
	WriteReg(0x32, 0x00);	// Image start and size control  Default - 00
	WriteReg(0x33, 0x00);	// Dummy Row low 8 bits  Default - 00
	WriteReg(0x34, 0x00);	// Dummy Row high 8 bits  Default - 00
	WriteReg(0x35, 0x80);	// ADC offset compensation for B channel  Default - 80
	WriteReg(0x36, 0x80);	// ADC offset compensation for R channel  Default - 80
	WriteReg(0x37, 0x80);	// ADC offset compensation for Gb channel  Default - 80
	WriteReg(0x38, 0x80);	// ADC offset compensation for Gr channel  Default - 80
	WriteReg(0x39, 0x80);	// Analog process B channel offset compensation value  Default - 80
	WriteReg(0x3A, 0x80);	// Analog process R channel offset compensation value  Default - 80
	WriteReg(0x3B, 0x80);	// Analog process Gb channel offset compensation value  Default - 80
	WriteReg(0x3C, 0x80);	// Analog process Gr channel offset compensation value  Default - 80
	WriteReg(0x3D, 0x80);	// Common control 12  Default - 80
	WriteReg(0x3E, 0xE2);	// Common control 13  Default - E2
	WriteReg(0x3F, 0x1F);	// Common control 14  Default - 1F
//	WriteReg(0x40, 0xC0);	// Common control 15  Default - C0
	WriteReg(0x41, 0x08);	// Common control 16  Default - 08
	WriteReg(0x42, 0x80);	// BLC B channel target value  Default - 80
	WriteReg(0x43, 0x80);	// BLC R channel target value  Default - 80
	WriteReg(0x44, 0x80);	// BLC Gb channel target value  Default - 80
	WriteReg(0x45, 0x80);	// BLC Gr channel target value  Default - 80
	/*0x46 to 0x4C lens correction control*/
	WriteReg(0x4D, 0x00);	// Analog fix gain amplifier  Default - 00
	WriteReg(0x4E, 0xEF);	// Sensor reference control  Default - EF
	WriteReg(0x4F, 0x10);	// Sensor reference current control  Default - 10

	WriteReg(0x50, 0x60);	// Analog reference control  Default - 60
	WriteReg(0x51, 0x00);	// ADC reference control  Default - 00
	WriteReg(0x52, 0x00);	// ADC reference control  Default - 00
	WriteReg(0x53, 0x00);	// ADC reference control  Default - 00
	WriteReg(0x54, 0x7A);	// Analog reference control  Default - 7A
	WriteReg(0x55, 0xFC);	// Analog reference control  Default - FC
	/* 0x56 to 0x5F are reserved*/

	WriteReg(0x60, 0x80);	// U channel fixed value output  Default - 80
	WriteReg(0x61, 0x80);	// V channel fixed value output  Default - 80
	WriteReg(0x62, 0xFF);	// AWB option for advanced AWB  Default - FF
	WriteReg(0x63, 0xF0);	// AWB control byte 0  Default - F0
	WriteReg(0x64, 0x1F);	// DSP control Byte1 	Default - 1F
	WriteReg(0x65, 0x00);	// DSP control Byte2 	Default - 00
	WriteReg(0x66, 0x10);	// DSP control Byte3 	Default - 10
	WriteReg(0x67, 0x00);	// DSP control Byte4 	Default - 00
	WriteReg(0x68, 0x00);	// AWB BLC level chip 	Default - 00
	WriteReg(0x69, 0x5C);	// AWB control1 		Default - 5C


	WriteReg(0x7B, 0xF0);	// AWB R gain range 	Default - F0
	WriteReg(0x7C, 0xF0);	// AWB G gain range 	Default - F0
	WriteReg(0x7D, 0xF0);	// AWB B gain range 	Default - F0

	/*Gamma correction*/
//    WriteReg(0x7E, 0x1c);
//    WriteReg(0x7F, 0x28);
//    WriteReg(0x80, 0x3c);
//    WriteReg(0x81, 0x5a);
//    WriteReg(0x82, 0x68);
//    WriteReg(0x83, 0x76);
//    WriteReg(0x84, 0x80);
//    WriteReg(0x85, 0x88);
//    WriteReg(0x86, 0x8f);
//    WriteReg(0x87, 0x96);
//    WriteReg(0x88, 0xa3);
//    WriteReg(0x89, 0xaf);
//    WriteReg(0x8A, 0xc4);
//    WriteReg(0x8B, 0xd7);
//    WriteReg(0x8C, 0xe8);
//    WriteReg(0x8D, 0x20);

    WriteReg(0x8E, 0x00);	// Denoise threshold 	Default - 00
    WriteReg(0x8F, 0x00);	// Sharpness control0 	Default - 00
    WriteReg(0x90, 0x08);	// Sharpness control1 	Default - 08
    WriteReg(0x91, 0x10);	// Auto denoise threshold control 	Default - 10
    WriteReg(0x92, 0x02);	// Sharpness strength upper limit 	Default - 1F
    WriteReg(0x93, 0x01);	// Sharpness strength lower limit 	Default - 01

    WriteReg(0x94, 0x2C);	// Matrix coefficient1 	Default - 2C
    WriteReg(0x95, 0x24);	// Matrix coefficient2 	Default - 24
    WriteReg(0x96, 0x08);	// Matrix coefficient3 	Default - 08
    WriteReg(0x97, 0x14);	// Matrix coefficient4 	Default - 14
    WriteReg(0x98, 0x24);	// Matrix coefficient5 	Default - 24
    WriteReg(0x99, 0x38);	// Matrix coefficient6 	Default - 38
	WriteReg(0x9A, 0x9E);	// Matrix control 	Default - 9E
	WriteReg(0x9B, 0x00);	// Brightness control 	Default - 00
	WriteReg(0x9C, 0x80);	// Contrast control		Default - 40
	/* 0x9D is reserved*/
	WriteReg(0x9E, 0x11);	// Auto UV adjust control0 Default - 11
	WriteReg(0x9F, 0x02);	// Auto UV adjust control1 	Default - 02
	WriteReg(0xA0, 0x00);	// DCW Ratio control Default - 00
	WriteReg(0xA1, 0x40);	// Horizontal zoom out 	Default - 40
	WriteReg(0xA2, 0x40);	// Vertical zoom out	Default - 40
	WriteReg(0xA3, 0x06);	// FIFO manual mode delay control Default - 06
	WriteReg(0xA4, 0x00);	// FIFO Auto mode delay control Default - 00
	/* 0xA5 is reserved*/
	WriteReg(0xA6, 0x04);	// Special Digital Effect 	Default - 00
	WriteReg(0xA7, 0x40);	// U component saturation gain 	Default - 40
	WriteReg(0xA8, 0x40);	// V component saturation gain 	Default - 40
	WriteReg(0xA9, 0xF0);	// Hue COS	Default - 80
	WriteReg(0xAA, 0xF0);	// Hue SIN	Default - 80
	WriteReg(0xAB, 0x06);	// Sign bit for Hue and brightness	Default - 06
	WriteReg(0xAC, 0xFF);	// DSP auto function ON/OFF			Default - FF


    }


void WriteReg(uint8_t addr, uint8_t data)
{
	uint16_t a,b,i,x;
	tx_buff[0] = addr;
	tx_buff[1] = data;
	 MSS_I2C_write( &g_mss_i2c0, 0x21, &tx_buff[0], 2,
						   MSS_I2C_RELEASE_BUS );
	for(a = 0; a < 1500; a++)
		for(b= 0; b< 10; b++);
}
uint8_t ReadReg(uint8_t addr)
{
	uint8_t rx_buff[64];

	MSS_I2C_read( &g_mss_i2c0, 0x21, &rx_buff[0], 1, MSS_I2C_RELEASE_BUS );
	delay_us(65500);
	return rx_buff[0];
}
void delay_us(uint64_t x)
{
	for(uint64_t j; j<x; j++)
	{
		for(int i =0; i<100; i++)
		{
			asm("NOP\n");
		}
	}
}
void Reset()
{
	    WriteReg(0x12, 0x80);                  // RESET CAMERA
	    delay_us(65500);
}
