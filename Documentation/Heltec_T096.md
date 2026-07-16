# RNode Firmware on the Heltec Mesh Node T096

Support for the Heltec Mesh Node T096 was added to this fork on 2026-07-16,
modelled on the existing Heltec T114 support (same nRF52840 platform and
Arduino core) and the Heltec V4 support (same KCT8103L PA front end).

Pinout and hardware parameters were taken from the Meshtastic
`variants/nrf52840/heltec_mesh_node_t096` variant (develop branch) and the
manufacturer's published conduction test data.

> **Status:** compiles cleanly (245 KB, 11% of flash). Not yet verified on
> hardware — see the [bring-up checklist](#hardware-bring-up-checklist) below
> for the things to confirm on first boot.

---

## Quick reference: flash + set up from scratch

```sh
# 1. Build (Heltec nRF52 core 1.7.0, see Prerequisites below)
make firmware-heltec_t096
#    ...or directly:
arduino-cli compile --fqbn Heltec_nRF52:Heltec_nRF52:HT-n5262 -e \
  --build-property "build.partitions=no_ota" \
  --build-property "upload.maximum_size=2097152" \
  --build-property "compiler.cpp.extra_flags=\"-DBOARD_MODEL=0x46\""

# 2. Flash. Two options:
#    a) UF2 drag-and-drop: double-press the reset button, a USB drive
#       appears, copy build/Heltec_nRF52.Heltec_nRF52.HT-n5262/RNode_Firmware.ino.uf2 onto it.
#    b) Serial DFU:
arduino-cli upload -p <PORT> --fqbn Heltec_nRF52:Heltec_nRF52:HT-n5262
#       (or: adafruit-nrfutil dfu serial --package build/.../RNode_Firmware.ino.zip -p <PORT> -b 115200)

# 3. Provision the EEPROM (first time only - survives reflashes)
rnodeconf <PORT> -r --product cb --model cc --hwrev 1

# 4. Set the firmware hash (device self-attestation, like the T114):
rnodeconf <PORT> -L          # prints "The actual firmware hash is: <hash>"
rnodeconf <PORT> --firmware-hash <hash>

# 5. Check state:
rnodeconf <PORT> -i
```

Unlike the ESP32-S3 based Station G2, the nRF52840 does **not** reset when
the serial port is opened or closed, so plain rnodeconf works reliably for
all configuration writes. No manual restart after flashing is needed either —
the DFU bootloader starts the application automatically.

A healthy device reports:

```
Product            : Heltec Mesh Node T096 863 - 928 MHz (cb:cc:46)
Modem chip         : SX1262
Frequency range    : 863.0 MHz - 928.0 MHz
Max TX power       : 28 dBm
```

## Prerequisites (one-time host setup)

```sh
# Core + libraries (or run: make prep-nrf)
arduino-cli core update-index --config-file arduino-cli.yaml
arduino-cli core install Heltec_nRF52:Heltec_nRF52 --config-file arduino-cli.yaml
arduino-cli lib install "Adafruit ST7735 and ST7789 Library"
pip install adafruit-nrfutil    # only needed for serial DFU / release packaging
```

The stock rnodeconf does not know this board. Patch the local
`RNS/Utilities/rnodeconf.py` (re-apply after every `rns` upgrade):

- `ROM` class: `PRODUCT_HELTEC_T096 = 0xCB`, `BOARD_HELTEC_T096 = 0x46`, `MODEL_CC = 0xCC`
- `products` dict: `ROM.PRODUCT_HELTEC_T096: "Heltec Mesh Node T096",`
- `models` dict: `0xCC: [863000000, 928000000, 28, "863 - 928 MHz", "rnode_firmware_heltec_t096.zip", "SX1262"],`

---

## Hardware and port details

### Device overview

Low-power mesh node by Heltec Automation, released 2026.
Reference: [Heltec product page](https://heltec.org/project/t096/).

| Item | Value |
| --- | --- |
| MCU | nRF52840 (native USB-CDC, BLE 5) |
| Transceiver | Semtech SX1262, 32 MHz TCXO on DIO3 (1.8 V), DIO2 as RF switch |
| Frequency range | 863–928 MHz |
| PA/LNA | KCT8103L front end, 28 dBm max output, ~21 dB LNA gain |
| GNSS | UC6580 (not used by RNode firmware, kept powered off) |
| Display | 0.96" TFT, ST7735S controller, 80x160, SPI |
| Power | USB-C 5 V or 3.7 V LiPo (battery telemetry supported) |

### Firmware identifiers

| Define | Value |
| --- | --- |
| `PRODUCT_HELTEC_T096` | `0xCB` |
| `BOARD_HELTEC_T096` | `0x46` |
| `MODEL_CC` | `0xCC` (863–928 MHz, max 28 dBm output) |

### Pin mapping

From the Meshtastic `variants/nrf52840/heltec_mesh_node_t096` variant.
Arduino pin number = P0.x → x, P1.y → 32+y.

| Function | Pin |
| --- | --- |
| SX1262 SCK / MOSI / MISO / CS | P1.08 (40) / P0.11 / P0.14 / P0.05 |
| SX1262 RESET / DIO1 / BUSY | P0.16 / P0.21 / P0.19 |
| PA power (Vfem LDO) / CSD / CTX | P0.30 / P0.12 / P1.09 (41) |
| TFT SCK / MOSI / CS / DC / RST | P0.20 / P0.17 / P0.22 / P0.15 / P0.13 |
| TFT backlight (active high) | P1.12 (44) |
| Vext enable (TFT supply, active high) | P0.26 |
| User button (active low) | P1.10 (42) |
| Green LED (active high, shared RX/TX) | P0.28 |
| Battery ADC / ADC enable (active high) | P0.03 / P1.15 (47) |
| GNSS enable (active low, kept off) | P0.06 |

### Power amplifier and LNA handling

The T096 uses the same KCT8103L front end as the Heltec V4, but with a fixed
FEM model (no runtime detection) and its own gain table from the
manufacturer's conduction test data:

| Modem output (dBm) | PA gain | Antenna output |
| :---: | :---: | :---: |
| 0–12 | +14 dB | 14–26 dBm |
| 13–15 | +13 dB | 26–28 dBm |
| 16–21 | +12…+7 dB | 28 dBm |

- **TX power set from the host means actual output at the antenna port.**
- Maximum setting: **28 dBm** (`PA_MAX_OUTPUT`); higher requests are clamped.
- Minimum calibrated setting: **14 dBm** (modem 0 dBm + 14 dB gain).
  Settings below 14 drive the modem into its negative range down to the
  SX1262 floor of −9 dBm, so real output bottoms out around **5 dBm**
  regardless of how low the setting goes.
- The PA TX/RX path (CTX pin) is switched by the firmware on every
  transmit/receive transition; the LNA is in-path during receive, and
  `LORA_LNA_GAIN` = 21 dB is subtracted from reported RSSI so signal
  readings are antenna-referred.
- Heltec notes that stable high-power output requires a solid supply
  (charged LiPo or good USB source) — there is no separate PA supply input
  like on the Station G2.

**Regulatory note:** most unlicensed 868/915 MHz regimes cap output well
below 28 dBm — check your local rules before turning it up.

### Display

The 0.96" 80x160 ST7735S TFT is driven by the standard Adafruit ST7735
library (`INITR_MINI160x80`, which applies the panel's 24-pixel column
offset) over a dedicated SPIM0 bus, following the T-Deck's unbuffered-TFT
code path. Default orientation is portrait; the display rotation can be
changed with `rnodeconf --display-rotation`. Backlight is on/off only
(no intensity control), tied to the display blanking timer.

### Files touched by the port

| File | Change |
| --- | --- |
| `Boards.h` | Product/board/model defines, full board block |
| `Utilities.h` | LED functions, `MODEL_CC` TX power path, EEPROM product/model validation |
| `sx126x.cpp` | 1.8 V DIO3 TCXO for this board |
| `RNode_Firmware.ino` | Vext/GNSS power setup, serial-wait exclusion, sleep power-down |
| `Display.h` | Adafruit_ST7735 display path (SPIM0), backlight control, blanking |
| `Power.h` | Battery sensing (AIN1, divider 4.916, ADC enable pin) |
| `Makefile` | `firmware-heltec_t096`, `upload-heltec_t096`, `release-heltec_t096` targets |

### Known limitations

- The GNSS receiver is unused and held powered off.
- Backlight has no dimming; display intensity settings act as on/off.
- BLE serial is available (nRF52 platform standard); WiFi does not exist on
  this board.

---

## Hardware bring-up checklist

Things to verify on first flash, in order:

1. **Enumerates as USB serial** after flashing (no manual reset should be
   needed; if unresponsive, double-press reset and reflash via UF2).
2. **rnodeconf detects it** (`rnodeconf <PORT> -i` after provisioning).
3. **Display shows the RNode boot screen.** If the panel is dark: check
   backlight polarity (P1.12, assumed active high) and Vext (P0.26, assumed
   active high). If the image is offset or mirrored: the `INITR_MINI160x80`
   variant/rotation may need adjusting (`INITR_MINI160x80_PLUGIN` inverts
   colors; offsets are 24/0).
4. **RX works** (see traffic / RSSI values plausible, ~-100 dBm noise floor
   after LNA compensation).
5. **TX works at low power first** (set 14-17 dBm, confirm with another
   node), then verify high power with a proper antenna attached.
6. **Battery voltage** plausible on the display/`rnodeconf -i` when on LiPo
   (divider assumed 4.916; adjust `0.017300` in `Power.h` if consistently
   off).
7. **Button** flips display pages; **green LED** blinks on RX/TX.
