"""TAS2780 register addresses and bit masks."""


class TAS2780_REGS:
    """Register addresses and bit masks for TAS2780."""

    PAGE_SELECT = 0x0
    # PAGE 0
    SW_RESET = 0x01  # Software Reset
    MODE_CTRL = 0x02  # Device operational mode
    MODE_CTRL_BOP_SRC__PVDD_UVLO = 0x80
    MODE_CTRL_MODE_MASK = 0x07
    MODE_CTRL_MODE__ACTIVE = 0x00
    MODE_CTRL_MODE__ACTIVE_MUTED = 0x01
    MODE_CTRL_MODE__SFTW_SHTDWN = 0x02

    CHNL_0 = 0x03  # Y Bridge and Channel settings
    CHNL_0_CDS_MODE_SHIFT = 6
    CHNL_0_CDS_MODE_MASK = 0x03 << CHNL_0_CDS_MODE_SHIFT
    CHNL_0_AMP_LEVEL_SHIFT = 1
    CHNL_0_AMP_LEVEL_MASK = 0x1F << CHNL_0_AMP_LEVEL_SHIFT

    DC_BLK0 = 0x04  # SAR Filter and DC Path Blocker
    DC_BLK0_VBAT1S_MODE_SHIFT = 7
    DC_BLK1 = 0x05  # Record DC Blocker
    MISC_CFG1 = 0x06  # Misc Configuration 1
    MISC_CFG2 = 0x07  # Misc Configuration 2
    TDM_CFG0 = 0x08  # TDM Configuration 0
    TDM_CFG1 = 0x09  # TDM Configuration 1

    TDM_CFG2 = 0x0A  # TDM Configuration 2
    TDM_CFG2_RX_SCFG_SHIFT = 4
    TDM_CFG2_RX_SCFG_MASK = 3 << TDM_CFG2_RX_SCFG_SHIFT
    TDM_CFG2_RX_SCFG__STEREO_DWN_MIX = 3 << TDM_CFG2_RX_SCFG_SHIFT
    TDM_CFG2_RX_SCFG__MONO_LEFT = 1 << TDM_CFG2_RX_SCFG_SHIFT
    TDM_CFG2_RX_SCFG__MONO_RIGHT = 2 << TDM_CFG2_RX_SCFG_SHIFT
    TDM_CFG2_RX_WLEN_SHIFT = 2
    TDM_CFG2_RX_WLEN_MASK = 3 << TDM_CFG2_RX_WLEN_SHIFT
    TDM_CFG2_RX_WLEN__16BIT = 0 << TDM_CFG2_RX_WLEN_SHIFT
    TDM_CFG2_RX_WLEN__24BIT = 2 << TDM_CFG2_RX_WLEN_SHIFT
    TDM_CFG2_RX_WLEN__32BIT = 3 << TDM_CFG2_RX_WLEN_SHIFT
    TDM_CFG2_RX_SLEN_MASK = 3 << 0
    TDM_CFG2_RX_SLEN__32BIT = 2

    LIM_MAX_ATTN = 0x0B  # Limiter
    TDM_CFG3 = 0x0C  # TDM Configuration 3
    TDM_CFG4 = 0x0D  # TDM Configuration 4
    TDM_CFG5 = 0x0E  # TDM Configuration 5
    TDM_CFG6 = 0x0F  # TDM Configuration 6
    TDM_CFG7 = 0x10  # TDM Configuration 7
    TDM_CFG8 = 0x11  # TDM Configuration 8
    TDM_CFG9 = 0x12  # TDM Configuration 9
    TDM_CFG10 = 0x13  # TDM Configuration 10
    TDM_CFG11 = 0x14  # TDM Configuration 11
    ICC_CNFG2 = 0x15  # ICC Mode
    TDM_CFG12 = 0x16  # TDM Configuration 12
    ICLA_CFG0 = 0x17  # Inter Chip Limiter Alignment 0
    ICLA_CFG1 = 0x18  # Inter Chip Gain Alignment 1
    DG_0 = 0x19  # Diagnostic Signal

    DVC = 0x1A  # Digital Volume Control
    LIM_CFG0 = 0x1B  # Limiter Configuration 0
    LIM_CFG1 = 0x1C  # Limiter Configuration 1
    BOP_CFG0 = 0x1D  # Brown Out Prevention 0
    BOP_CFG1 = 0x1E  # Brown Out Prevention 1
    BOP_CFG2 = 0x1F  # Brown Out Prevention 2
    BOP_CFG3 = 0x20  # Brown Out Prevention 3
    BOP_CFG4 = 0x21  # Brown Out Prevention 4
    BOP_CFG5 = 0x22  # BOP Configuration 5
    BOP_CFG6 = 0x23  # Brown Out Prevention 6
    BOP_CFG7 = 0x24  # Brown Out Prevention 7
    BOP_CFG8 = 0x25  # Brown Out Prevention 8
    BOP_CFG9 = 0x26  # Brown Out Prevention 9
    BOP_CFG10 = 0x27  # BOP Configuration 10
    BOP_CFG11 = 0x28  # Brown Out Prevention 11
    BOP_CFG12 = 0x29  # Brown Out Prevention 12
    BOP_CFG13 = 0x2A  # Brown Out Prevention 13
    BOP_CFG14 = 0x2B  # Brown Out Prevention 14
    BOP_CFG15 = 0x2C  # BOP Configuration 15
    BOP_CFG17 = 0x2D  # Brown Out Prevention 17
    BOP_CFG18 = 0x2E  # Brown Out Prevention 18
    BOP_CFG19 = 0x2F  # Brown Out Prevention 19
    BOP_CFG20 = 0x30  # Brown Out Prevention 20
    BOP_CFG21 = 0x31  # BOP Configuration 21
    BOP_CFG22 = 0x32  # Brown Out Prevention 22
    BOP_CFG23 = 0x33  # Lowest PVDD Measured
    BOP_CFG24 = 0x34  # Lowest BOP Attack Rate
    NG_CFG0 = 0x35  # Noise Gate 0
    NG_CFG1 = 0x36  # Noise Gate 1
    LVS_CFG0 = 0x37  # Low Voltage Signaling
    DIN_PD = 0x38  # Digital Input Pin Pull Down

    # Interrupts
    INT_MASK0 = 0x3B  # Interrupt Mask 0
    INT_MASK1 = 0x3C  # Interrupt Mask 1
    INT_MASK4 = 0x3D  # Interrupt Mask 4
    INT_MASK2 = 0x40  # Interrupt Mask 2
    INT_MASK3 = 0x41  # Interrupt Mask 3
    INT_LIVE0 = 0x42  # Live Interrupt Read-back 0
    INT_LIVE1 = 0x43  # Live Interrupt Read-back 1
    INT_LIVE1_0 = 0x44  # Live Interrupt Read-back 1_0
    INT_LIVE2 = 0x47  # Live Interrupt Read-back 2
    INT_LIVE3 = 0x48  # Live Interrupt Read-back 3
    INT_LTCH0 = 0x49  # Latched Interrupt Read-back 0
    INT_LTCH1 = 0x4A  # Latched Interrupt Read-back 1
    INT_LTCH1_0 = 0x4B  # Latched Interrupt Read-back 1_0
    INT_LTCH2 = 0x4F  # Latched Interrupt Read-back 2
    INT_LTCH3 = 0x50  # Latched Interrupt Read-back 3
    INT_LTCH4 = 0x51  # Latched Interrupt Read-back 4

    VBAT_MSB = 0x52  # SAR VBAT1S 0
    VBAT_LSB = 0x53  # SAR VBAT1S 1
    PVDD_MSB = 0x54  # SAR PVDD 0
    PVDD_LSB = 0x55  # SAR PVDD 1
    TEMP = 0x56  # SAR ADC Conversion 2
    INT_CLK_CFG = 0x5C  # Clock Setting and IRQZ
    MISC_CFG3 = 0x5D  # Misc Configuration 3
    CLOCK_CFG = 0x60  # Clock Configuration
    IDLE_IND = 0x63  # Idle channel current optimization
    SAR_SAMP = 0x64  # SAR Sampling Time
    MISC_CFG4 = 0x65  # Misc Configuration 4
    TG_CFG0 = 0x67  # Tone Generator
    CLK_CFG = 0x68  # Detect Clock Ratio and Sample Rate
    LV_EN_CFG = 0x6A  # Class-D and LVS Delays
    NG_CFG2 = 0x6B  # Noise Gate 2
    NG_CFG3 = 0x6C  # Noise Gate 3
    NG_CFG4 = 0x6D  # Noise Gate 4
    NG_CFG5 = 0x6E  # Noise Gate 5
    NG_CFG6 = 0x6F  # Noise Gate 6
    NG_CFG7 = 0x70  # Noise Gate 7
    PVDD_UVLO = 0x71  # UVLO Threshold
    DMD = 0x73  # DAC Modulator Dither
    I2C_CKSUM = 0x7E  # I2C Checksum
    BOOK = 0x7F  # Device Book

    # PAGE 0x01
    INIT_0 = 0x17  # Initialization
    LSR = 0x19  # Modulation
    INIT_1 = 0x21  # Initialization
    INIT_2 = 0x35  # Initialization
    INT_LDO = 0x36  # Internal LDO Setting
    SDOUT_HIZ_1 = 0x3D  # Slots Control
    SDOUT_HIZ_2 = 0x3E  # Slots Control
    SDOUT_HIZ_3 = 0x3F  # Slots Control
    SDOUT_HIZ_4 = 0x40  # Slots Control
    SDOUT_HIZ_5 = 0x41  # Slots Control
    SDOUT_HIZ_6 = 0x42  # Slots Control
    SDOUT_HIZ_7 = 0x43  # Slots Control
    SDOUT_HIZ_8 = 0x44  # Slots Control
    SDOUT_HIZ_9 = 0x45  # Slots Control
    TG_EN = 0x47  # Thermal Detection Enable
    EDGE_CTRL = 0x4C  # Slew rate control

    # PAGE 0x04
    DG_DC_VAL1 = 0x08  # Diagnostic DC Level
    DG_DC_VAL2 = 0x09  # Diagnostic DC Level
    DG_DC_VAL3 = 0x0A  # Diagnostic DC Level
    DG_DC_VAL4 = 0x0B  # Diagnostic DC Level
    LIM_TH_MAX1 = 0x0C  # Limiter Maximum Threshold
    LIM_TH_MAX2 = 0x0D  # Limiter Maximum Threshold
    LIM_TH_MAX3 = 0x0E  # Limiter Maximum Threshold
    LIM_TH_MAX4 = 0x0F  # Limiter Maximum Threshold
    LIM_TH_MIN1 = 0x10  # Limiter Minimum Threshold
    LIM_TH_MIN2 = 0x11  # Limiter Minimum Threshold
    LIM_TH_MIN3 = 0x12  # Limiter Minimum Threshold
    LIM_TH_MIN4 = 0x13  # Limiter Minimum Threshold
    LIM_INF_PT1 = 0x14  # Limiter Inflection Point
    LIM_INF_PT2 = 0x15  # Limiter Inflection Point
    LIM_INF_PT3 = 0x16  # Limiter Inflection Point
    LIM_INF_PT4 = 0x17  # Limiter Inflection Point
    LIM_SLOPE1 = 0x18  # Limiter Slope
    LIM_SLOPE2 = 0x19  # Limiter Slope
    LIM_SLOPE3 = 0x1A  # Limiter Slope
    LIM_SLOPE4 = 0x1B  # Limiter Slope
    TF_HLD1 = 0x1C  # TFB Maximum Hold
    TF_HLD2 = 0x1D  # TFB Maximum Hold
    TF_HLD3 = 0x1E  # TFB Maximum Hold
    TF_HLD4 = 0x1F  # TFB Maximum Hold
    TF_RLS1 = 0x20  # TFB Release Rate
    TF_RLS2 = 0x21  # TFB Release Rate
    TF_RLS3 = 0x22  # TFB Release Rate
    TF_RLS4 = 0x23  # TFB Release Rate
    TF_SLOPE1 = 0x24  # TFB Limiter Slope
    TF_SLOPE2 = 0x25  # TFB Limiter Slope
    TF_SLOPE3 = 0x26  # TFB Limiter Slope
    TF_SLOPE4 = 0x27  # TFB Limiter Slope
    TF_TEMP_TH1 = 0x28  # TFB Threshold
    TF_TEMP_TH2 = 0x29  # TFB Threshold
    TF_TEMP_TH3 = 0x2A  # TFB Threshold
    TF_TEMP_TH4 = 0x2B  # TFB Threshold
    TF_MAX_ATTN1 = 0x2C  # TFB Gain Reduction
    TF_MAX_ATTN2 = 0x2D  # TFB Gain Reduction
    TF_MAX_ATTN3 = 0x2E  # TFB Gain Reduction
    TF_MAX_ATTN4 = 0x2F  # TFB Gain Reduction
    LD_CFG0 = 0x40  # Load Diagnostics Resistance Upper Threshold
    LD_CFG1 = 0x41  # Load Diagnostics Resistance Upper Threshold
    LD_CFG2 = 0x42  # Load Diagnostics Resistance Upper Threshold
    LD_CFG3 = 0x43  # Load Diagnostics Resistance Upper Threshold
    LD_CFG4 = 0x44  # Load Diagnostics Resistance Lower Threshold
    LD_CFG5 = 0x45  # Load Diagnostics Resistance Lower Threshold
    LD_CFG6 = 0x46  # Load Diagnostics Resistance Lower Threshold
    LD_CFG7 = 0x47  # Load Diagnostics Resistance Lower Threshold
    CLD_EFF_1 = 0x48  # Class D Efficiency
    CLD_EFF_2 = 0x49  # Class D Efficiency
    CLD_EFF_3 = 0x4A  # Class D Efficiency
    CLD_EFF_4 = 0x4B  # Class D Efficiency
    LDG_RES1 = 0x4C  # Load Diagnostics Resistance Value
    LDG_RES2 = 0x4D  # Load Diagnostics Resistance Value
    LDG_RES3 = 0x4E  # Load Diagnostics Resistance Value
    LDG_RES4 = 0x4F  # Load Diagnostics Resistance Value

    # PAGE 0xFD
    INIT_3 = 0x3E  # Initialization

    INT_LTCH0_IR_OT = 1 << 0  # over temp error
    INT_LTCH0_IR_OC = 1 << 1  # over current error
    INT_LTCH0_IR_TDMCE = 1 << 2  # TDM_CLOCK_ERROR
    INT_LTCH0_IR_LIMA = 1 << 3  # limiter active
    INT_LTCH0_IR_PBIP = 1 << 4  # PVDD below limiter inflection point
    INT_LTCH0_IR_LIMMA = 1 << 5  # limiter max attenuation
    INT_LTCH0_IR_BOPIH = 1 << 6  # BOP infinite hold
    INT_LTCH0_IR_BOPM = 1 << 7  # due to BOP mute

    INT_LTCH1_IR_VBATLIM = 1 << 0  # Gain Limiter interrupt
    INT_LTCH1_IR_LDMODE = 3 << 3  # Load Diagnostic mode fault status
    INT_LTCH1_IR_LDC = 1 << 5  # Load diagnostic completion
    INT_LTCH1_IR_OTPCRC = 1 << 6  # OTP CRC error flag

    INT_LTCH1_0_IR_VBAT1S_UVLO = 1 << 5  # VBAT1S Under Voltage
    INT_LTCH1_0_IR_PLL_CLK = 1 << 7  # Internal PLL Clock Error

    INT_LTCH2_IR_PUVLO = 1 << 0  # PVDD UVLO
    INT_LTCH2_IR_LDO_OL = 1 << 1  # Internal VBAT1S LDO Over Load
    INT_LTCH2_IR_LDO_OV = 1 << 2  # Internal VBAT1S LDO Over Voltage
    INT_LTCH2_IR_LDO_UV = 1 << 3  # Internal VBAT1S LDO Under Voltage
