# RNode Firmware on the Heltec Mesh Node T096

Support for the Heltec Mesh Node T096 was added to this fork on 2026-07-16,
modelled on the existing Heltec T114 support (same nRF52840 platform and
Arduino core) and the Heltec V4 support (same KCT8103L PA front end).

Pinout and hardware parameters were taken from the Meshtastic
`variants/nrf52840/heltec_mesh_node_t096` variant (develop branch) and the
manufacturer's published conduction test data.

> **Status:** verified on real hardware 2026-07-16 — display, provisioning,
> EEPROM, firmware validation all working (device cb:cc:46, serial
> 00:00:00:02). Radio RX/TX and battery telemetry not yet field-tested.
> Three hardware bring-up bugs were found and fixed; they are all described
> in [Troubleshooting](#troubleshooting) so nobody has to rediscover them.

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

# 2. Flash over SERIAL DFU - this is the only fully correct method:
arduino-cli upload -p <PORT> --fqbn Heltec_nRF52:Heltec_nRF52:HT-n5262 --input-dir build/Heltec_nRF52.Heltec_nRF52.HT-n5262
#    (equivalent: adafruit-nrfutil dfu serial --package <...>.zip -p <PORT> -b 115200 --touch 1200)
#    No button presses needed: the 1200 baud touch enters the bootloader
#    even if the running application is frozen, and the app auto-starts
#    after flashing.
#
#    UF2 drag-and-drop (double-press reset, copy the .uf2) also works BUT
#    does not update the bootloader's image-size record, so firmware
#    validation always fails afterwards ("Firmware corrupt" on screen).
#    Use it only for recovery, and follow up with a serial DFU flash.

# 3. Provision the EEPROM (first time only - survives reflashes).
#    PATIENCE: the "Bootstrapping device EEPROM" step takes 30+ seconds
#    of silence. Do not interrupt or power-cycle during it.
rnodeconf <PORT> -r --product cb --model cc --hwrev 1

# 4. Set the firmware hash (device self-attestation, like the T114).
#    The device reboots itself after the hash write; give it ~30 s.
rnodeconf <PORT> -L          # prints "The actual firmware hash is: <hash>"
rnodeconf <PORT> --firmware-hash <hash>

# 5. Check state (target and actual hashes must match):
rnodeconf <PORT> -i
rnodeconf <PORT> -K
rnodeconf <PORT> -L
```

Unlike the ESP32-S3 based Station G2, the nRF52840 does **not** reset when
the serial port is opened or closed, so plain rnodeconf works reliably for
all configuration writes.

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

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Backlight on, screen otherwise dark ("no image") | The display sits on a custom SPIM0 bus; `Adafruit_SPITFT::initSPI` only starts the core's predefined SPI interfaces, so without an explicit `displaySPI.begin()` the panel never receives a single bit. | Fixed in `Display.h` (commit `82cb168`). |
| Screen completely dark | Backlight pin P1.12 is active **low** — declared only in Meshtastic's `platformio.ini` (`TFT_BACKLIGHT_ON=LOW`), not in `variant.h`. | Fixed in `Display.h` (commit `83fecab`). When porting from Meshtastic, always read `platformio.ini` build flags too. |
| `rnodeconf` says "Could not download EEPROM" although the firmware version was read | rnodeconf gives the device only 0.6 s to answer. Per-pixel TFT drawing (~8000 SPI transactions/frame) stalled the main loop past that deadline. | Fixed with bulk row transfers (commit `e925999`). If it still happens right after a reboot, simply retry — the device is busiest during its first seconds. |
| Device frozen after provisioning: USB port enumerates but nothing answers, screen black/stuck | Firmware was flashed via **UF2 drag-and-drop**, which leaves the bootloader's image-size record (flash `0xFF008`) erased. On a *provisioned* device, boot-time firmware validation then hashed a bogus 4 GB region and hard-faulted. | Reflash over **serial DFU** (`arduino-cli upload`), which writes the record. Firmware now also guards against this (`Device.h`): a UF2-flashed device fails validation gracefully ("Firmware corrupt") instead of freezing. |
| Device stops responding during provisioning or `--firmware-hash`; rnodeconf hangs | The emulated EEPROM commits every byte to internal flash individually (~160 writes for provisioning); the device can wedge during such write storms while USB stays enumerated. The writes themselves usually complete first. | Reflash over serial DFU — the 1200 baud touch works even when the app is frozen and doubles as a remote reset. Then verify with `-i` / `-K` / `-L`; the interrupted writes are usually intact. |
| "Firmware corrupt" on display | Target hash unset (fresh provision), stale (set for a different build), or the device was UF2-flashed (see above). | After every reflash: `rnodeconf <PORT> -L`, then `--firmware-hash <hash>`, then let it reboot. If UF2-flashed, serial-DFU reflash first. |
| Port number changes / device briefly gone | The nRF re-enumerates USB after every reset (including the self-reset after `--firmware-hash`). | Wait ~10-30 s, re-check the port list. |
| `rnodeconf -i` crashes with `KeyError: 204` | Stock rnodeconf doesn't know model `0xCC`. | Apply the rnodeconf patch from [Prerequisites](#prerequisites-one-time-host-setup). |

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
| TFT backlight (active **low**, per Meshtastic `TFT_BACKLIGHT_ON=LOW`) | P1.12 (44) |
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
| `Device.h` | Guard against unwritten bootloader image-size record (UF2 flashing) |
| `Power.h` | Battery sensing (AIN1, divider 4.916, ADC enable pin) |
| `Makefile` | `firmware-heltec_t096`, `upload-heltec_t096`, `release-heltec_t096` targets |

### Known limitations

- The GNSS receiver is unused and held powered off.
- Backlight has no dimming; display intensity settings act as on/off.
- BLE serial is available (nRF52 platform standard); WiFi does not exist on
  this board.

---

## Hardware verification status

Verified on the real device (2026-07-16): USB enumeration and serial DFU
flashing, display (portrait, rotation 0, correct backlight), EEPROM
provisioning as `cb:cc:46`, device signature validation, firmware hash
validation (target == actual, no "Firmware corrupt").

Still to verify in the field:

1. **RX** (traffic received / plausible RSSI, ~-100 dBm noise floor after
   the 21 dB LNA compensation).
2. **TX at low power first** (14-17 dBm against another node), then high
   power with a proper antenna attached.
3. **Battery voltage** plausible when on LiPo (divider assumed 4.916;
   adjust the `0.017300` factor in `Power.h` if consistently off).
4. **Button** flips display pages; **green LED** blinks on RX/TX.
5. Display cosmetics: if the image is offset, mirrored, or color-inverted,
   adjust the `INITR_MINI160x80` init/rotation in `Display.h`
   (`INITR_MINI160x80_PLUGIN` inverts colors; offsets are 24/0).
