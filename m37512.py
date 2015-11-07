#!/usr/bin/python3

import os
import struct
import itertools
from collections import namedtuple

import smbus  # pip3 install smbus-cffi


from pprint import pprint
from hexdump import hexdump as _hexdump
def h(it, hdr=''):
    for line in _hexdump(bytes(it), result='generator'):
        print(hdr + line)


_MemBlock = namedtuple('MemBlock', ['addr', 'length', 'offset'])

_memmap = {
        'B' : _MemBlock(0x1000, 0x0800, 0x0000),
        'A' : _MemBlock(0x1800, 0x0800, 0x0800),
        '3' : _MemBlock(0x4000, 0x4000, 0x1000),
        '2' : _MemBlock(0x8000, 0x4000, 0x5000),
        '1' : _MemBlock(0xC000, 0x2000, 0x9000),
        '0' : _MemBlock(0xE000, 0x2000, 0xB000),
}

_memsize = sum([ b.length for b in _memmap.values() ])


class VerificationError(Exception):
    pass


class _M37512FlashBackend:
    """True backend. Use for reading/writing real M37512 memory over SMBUS."""
    def __init__(self, i2c_bus, bat_addr):
        self.bus = smbus.SMBus(i2c_bus)
        self.bat_addr = bat_addr

    def read16B(self, addr):
        """Read 16 bytes from flash memory (single transaction)"""
        # 0xFF -> sets read address (data=[AddrLO, AddrHI]); 0xFE -> returns 16 bytes
        self.bus.write_block_data(self.bat_addr, 0xFF, list(struct.pack('<H', addr)))
        r = bytes(self.bus.read_block_data(self.bat_addr, 0xFE))
        assert len(r) == 16  # if this fails, SMBUS API of your chip is probably different...
        return r

    def write(self, addr, data):
        """Writes up to 16 bytes to the flash memory (single transaction)"""
        # 0x40 -> write (data=[AddrLO, AddrHI, data0, data1, ..., data15])
        assert len(data) <= 16
        self.bus.write_block_data(self.bat_addr, 0x40, list(struct.pack('<H', addr) + data))

    def erase_block(self, addr):
        """Erase block. Address should be the last address *in* the block."""
        # 0x20 -> erase (data=[AddrHI, AddrLO]) note the different byte order in address!
        self.bus.write_block_data(self.bat_addr, 0x20, list(struct.pack('>H', addr)))


class _TestBackend:
    """File-only backend. Use for testing instead of _M37512FlashBackend
    to avoid needless flash wearing."""

    def __init__(self, i2c_bus, bat_addr):
        testing_filename = '/tmp/testbackend_{0}_{1:02x}.bin'.format(i2c_bus, bat_addr)
        try:
            self.f = DumpFile(testing_filename, 'r')
        except FileNotFoundError:
            self.f = DumpFile(testing_filename, 'w')
            self.f.save()

    def __addr_to_offset(self, addr):
        for a, l, o in _memmap.values():
            if addr >= a and addr < a + l:
                return o + addr - a
        raise ValueError("Wrong 'addr' value")

    def __addr_to_block(self, addr):
        for block, (a, l, o) in _memmap.items():
            if addr >= a and addr < a + l:
                return block
        raise ValueError("Wrong 'addr' value")

    def read16B(self, addr):
        offset = self.__addr_to_offset(addr)
        return self.f.mem_image[offset:offset+16]

    def write(self, addr, data):
        offset = self.__addr_to_offset(addr)
        l = len(data)
        assert l <= 16
        self.f.mem_image[offset:offset+l] = data
        self.f.save()

    def erase_block(self, addr):
        block = self.__addr_to_block(addr)
        length, offset = _memmap[block.upper()][1:3]
        self.mem_image[offset:offset+length] = b'\xFF' * length
        self.f.save()



class M37512Flash:
    """Class for reading/writing flash memory of M37512 over SMBUS interface"""

    def __init__(self, i2c_bus, bat_addr=0x0B):
        """i2c-bus: number of i2c bus to use; (/dev/i2c-<i2c_bus>)
        bat_addr: battery address on the i2c bus"""
#        self.__b = _M37512FlashBackend(i2c_bus, bat_addr)
        self.__b = _TestBackend(i2c_bus, bat_addr)

    def __read_block(self, block):
        """Read complete flash memory block (without verification)"""
        addr, length = _memmap[block.upper()][0:2]
        d, i = bytearray(length), 0
        while i < length:
            d[i:i+16] = self.__b.read16B(addr+i)
            i += 16
        return d

    def __write_data(self, addr, data):
        """Writes arbitrarily long data to the memory (multiple transactions, no verification)"""
        to_write, i, e = 0, 0, len(data)
        while i < e:
            to_write = min(16, e-i)
            self.__b.write(addr+i, data[i:i+to_write])
            i += to_write

    def erase_block(self, block):
        addr, length = _memmap[block.upper()][0:2]
        # calculate address of the last byte in the block
        self.__b.erase_block(addr + length - 1)

    def read_block(self, block):
        """Read complete flash memory block (with double check)"""
        print("Reading block {0}... (1st time)".format(block))
        d1 = self.__read_block(block)
        print("Reading block {0}... (2nd time)".format(block))
        d2 = self.__read_block(block)
        if d1 != d2:
            raise VerificationError
        return d1

    def write_block(self, block, data):
        """Write complete block to the memory (optimized, with verification)"""
        # This one is more complicated to avoid unneeded writes/erase cycles.
        addr, length = _memmap[block.upper()][0:2]
        assert len(data) == length
        # 1st, read and compare existing contents of the block
        erase_needed = False


        self.__write_block(block)
        d2 = self.__read_block(block)
        if data != d2:
            raise VerificationError

    def verify_block(self, block, data):
        """Verify if memory block contains specified contents"""
        existing_data = self.read_block(block)
        if existing_data != data:
            raise VerificationError




class DumpFile:
    """Class representing BE2Works-compatible M37512 memory dump file"""

    def __init__(self, file_name, mode):
        self.file_name = file_name
        if mode == 'r':
            # preread the existing file
            with open(self.file_name, 'rb') as f:
                self.mem_image = bytearray(f.read())
                assert len(self.mem_image) == _memsize
        else:
            # prepare empty buffer to be filled up
            self.mem_image = bytearray(itertools.repeat(0xFF, _memsize))

    def get_block(self, block):
        length, offset = _memmap[block.upper()][1:3]
        return self.mem_image[offset:offset+length]

    def put_block(self, block, data):
        length, offset = _memmap[block.upper()][1:3]
        assert len(data) == length
        self.mem_image[offset:offset+length] = data

    def save(self):
        with open(self.file_name, 'wb') as f:
            f.write(self.mem_image)



if __name__ == "__main__":
    dev = M37512Flash(5)
    f = DumpFile('/tmp/x.bin', 'w')
    for block in _memmap.keys():
        f.put_block(block, dev.read_block(block))
    f.save()
#    dev.read_block('1')
