"""
Allwinner FEL USB Communication
Python implementation using pyusb (libusb)
"""

import usb.core
import usb.util
import struct
import logging
import time
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)

# Allwinner FEL USB Vendor ID / Product ID
AW_VID = 0x1F3A
AW_PID = 0xEF68

# FEL USB Endpoints
FEL_BULK_OUT = 0x01
FEL_BULK_IN = 0x81
FEL_TIMEOUT_MS = 5000

# FEL Protocol Commands
FEL_CMD_BOARD_INFO = 0x00000001
FEL_CMD_CHIP_ID = 0x00000002
FEL_CMD_FEL_FLAG = 0x00000003
FEL_CMD_VERSION = 0x00000004
FEL_CMD_WRITE_SRAM = 0x00000006
FEL_CMD_EXECUTE = 0x00000007
FEL_CMD_READ_SRAM = 0x00000008
FEL_CMD_WRITE_MEM = 0x00000009
FEL_CMD_READ_MEM = 0x0000000A
FEL_CMD_DRAM_INIT = 0x0000000B
FEL_CMD_STANDBY = 0x0000000C
FEL_CMD_ERASE = 0x0000000D

# EFEX Commands
EFEX_CMD_FEL_INIT = 0x01
EFEX_CMD_FEL_READ = 0x02
EFEX_CMD_FEL_WRITE = 0x03
EFEX_CMD_FEL_EXEC = 0x04
EFEX_CMD_FEL_VERIFY = 0x05
EFEX_CMD_FES_QUERY = 0x06
EFEX_CMD_FES_GET_CHIPID = 0x07
EFEX_CMD_FEL_REINIT = 0x08
EFEX_CMD_STORAGE_READ = 0x09
EFEX_CMD_STORAGE_WRITE = 0x0A
EFEX_CMD_STORAGE_ERASE = 0x0B
EFEX_CMD_FEL_RECONNECT = 0x0C

# Chip Database
CHIP_DB = {
    0x00000001: "Allwinner A10",
    0x00000002: "Allwinner A10s",
    0x00000003: "Allwinner A13",
    0x00000004: "Allwinner A20",
    0x00000010: "Allwinner V821",
    0x00000011: "Allwinner V853",
    0x00000012: "Allwinner H616",
    0x00000013: "Allwinner R328",
    0x00000014: "Allwinner H6",
    0x00000015: "Allwinner V316",
    0x00000016: "Allwinner V536",
    0x00000017: "Allwinner V533",
    0x00000018: "Allwinner R329",
}


