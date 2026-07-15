#!/usr/bin/env python3

# Reliable post-flash configuration for the B&Q Consulting Station G2.
#
# The G2 resets when the serial port control lines transition, including on
# port close. rnodeconf sends write-only commands (WiFi settings, firmware
# hash) and closes the port immediately, so on this board the reset can
# interrupt the EEPROM writes mid-way, silently losing settings or leaving a
# partially written firmware hash ("Firmware corrupt" on the display).
#
# This script performs the same operations over a single serial session that
# is held open while the device commits, and verifies every write by reading
# it back before exiting. See Documentation/Station_G2.md for the full story.
#
# Usage examples:
#   python station_g2_setup.py COM20 --status
#   python station_g2_setup.py COM20 --ssid mynet --psk 'secret' --firmware-hash-from build/esp32.esp32.esp32s3/RNode_Firmware.ino.bin
#   python station_g2_setup.py COM20 --wifi-mode off

import argparse
import hashlib
import sys
import time

try:
    import serial
except ImportError:
    print("This script requires pyserial (pip install pyserial)")
    sys.exit(1)

FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD

CMD_DETECT    = 0x08
CMD_ROM_READ  = 0x51
CMD_RESET     = 0x55
CMD_FW_HASH   = 0x58
CMD_HASHES    = 0x60
CMD_WIFI_MODE = 0x6A
CMD_WIFI_SSID = 0x6B
CMD_WIFI_PSK  = 0x6C
CMD_CFG_READ  = 0x6D

ADDR_CONF_WIFI = 0xBA
ADDR_CONF_SSID = 0x00
ADDR_CONF_PSK  = 0x21

WIFI_MODES = {"off": 0x00, "station": 0x01, "sta": 0x01, "ap": 0x02}


def kiss_escape(data):
    out = bytearray()
    for b in data:
        if b == FEND:
            out += bytes([FESC, TFEND])
        elif b == FESC:
            out += bytes([FESC, TFESC])
        else:
            out.append(b)
    return bytes(out)


def kiss_unescape(data):
    out = bytearray()
    esc = False
    for b in data:
        if esc:
            out.append(FEND if b == TFEND else (FESC if b == TFESC else b))
            esc = False
        elif b == FESC:
            esc = True
        else:
            out.append(b)
    return bytes(out)


def kiss_frame(cmd, payload=b""):
    return bytes([FEND, cmd]) + kiss_escape(payload) + bytes([FEND])


class StationG2:
    def __init__(self, port, retries=8):
        self.serial = None
        for attempt in range(1, retries + 1):
            try:
                s = serial.Serial(port, 115200, timeout=0.5)
            except Exception:
                time.sleep(2)
                continue
            # Opening the port may reset the device; give it time to boot.
            time.sleep(2.5)
            try:
                s.reset_input_buffer()
                s.write(kiss_frame(CMD_DETECT, b"\x73"))
                s.flush()
                time.sleep(0.8)
                if b"\xc0\x08\x46\xc0" in s.read(64):
                    self.serial = s
                    print(f"Device connected on {port} (attempt {attempt})")
                    return
                s.close()
            except Exception:
                try:
                    s.close()
                except Exception:
                    pass
            time.sleep(1.5)
        print("Could not connect to the device. Is it flashed and restarted?")
        print("Remember: after flashing, the G2 needs a manual press of the")
        print("restart button before the firmware starts running.")
        sys.exit(1)

    def send(self, cmd, payload=b"", settle=1.5):
        self.serial.write(kiss_frame(cmd, payload))
        self.serial.flush()
        time.sleep(settle)

    def request(self, cmd, payload=b"", timeout=4.0):
        self.serial.reset_input_buffer()
        self.serial.write(kiss_frame(cmd, payload))
        self.serial.flush()
        deadline = time.time() + timeout
        data = b""
        while time.time() < deadline:
            data += self.serial.read(4096)
        for f in data.split(bytes([FEND])):
            if len(f) > 1 and f[0] == cmd:
                return kiss_unescape(f[1:])
        return None

    def close(self, settle=3.0):
        # Hold the session before closing: the close-triggered reset must not
        # land while the device is still committing EEPROM writes.
        time.sleep(settle)
        self.serial.close()

    def read_rom(self):
        return self.request(CMD_ROM_READ, b"\x00")

    def read_cfg(self):
        return self.request(CMD_CFG_READ, b"\x00")

    def read_hash(self, which):
        resp = self.request(CMD_HASHES, bytes([which]))
        if resp and len(resp) >= 33:
            return resp[1:33]
        return None


def cstring(data):
    return data.split(b"\x00")[0].split(b"\xff")[0].decode("utf-8", "replace")


def bin_hash(path):
    data = open(path, "rb").read()
    calc = hashlib.sha256(data[0:-32]).digest()
    if calc != data[-32:]:
        print(f"Error: {path} does not carry a valid trailing image hash")
        sys.exit(1)
    return calc


