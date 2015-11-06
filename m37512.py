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


class M37512Flash:
    """Class for reading/writing flash memory of M37512 over SMBUS interface"""

    def __init__(self, i2c_bus, bat_addr=0x0B):
        self.bus = smbus.SMBus(i2c_bus)
        self.bat_addr = bat_addr

    def __read16B(self, addr):
        """Read 16 bytes from flash memory (one transaction)"""
        # 0xFF -> sets read address (data=[AddrLO, AddrHI]); 0xFE -> returns 16 bytes
        self.bus.write_block_data(self.bat_addr, 0xFF, list(struct.pack('<H', addr)))
        r = bytes(self.bus.read_block_data(self.bat_addr, 0xFE))
        assert len(r) == 16  # if this fails, SMBUS API of your chip is probably different...
        return r

    def __write16B(self, addr, data):
        """Writes 16 bytes to the flash memory (one transaction). Device seems to accept different sizes,
        but 16 bytes were chosen for simplicity / similarity with read process."""
        # 0x40 -> write (data=[AddrLO, AddrHI, data0, data1, ..., data15])
        assert len(data) == 16
        self.bus.write_block_data(self.bat_addr, 0x40, list(struct.pack('<H', addr) + data))

    def __erase_block(self, addr):
        """Erase block. Address should be the last address *in* the block."""
        # 0x20 -> erase (data=[AddrHI, AddrLO]) note the different byte order in address!
        self.bus.write_block_data(self.bat_addr, 0x20, list(struct.pack('>H', addr)))


    def __read_block(self, block):
        """Read complete flash memory block (without verification)"""
        addr, length = _memmap[block.upper()][0:2]
        d = bytearray(length)
        i = 0
        while i < length:
            d[i:i+16] = self.__read16B(addr+i)
            i += 16
        return d

    def __write_block(self, block, data):
        """Writes complete block to the memory (without verification)"""
        addr, length = _memmap[block.upper()][0:2]
        assert len(data) == length
        existing_data = self.__read_block(block)
        i = 0
        while i < length:
            # write only rows which are different than memory contents
            if existing_data[i:i+16] != data[i:i+16]:
                self.__write16B(addr+i, data[i:i+16])
            i += 16

    def read_block(self, block):
        """Read complete flash memory block (with verification)"""
        d1 = self.__read_block(block)
        d2 = self.__read_block(block)
        if d1 != d2:
            raise VerificationError
        return d1

    def write_block(self, block, data):
        """Writes complete block to the memory (with verification)"""
        self.__write_block(block)
        d2 = self.__read_block(block)
        if data != d2:
            raise VerificationError

    def erase_block(self, block):
        addr, length = _memmap[block.upper()][0:2]
        # calculate address of the last byte in the block
        self.__erase_block(addr + length - 1)




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
#    for block in _memmap.keys():
#        f.put_block(block, dev.read_block(block))
#    f.save()
#    dev.read_block('1')
