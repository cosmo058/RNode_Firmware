# TX power on PA-equipped boards

Three boards supported by this fork have a power amplifier and LNA
between the SX1262 modem and the antenna port: the Heltec LoRa32 V4,
the Heltec Mesh Node T096, and the B&Q Station G2.

On all of them the firmware knows the PA's gain curve, so **the TX
power set from the host is the actual output at the antenna port** —
the modem drive level is back-calculated from the gain table, and
requests above the board maximum are clamped. Received RSSI is
likewise antenna-referred: the LNA gain is subtracted before values
are reported.

| Board | Max setting | Calibrated range | Real floor¹ | PA / FEM | LNA gain | Frequency range |
| --- | :---: | :---: | :---: | --- | :---: | :---: |
| Heltec LoRa32 V4 (`c3:c8:3f`) | 28 dBm (~630 mW) | 11–28 dBm (GC1109) / 13–28 dBm (KCT8103L) | ~2 / ~4 dBm | GC1109 **or** KCT8103L, auto-detected at boot | 17 / 21 dB | 850–950 MHz |
| Heltec T096 (`cb:cc:46`) | 28 dBm (~630 mW) | 14–28 dBm | ~5 dBm | KCT8103L (fixed) | 21 dB | 863–928 MHz |
| Station G2 (`e2:e5:45`) | 35 dBm (~3.2 W) | 20–35 dBm | ~11 dBm² | Integrated PA module, no MCU control lines | 19 dB | 815–940 MHz |

¹ Settings below the calibrated range drive the modem into its
negative output range, which bottoms out at the SX1262 floor of
−9 dBm; real antenna output therefore stops falling at roughly
(−9 dBm + minimum PA gain) no matter how low the setting goes.

² Only meaningful when the G2's PA is powered at all — see below.

## Gain tables

PA gain by modem output level, from each manufacturer's conduction
test data (`PA_GAIN_VALUES` / `PA_*_VALUES` in `Boards.h`):

| Modem output (dBm) | V4 GC1109 | V4 KCT8103L | T096 KCT8103L | G2 |
| :---: | :---: | :---: | :---: | :---: |
| 0–12 | +11 | +13 | +14 | +20 |
| 13 | +11 | +13 | +13 | +20 |
| 14 | +11 | +12 | +13 | +20 |
| 15 | +11 | +12 | +13 | +19 |
| 16 | +10 | +11 | +12 | +19 (cap: 35 dBm) |
| 17 | +10 | +11 | +11 | — |
| 18 | +9 | +10 | +10 | — |
| 19 | +9 | +9 | +9 | — |
| 20 | +8 | +8 | +8 | — |
| 21 | +7 (cap: 28 dBm) | +7 (cap: 28 dBm) | +7 (cap: 28 dBm) | — |

The G2's 35 dBm cap is the PA's P1dB compression point, reached at
just 16 dBm of modem drive — the modem is deliberately kept well
below the PA's 19 dBm saturation limit.

## Board-specific notes

### Heltec LoRa32 V4

Ships with one of two FEM chips. The firmware detects which one at
boot by powering the FEM and reading back the CSD pin
(`sx126x.cpp`), then applies the matching TX gain table and LNA
compensation (17 dB for the GC1109, 21 dB for the KCT8103L). Full
details, including a provisioning gotcha shared with the Station G2,
in [Heltec_V4.md](Heltec_V4.md).

### Heltec T096

Same KCT8103L front end as (some) V4s, but the FEM model is fixed,
so no runtime detection. The PA TX/RX path (CTX pin) is switched by
the firmware on every transmit/receive transition. Heltec notes that
stable high-power output needs a solid supply — a charged LiPo or a
good USB source. Full details in [Heltec_T096.md](Heltec_T096.md).

### Station G2

The PA runs from a dedicated 7.5 V rail that only exists when the
device is supplied by 15 V USB-C PD or the 9–19 V DC input. **On
plain 5 V USB the modem transmits but the unpowered PA heavily
attenuates the output** — actual radiated power will be nowhere near
the setting. The PA and LNA have no control lines to the MCU. Full
details in [Station_G2.md](Station_G2.md).

## Regulatory note

Most unlicensed 868/915 MHz regimes cap radiated power well below
these hardware maxima — 28 dBm usually exceeds them and 35 dBm
certainly does. Check the rules that apply to your band, region and
antenna before turning the setting up.
