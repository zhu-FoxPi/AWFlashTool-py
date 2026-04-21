"""
Allwinner Firmware Parser
Supports sunxi IMAGEWTY and Boot0 formats
"""

import struct
import logging
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger(__name__)

# Partition type to name mapping
CHUNK_NAMES = {
    0x7000: "boot0",
    0x7001: "boot1",
    0x7002: "mbr",
    0x7003: "uboot",
    0x7004: "tos",          # OP-TEE / secure OS
    0x7005: "boot_img",     # kernel + initrd
    0x7006: "rootfs",
    0x7007: "data",
    0x7008: "env",
    0x7009: "env_redund",
    0x7010: "boot-resource",
    0x7011: "dsp0",
    0x7012: "logo",
    0x7013: "recovery",
    0x7014: "fastboot",
    0x7015: "boot_package",
    0x7016: "swupdate",
}


def get_chunk_name(type_id: int) -> str:
    """Get partition name from type ID"""
    return CHUNK_NAMES.get(type_id, f"data_{type_id:04X}")


class Partition:
    """A single partition in a firmware image"""

    def __init__(self, name: str, offset: int, size: int, data: bytes = None):
        self.name = name
        self.offset = offset
        self.size = size
        self.data = data

    def __repr__(self):
        return f"<Partition {self.name}: {self.size} bytes @ 0x{self.offset:X}>"


class FirmwareImage:
    """Parsed firmware image"""

    def __init__(self, file_path: str, img_type: str, chip_id: str, total_size: int, partitions: list):
        self.file_path = file_path
        self.type = img_type
        self.chip_id = chip_id
        self.total_size = total_size
        self.partitions = partitions

    def __repr__(self):
        return f"<FirmwareImage {self.type}: {len(self.partitions)} partitions, {self.total_size} bytes>"


def parse_imagewty(buffer: bytes) -> FirmwareImage:
    """
    Parse IMAGEWTY (sunxi flash image) format.

    Header structure (0x00-0x1F):
      0x00-0x07: "IMAGEWTY" magic
      0x08-0x0B: version
      0x0C-0x0F: total_size
      0x10-0x13: chunk_header_size (usually 0x20)
      0x14-0x17: chunk_count
    """
    magic = buffer[0:8].decode("ascii", errors="replace")
    if magic != "IMAGEWTY":
        raise ValueError(f"Invalid IMAGEWTY magic: {magic}")

    version = struct.unpack("<I", buffer[0x08:0x0C])[0]
    total_size = struct.unpack("<I", buffer[0x0C:0x10])[0]
    chunk_header_size = struct.unpack("<I", buffer[0x10:0x14])[0]
    chunk_count = struct.unpack("<I", buffer[0x14:0x18])[0]

    logger.info(f"IMAGEWTY: version=0x{version:X}, chunks={chunk_count}, total_size={total_size}")

    partitions = []
    offset = 0x20  # Start of first chunk

    for i in range(chunk_count):
        if offset + 32 > len(buffer):
            break

        chunk_type = struct.unpack("<I", buffer[offset:offset + 4])[0]
        chunk_size = struct.unpack("<I", buffer[offset + 4:offset + 8])[0]
        data_offset = offset + 32

        name = get_chunk_name(chunk_type)
        data = buffer[data_offset:data_offset + chunk_size]

        partitions.append(Partition(
            name=name,
            offset=data_offset,
            size=chunk_size,
            data=data,
        ))

        logger.info(f"  chunk {i}: {name} (0x{chunk_type:X}), {chunk_size} bytes @ 0x{data_offset:X}")

        # Advance to next chunk (aligned to 32 bytes)
        offset += 32 + chunk_size
        if chunk_size % 32 != 0:
            offset += 32 - (chunk_size % 32)

    return FirmwareImage(
        file_path="",
        img_type="sunxi",
        chip_id="sunxi",
        total_size=total_size,
        partitions=partitions,
    )


def parse_boot0(buffer: bytes) -> FirmwareImage:
    """Parse eGON.BT0 (Boot0) format."""
    magic = buffer[0:8].decode("ascii", errors="replace")
    if not (magic.startswith("eGON.BT0") or magic.startswith("eGON.FE0")):
        raise ValueError(f"Invalid Boot0 magic: {magic}")

    logger.info(f"Boot0 format: {magic}")

    partition = Partition(name="boot0", offset=0, size=len(buffer), data=buffer)

    return FirmwareImage(
        file_path="",
        img_type="boot0",
        chip_id="boot0",
        total_size=len(buffer),
        partitions=[partition],
    )


def parse_boot0_variant(buffer: bytes) -> FirmwareImage:
    """Parse alternate Boot0 variant (starts with 0x6F 0x00 0x80 0x3C)."""
    logger.info("Boot0 variant format")

    partition = Partition(name="boot0", offset=0, size=len(buffer), data=buffer)

    return FirmwareImage(
        file_path="",
        img_type="boot0_variant",
        chip_id="boot0",
        total_size=len(buffer),
        partitions=[partition],
    )


def parse_firmware(file_path: str) -> FirmwareImage:
    """
    Auto-detect and parse a firmware file.
    Supports: IMAGEWTY, eGON.BT0, eGON.FE0, and boot0 variant
    """
    with open(file_path, "rb") as f:
        buffer = f.read()

    magic = buffer[0:8].decode("ascii", errors="replace")
    logger.info(f"Parsing firmware: magic='{magic}', size={len(buffer)} bytes")

    if magic == "IMAGEWTY":
        fw = parse_imagewty(buffer)
    elif magic.startswith("eGON.BT0") or magic.startswith("eGON.FE0"):
        fw = parse_boot0(buffer)
    elif buffer[0:4] == bytes.fromhex("6f00803c"):
        fw = parse_boot0_variant(buffer)
    else:
        raise ValueError(f"Unknown firmware format: magic='{magic}', hex={buffer[0:8].hex()}")

    fw.file_path = file_path
    return fw
