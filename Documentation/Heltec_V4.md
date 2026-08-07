# RNode Firmware on the Heltec LoRa32 V4

The Heltec LoRa32 V4 is an ESP32-S3 board (native USB-CDC) with an SX1262
modem and a PA/LNA front end (GC1109 or KCT8103L, auto-detected at boot —
see [TX_Power.md](TX_Power.md) for gain tables and calibrated ranges).

## Quick reference: build + flash + provision

```sh
# 1. Build (or: make firmware-heltec32_v4)
arduino-cli compile --fqbn "esp32:esp32:esp32s3:CDCOnBoot=cdc" -e \
  --build-property "build.partitions=no_ota" \
  --build-property "upload.maximum_size=2097152" \
  --build-property "compiler.cpp.extra_flags=\"-DBOARD_MODEL=0x3F\""

# 2. Flash (device already in download mode: hold BOOT, tap RESET, release BOOT)
arduino-cli upload -p <PORT> --fqbn esp32:esp32:esp32s3 --input-dir build/esp32.esp32.esp32s3

# 3. Provision the EEPROM (first time only — survives reflashes)
rnodeconf <PORT> -r --product c3 --model c8 --hwrev 1

# 4. Set the firmware hash (device self-attestation)
python partition_hashes build/esp32.esp32.esp32s3/RNode_Firmware.ino.bin
rnodeconf <PORT> --firmware-hash <hash>

# 5. Check state (target and actual hashes must match):
rnodeconf <PORT> -i
rnodeconf <PORT> -K   # target hash (from EEPROM)
rnodeconf <PORT> -L   # actual hash (device-calculated)
```

A healthy device reports:

```
Product            : Heltec LoRa32 v4 850 - 950 MHz (c3:c8:3f)
Modem chip         : SX1262
Frequency range    : 860.0 MHz - 930.0 MHz
Max TX power       : 28 dBm
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| "Firmware corrupt" on the console/display after `rnodeconf --firmware-hash`, even though the command reported "Firmware hash set" | Like the Station G2, this is an ESP32-S3 board with native USB-CDC: it resets on serial port control-line transitions, **including port close**. `rnodeconf` writes the hash byte-by-byte and closes the port right after, so the reset interrupts the write partway through — `-K` then shows the target hash correct for the first few bytes and `0xFF` (unwritten) after that. | Retry `rnodeconf <PORT> --firmware-hash <hash>` and re-check with `-K` after each attempt. Each retry tends to commit further into the value (the flash page write is progressive), so a handful of retries — verified in practice: 5 — converges on a full match. Compare against `-L` (the device's own calculated hash) to confirm you're retrying with the right value. |

## Firmware identifiers

| Define | Value |
| --- | --- |
| `PRODUCT_H32_V4` | `0xC3` |
| `BOARD_HELTEC32_V4` | `0x3F` |
| Model (rnodeconf) | `0xC8` (850–950 MHz, max 28 dBm output) |

## Power amplifier and LNA handling

See [TX_Power.md](TX_Power.md) for the full gain tables, calibrated TX
ranges, and the GC1109/KCT8103L auto-detection mechanism (`sx126x.cpp`).