def show_status(dev):
    rom = dev.read_rom()
    cfg = dev.read_cfg()
    target = dev.read_hash(0x01)
    actual = dev.read_hash(0x02)
    print()
    if rom and len(rom) > ADDR_CONF_WIFI:
        mode = rom[ADDR_CONF_WIFI]
        mode_str = {0x01: "Station", 0x02: "Access Point"}.get(mode, "Off")
        print(f"  Provisioned identity : {rom[0]:02x}:{rom[1]:02x} hwrev {rom[2]}")
        print(f"  WiFi mode            : {mode_str}")
    if cfg and len(cfg) > ADDR_CONF_PSK + 32:
        ssid = cstring(cfg[ADDR_CONF_SSID:ADDR_CONF_SSID + 32])
        psk = cstring(cfg[ADDR_CONF_PSK:ADDR_CONF_PSK + 32])
        print(f"  WiFi SSID            : {ssid if ssid else '(not set)'}")
        print(f"  WiFi PSK             : {'set (' + str(len(psk)) + ' chars)' if psk else '(not set)'}")
    if target and actual:
        ok = "OK, hashes match" if target == actual else "MISMATCH - device will report firmware corrupt"
        print(f"  Target fw hash       : {target.hex()}")
        print(f"  Actual fw hash       : {actual.hex()}")
        print(f"  Firmware validation  : {ok}")
    print()


def main():
    p = argparse.ArgumentParser(description="Reliable Station G2 RNode configuration")
    p.add_argument("port", help="Serial port, e.g. COM20 or /dev/ttyACM0")
    p.add_argument("--status", action="store_true", help="Show stored configuration and hash state")
    p.add_argument("--ssid", help="Set WiFi SSID (implies station mode unless --wifi-mode given)")
    p.add_argument("--psk", help="Set WiFi PSK")
    p.add_argument("--wifi-mode", choices=sorted(set(WIFI_MODES)), help="Set WiFi mode")
    p.add_argument("--firmware-hash", metavar="HEX", help="Set target firmware hash (64 hex chars)")
    p.add_argument("--firmware-hash-from", metavar="BIN", help="Compute and set target hash from a firmware .bin")
    p.add_argument("--reboot", action="store_true", help="Reboot the device when done")
    args = p.parse_args()

    dev = StationG2(args.port)
    failures = 0

    if args.ssid is not None:
        dev.send(CMD_WIFI_SSID, args.ssid.encode("utf-8") + b"\x00")
    if args.psk is not None:
        dev.send(CMD_WIFI_PSK, args.psk.encode("utf-8") + b"\x00")

    mode = None
    if args.wifi_mode is not None:
        mode = WIFI_MODES[args.wifi_mode]
    elif args.ssid is not None:
        mode = WIFI_MODES["station"]
    if mode is not None:
        # Starting WiFi takes a moment; give the handler extra settle time.
        dev.send(CMD_WIFI_MODE, bytes([mode]), settle=5.0)

    target_hash = None
    if args.firmware_hash_from:
        target_hash = bin_hash(args.firmware_hash_from)
    elif args.firmware_hash:
        target_hash = bytes.fromhex(args.firmware_hash)
    if target_hash is not None:
        if len(target_hash) != 32:
            print("Error: firmware hash must be 32 bytes")
            sys.exit(1)
        # 32 individual EEPROM commits; give it generous settle time.
        dev.send(CMD_FW_HASH, target_hash, settle=8.0)

    # Verify everything that was set
    if args.ssid is not None or args.psk is not None:
        cfg = dev.read_cfg()
        if args.ssid is not None:
            stored = cstring(cfg[ADDR_CONF_SSID:ADDR_CONF_SSID + 32]) if cfg else ""
            if stored == args.ssid:
                print(f"Verified: SSID stored ({stored})")
            else:
                print(f"FAILED: SSID readback was '{stored}'")
                failures += 1
        if args.psk is not None:
            stored = cstring(cfg[ADDR_CONF_PSK:ADDR_CONF_PSK + 32]) if cfg else ""
            if stored == args.psk:
                print("Verified: PSK stored")
            else:
                print("FAILED: PSK readback did not match")
                failures += 1
    if mode is not None:
        rom = dev.read_rom()
        if rom and len(rom) > ADDR_CONF_WIFI and rom[ADDR_CONF_WIFI] == mode:
            print(f"Verified: WiFi mode stored (0x{mode:02x})")
        else:
            print("FAILED: WiFi mode readback did not match")
            failures += 1
    if target_hash is not None:
        stored = dev.read_hash(0x01)
        if stored == target_hash:
            print("Verified: target firmware hash stored")
        else:
            print(f"FAILED: target hash readback was {stored.hex() if stored else 'empty'}")
            failures += 1

    if args.status or (args.ssid is None and args.psk is None and mode is None and target_hash is None):
        show_status(dev)

    if args.reboot:
        dev.send(CMD_RESET, b"\xf8", settle=0.5)
        print("Reboot command sent")

    dev.close()
    if failures:
        print(f"{failures} write(s) failed verification - re-run this script")
        sys.exit(1)


if __name__ == "__main__":
    main()
