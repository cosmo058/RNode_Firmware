# RNode Firmware on the B&Q Consulting Station G2

Support for the Station G2 was added to this fork on 2026-07-14 and verified
end-to-end on real hardware: radio provisioned, display working, WiFi/TCP
host mode working, firmware validation passing.

This document is a **complete runbook** — following the Quick Reference below
avoids every pitfall we hit while bringing the board up. The pitfalls
themselves are explained in [Troubleshooting](#troubleshooting).

---

## Quick reference: flash + set up from scratch

```sh
# 1. Build (ESP32 Arduino core 2.0.17 + libs from `make prep-esp32`)
make firmware-station_g2
#    ...or directly:
arduino-cli compile --fqbn "esp32:esp32:esp32s3:CDCOnBoot=cdc" -e \
  --build-property "build.partitions=no_ota" \
  --build-property "upload.maximum_size=2097152" \
  --build-property "compiler.cpp.extra_flags=\"-DBOARD_MODEL=0x45\""

# 2. Flash (first time: force download mode — hold 💾, tap 🔄, wait 5 s, release 💾.
#    Subsequent flashes usually enter download mode automatically.)
arduino-cli upload -p <PORT> --fqbn esp32:esp32:esp32s3 --input-dir build/esp32.esp32.esp32s3

# 3. *** PRESS THE 🔄 RESTART BUTTON *** — mandatory after every flash!
#    Until then the port responds but the firmware is NOT running.

# 4. Provision the EEPROM (first time only — survives reflashes)
rnodeconf <PORT> -r --product e2 --model e5 --hwrev 1

# 5. WiFi credentials + firmware hash — use the helper script, NOT rnodeconf
#    (see Troubleshooting: "Writes silently lost"). Verifies everything it sets.
python station_g2_setup.py <PORT> \
  --ssid <ssid> --psk '<psk>' \
  --firmware-hash-from build/esp32.esp32.esp32s3/RNode_Firmware.ino.bin \
  --reboot

# 6. Check state anytime:
python station_g2_setup.py <PORT> --status
rnodeconf <PORT> -i
```

A healthy device reports:

```
Product            : B&Q Consulting Station G2 815 - 940 MHz (e2:e5:45)
Firmware version   : 1.86
Modem chip         : SX1262
Frequency range    : 815.0 MHz - 940.0 MHz
Max TX power       : 35 dBm
```

## Reticulum over WiFi (TCP)

Once connected to WiFi (station mode), the device serves its KISS interface
on **TCP port 7633** (single client). The IP is shown on one of the OLED info
pages (flip pages with the ℹ️ button). Reticulum config:

```ini
[[Station G2 RNode]]
    type = RNodeInterface
    enabled = yes
    port = tcp://<device-ip>:7633
    frequency = 914875000
    bandwidth = 125000
    txpower = 17
    spreadingfactor = 8
    codingrate = 5
```

Give the device a DHCP reservation (or set a static IP with
`rnodeconf --ip/--nm`) so the address never changes. WiFi MAC = the base MAC
printed by `esptool read_mac`.

---

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| "RNode did not respond" right after flashing | The G2 does not leave ROM download mode from esptool's software reset. The port enumerates but the firmware is not running. | Press the 🔄 restart button. Always required after flashing. |
| WiFi settings / firmware hash silently not saved; `-c` shows WiFi Disabled; display says "Firmware corrupt" with a partial target hash | The G2 resets on serial port control-line transitions, **including port close**. rnodeconf sends write-only commands and closes the port immediately — the reset interrupts the slow byte-by-byte EEPROM commits. | Use `station_g2_setup.py`, which holds the session open and verifies every write by reading it back. If you must use rnodeconf, verify afterwards (`-c` for WiFi, `-K` vs `-L` for hashes) and re-run on failure. |
| "Firmware corrupt" on display | Target hash in EEPROM (from `-K`) doesn't match the device-calculated hash (`-L`) — usually a partial write (see above), or the hash was set for a different build. | `python station_g2_setup.py <PORT> --firmware-hash-from <the .bin you flashed>` then restart. |
| Blank OLED | Wrong driver init: Adafruit's SH1107 init sends `0xAD 0x8A` (internal DC-DC **off**, for their external-VPP panels), which leaves the G2's CH1115 panel unpowered. The panel still ACKs on I2C, so init "succeeds". | Already fixed in `Display.h`: the G2 uses a `CH1115Display` subclass of `Adafruit_SH1106G` (DC-DC **on**) with `_page_start_offset = 0` — equivalent to Meshtastic's SH1106 "subtype 7". |
| rnodeconf `-c` prints both "WiFi: Enabled (Station)" **and** "WiFi: Disabled" | Upstream rnodeconf display bug (dangling `else` on the AP check). | Ignore. The "Enabled (Station)" line is correct. |
| rnodeconf `-i` crashes with `KeyError: 229` | Stock rnodeconf doesn't know model `0xE5`. | Patch the local `rnodeconf.py`: add `PRODUCT_STATION_G2 = 0xE2` / `MODEL_E5 = 0xE5` to the `ROM` class, a name to `products`, and `0xE5: [815000000, 940000000, 35, "815 - 940 MHz", "rnode_firmware_station_g2.zip", "SX1262"]` to `models`. Must be re-applied after upgrading the `rns` package. |
| Very weak TX despite high power setting | The PA is powered by a dedicated 7.5 V rail that only exists on 15 V USB-C PD or 9–19 V DC input. On plain 5 V USB the modem transmits through an unpowered PA. | Use a PD supply or the DC input for real output power. |

---

## Hardware and port details

### Device overview

Discontinued Meshtastic base-station device by B&Q Consulting
(Unit Engineering). Reference: [uniteng wiki](https://wiki.uniteng.com/en/meshtastic/station-g2).

| Item | Value |
| --- | --- |
| MCU | ESP32-S3 (16 MB flash, 8 MB PSRAM), native USB-CDC |
| Transceiver | Semtech SX1262 |
| Frequency range | 815–940 MHz |
| Reference clock | 32 MHz TCXO (±1.5 ppm), powered from SX1262 DIO3 at 1.8 V |
| PA | Up to 35 dBm (P1dB), ~20 dB gain, dedicated 7.5 V rail |
| LNA | ~19 dB gain, 1.8 dB noise figure, always in the RX path |
| Display | 1.3" OLED, CH1115 controller (SH1106-like), I2C 0x3C |
| Power | 15 V USB-C PD, or 9–19 V DC input (either required for the PA) |

### Firmware identifiers

| Define | Value |
| --- | --- |
| `PRODUCT_STATION_G2` | `0xE2` |
| `BOARD_STATION_G2` | `0x45` |
| `MODEL_E5` | `0xE5` (815–940 MHz, max 35 dBm output) |

The firmware also accepts Homebrew models (`MODEL_FE`/`MODEL_FF`) so an
unpatched rnodeconf can provision the device (capped at 17 dBm host-side).

### Pin mapping

From the Meshtastic `variants/esp32s3/station-g2` variant (verified against
the v2.3.15 tag).

| Function | GPIO |
| --- | --- |
| SPI SCK / MOSI / MISO / CS | 12 / 13 / 14 / 11 |
| SX1262 RESET / DIO1 / BUSY | 21 / 48 / 47 |
| SX1262 DIO2 | RF switch (internal, no GPIO) |
| SX1262 DIO3 | 1.8 V TCXO supply (internal, no GPIO) |
| Program button | 38 (input pullup) |
| I2C SDA / SCL (OLED, GROVE, QWIIC) | 5 / 6 |
| GROVE GPS RX / TX | 7 / 15 (unused by RNode) |
| User LEDs | none (HV/PA/LV LEDs are hardware power indicators) |

### Power amplifier and LNA handling

The PA and LNA sit between the SX1262 and the antenna port with **no control
lines to the MCU**. The port uses the firmware's static PA gain-table
mechanism (`HAS_LORA_PA` + `PA_GAIN_VALUES`), populated from the
manufacturer's US915 conduction test data:

- **TX power set from the host means actual output at the antenna port**
  (when the PA is powered), not SX1262 modem output.
- Output is capped at `PA_MAX_OUTPUT` = 35 dBm (the PA's P1dB), which
  corresponds to 16 dBm modem output — safely below the manufacturer's
  19 dBm modem limit.
- `LORA_PA_INTEGRATED` (`0x03`) is a new PA-model constant for PAs without
  MCU control lines; none of the Heltec V4-style PA GPIO switching runs.
- `HAS_LORA_LNA` with `LORA_LNA_GAIN` = 19 subtracts the LNA gain from
  reported RSSI, so signal readings are antenna-referred.

**Regulatory note:** US unlicensed ISM operation is capped at 30 dBm into the
antenna. The 31–35 dBm range is for licensed (e.g. amateur radio) use.

### Files touched by the port

| File | Change |
| --- | --- |
| `Boards.h` | Product/board/model defines, `LORA_PA_INTEGRATED`, full board block |
| `Utilities.h` | No-op LED functions, `MODEL_E5` TX power path, EEPROM product/model validation |
| `sx126x.cpp` | S3 SPI pin init, 1.8 V DIO3 TCXO |
| `RNode_Firmware.ino` | Skip `while (!Serial)` on boot (native USB-CDC) |
| `Display.h` | `CH1115Display` driver (SH1106G subclass), I2C pins, init, rotation |
| `Makefile` | `firmware-station_g2`, `upload-station_g2`, `release-station_g2` targets |
| `station_g2_setup.py` | Reliable WiFi/firmware-hash configuration helper (new) |

### Known limitations

- Battery telemetry is not available (no battery sense circuit on the G2).
- Deep sleep is disabled (`HAS_SLEEP false`) — it is a base-station device.
- The WiFi TCP interface accepts a single client at a time.