class FelDevice:
    """FEL device connection via USB"""

    def __init__(self):
        self.handle: Optional[usb.core.Device] = None
        self.chip_id: Optional[str] = None
        self.chip_name: Optional[str] = None
        self.protocol: str = "fel"
        self.connected: bool = False
        self._debug_callback = None

    def set_debug_callback(self, cb):
        self._debug_callback = cb

    def debug(self, msg: str):
        logger.debug(msg)
        if self._debug_callback:
            self._debug_callback(msg)

    def scan(self) -> List[dict]:
        """Scan for Allwinner FEL devices"""
        devices = []
        try:
            found = usb.core.find(idVendor=AW_VID, idProduct=AW_PID, find_all=True)
            if found:
                for dev in found:
                    try:
                        addr = dev.address
                        port = ".".join(map(str, dev.port_numbers)) if dev.port_numbers else "0"
                        devices.append({
                            "vid": f"{AW_VID:04x}",
                            "pid": f"{AW_PID:04x}",
                            "address": addr,
                            "port": port,
                            "device": dev,
                        })
                    except Exception as e:
                        logger.warning(f"Error reading device info: {e}")
        except usb.core.NoBackendError:
            logger.error("libusb backend not found. Is libusb installed?")
        return devices

    def connect(self, device) -> dict:
        """Connect to a FEL device"""
        try:
            self.debug(f"Connecting to device at address {device.get('address', '?')}...")
            dev = device.get("device")
            if not dev:
                raise ValueError("No device provided")

            # Detach kernel driver if attached
            try:
                if dev.is_kernel_driver_active(0):
                    dev.detach_kernel_driver(0)
            except Exception:
                pass

            # Claim interface
            usb.util.claim_interface(dev, 0)

            self.handle = dev
            self.debug("USB interface claimed")

            # Try FEL ping
            try:
                self.fel_ping()
                self.protocol = "fel"
                self.debug("FEL protocol detected")
            except Exception:
                self.debug("FEL ping failed, trying EFEX...")
                try:
                    self.efex_ping()
                    self.protocol = "efex"
                    self.debug("EFEX protocol detected")
                except Exception as e:
                    raise Exception(f"Neither FEL nor EFEX responded: {e}")

            # Get chip ID
            chip_id_num = self.get_chip_id()
            self.chip_id = f"0x{chip_id_num:08X}"
            self.chip_name = CHIP_DB.get(chip_id_num, f"Unknown ({self.chip_id})")
            self.debug(f"Chip ID: {self.chip_id} ({self.chip_name})")

            self.connected = True
            return {
                "success": True,
                "chip_id": self.chip_id,
                "chip_name": self.chip_name,
                "protocol": self.protocol,
            }

        except Exception as e:
            self.disconnect()
            raise e

    def disconnect(self):
        """Disconnect from device"""
        if self.handle:
            try:
                usb.util.release_interface(self.handle, 0)
            except Exception:
                pass
            self.handle = None
        self.connected = False
        self.chip_id = None
        self.chip_name = None

    def fel_request(self, cmd: int, data: bytes = b"", expect_response: bool = True) -> bytes:
        """Send FEL request and receive response"""
        if not self.handle:
            raise Exception("Device not connected")

        # Build FEL packet
        # Header: magic(4) + len(4) + cmd(4) + reserved(4) = 16 bytes
        header = struct.pack("<IIII", 0x4155534C, 16 + len(data), cmd, 0)
        packet = header + data

        self.debug(f"FEL OUT: cmd=0x{cmd:X} len={len(packet)}")

        # Bulk write
        try:
            self.handle.write(FEL_BULK_OUT, packet, timeout=FEL_TIMEOUT_MS)
        except usb.core.USBError as e:
            raise Exception(f"USB write failed: {e}")

        if not expect_response:
            return b""

        # Bulk read
        try:
            response = self.handle.read(FEL_BULK_IN, 1024, timeout=FEL_TIMEOUT_MS)
            self.debug(f"FEL IN: {len(response)} bytes")
            return bytes(response)
        except usb.core.USBError as e:
            raise Exception(f"USB read failed: {e}")

    def fel_ping(self) -> bytes:
        """Ping FEL device"""
        return self.fel_request(FEL_CMD_VERSION, b"")

    def get_chip_id(self) -> int:
        """Get chip ID"""
        response = self.fel_request(FEL_CMD_CHIP_ID, b"")
        if len(response) < 4:
            raise Exception("Invalid chip ID response")
        return struct.unpack("<I", response[0:4])[0]

    def fel_ping_version(self) -> str:
        """Get FEL version string"""
        response = self.fel_request(FEL_CMD_VERSION, b"")
        return response[:32].decode("utf-8", errors="replace").strip("\x00")

    def read_mem(self, addr: int, length: int) -> bytes:
        """Read memory"""
        param = struct.pack("<II", addr, length)
        response = self.fel_request(FEL_CMD_READ_MEM, param)
        return response[8:]  # Skip header

    def write_mem(self, addr: int, data: bytes):
        """Write memory"""
        param = struct.pack("<II", addr, len(data))
        packet = param + data
        self.fel_request(FEL_CMD_WRITE_MEM, packet, expect_response=True)

    def exec(self, addr: int):
        """Execute code at address"""
        param = struct.pack("<I", addr)
        self.fel_request(FEL_CMD_EXECUTE, param, expect_response=True)

    def init_dram(self, params: bytes = b"") -> bool:
        """Initialize DRAM"""
        self.debug("Initializing DRAM...")
        self.fel_request(FEL_CMD_DRAM_INIT, params, expect_response=True)
        self.debug("DRAM initialized")
        return True

    def efex_ping(self) -> bytes:
        """Ping EFEX device"""
        cmd = struct.pack("<II", EFEX_CMD_FEL_INIT, 0)
        return self.efex_request(cmd)

    def efex_request(self, cmd: bytes, data: bytes = b"", expect_response: bool = True) -> bytes:
        """Send EFEX request"""
        if not self.handle:
            raise Exception("Device not connected")

        packet = cmd + data
        self.debug(f"EFEX OUT: cmd=0x{struct.unpack('<I', cmd[:4])[0]:X} len={len(packet)}")

        try:
            self.handle.write(FEL_BULK_OUT, packet, timeout=FEL_TIMEOUT_MS)
        except usb.core.USBError as e:
            raise Exception(f"USB write failed: {e}")

        if not expect_response:
            return b""

        try:
            response = self.handle.read(FEL_BULK_IN, 1024, timeout=FEL_TIMEOUT_MS)
            self.debug(f"EFEX IN: {len(response)} bytes")
            return bytes(response)
        except usb.core.USBError as e:
            raise Exception(f"USB read failed: {e}")

    def efex_read(self, addr: int, length: int) -> bytes:
        """EFEX read memory"""
        cmd = struct.pack("<II", EFEX_CMD_FEL_READ, 0)
        param = struct.pack("<II", addr, length)
        response = self.efex_request(cmd, param)
        return response[8:]

    def efex_write(self, addr: int, data: bytes):
        """EFEX write memory"""
        cmd = struct.pack("<II", EFEX_CMD_FEL_WRITE, 0)
        param = struct.pack("<II", addr, len(data))
        packet = param + data
        self.efex_request(cmd, packet)

    def storage_read(self, offset: int, length: int) -> bytes:
        """Read from storage (Flash)"""
        if self.protocol != "efex":
            raise Exception("Storage read requires EFEX protocol")
        cmd = struct.pack("<II", EFEX_CMD_STORAGE_READ, 0)
        param = struct.pack("<II", offset, length)
        response = self.efex_request(cmd, param)
        return response[8:]

    def storage_write(self, offset: int, data: bytes, progress_callback=None) -> bool:
        """Write to storage (Flash)"""
        if self.protocol != "efex":
            raise Exception("Storage write requires EFEX protocol")

        chunk_size = 32 * 1024  # 32KB
        written = 0

        while written < len(data):
            chunk = data[written:written + chunk_size]
            chunk_offset = offset + written

            cmd = struct.pack("<II", EFEX_CMD_STORAGE_WRITE, 0)
            param = struct.pack("<II", chunk_offset, len(chunk))
            packet = param + chunk

            self.efex_request(cmd, packet)
            written += len(chunk)

            if progress_callback:
                progress_callback({
                    "bytes_written": written,
                    "total_bytes": len(data),
                    "percent": (written * 100) // len(data),
                })

        return True

    def storage_erase(self, offset: int, length: int, progress_callback=None) -> bool:
        """Erase storage (Flash)"""
        if self.protocol != "efex":
            raise Exception("Storage erase requires EFEX protocol")

        cmd = struct.pack("<II", EFEX_CMD_STORAGE_ERASE, 0)
        param = struct.pack("<II", offset, length)
        self.efex_request(cmd, param)

        if progress_callback:
            progress_callback({"percent": 100})

        return True


def get_chip_name(chip_id: int) -> str:
    """Look up chip name from ID"""
    return CHIP_DB.get(chip_id, f"Unknown (0x{chip_id:08X})")
