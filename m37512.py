#!/usr/bin/python3

import os, sys
import struct
import itertools
from collections import namedtuple

import smbus  # pip3 install smbus-cffi


from pprint import pprint
from hexdump import hexdump as _hexdump
def h(it, hdr=''):
    for line in _hexdump(bytes(it), result='generator'):
        print(hdr + line)

# Settings:
_i2c_dev = 5
_bat_addr = 0x0b
# End of settings


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
        self.f.mem_image[offset:offset+length] = b'\xFF' * length
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

    def read_block(self, block):
        """Read complete flash memory block (with double check)"""
        print("Reading block {0}... (1st time)".format(block))
        d1 = self.__read_block(block)
        print("Reading block {0}... (2nd time)".format(block))
        d2 = self.__read_block(block)
        print("Comparing...", end='')
        if d1 != d2:
            print(" READ ERROR!", end='\n\n')
            raise VerificationError
        print(" READ OK", end='\n\n')
        return d1

    def write_block(self, block, data):
        """Write complete block to the memory (optimized, with verification)"""
        # This one is more complicated to avoid unneeded writes/erase cycles.
        addr, length = _memmap[block.upper()][0:2]
        assert len(data) == length

        # 1st, read and compare existing contents of the block
        print("Checking if write of block {0} is needed...".format(block))
        i, write_needed, erase_needed = 0, False, False
        existing_data = bytearray(length)
        while i < length and not erase_needed:
            j = 0
            existing_data[i:i+16] = self.__b.read16B(addr+i)
            while j < 16:
                if existing_data[i+j] != data[i+j]:
                    write_needed = True
                    if existing_data[i+j] != 0xFF:
                        erase_needed = True
                        break
                j += 1
            i += 16
        print("Check result: write_needed={0}, erase_needed={1}".format(write_needed, erase_needed))

        # 2nd, erase the data if needed
        if erase_needed:
            # calculate address of the last byte in the block
            print("Erasing block {0}...".format(block))
            self.__b.erase_block(addr + length - 1)
            existing_data[:] = b'\xFF' * length

        # 3rd, write the data
        if write_needed:
            print("Writing block {0}...".format(block))
            start, i = -1, 0
            while i < length:
                if existing_data[i] != data[i]:
                    if start < 0:
                        start = i
                else:
                    if start >= 0:
                        print("  write start={0:5d}: {1:4d}bytes  {2:02x}..{3:02x}".format(start, len(data[start:i]), data[start:i][0], data[start:i][-1]))
                        self.__write_data(addr+start, data[start:i])
                        start = -1
                i += 1
            if start >= 0:
                print("  WRITE start={0:5d}: {1:4d}bytes  {2:02x}..{3:02x}".format(start, len(data[start:]), data[start:][0], data[start:][-1]))
                self.__write_data(addr+start, data[start:])

            # 4th, verify the data
            existing_data = self.__read_block(block)
            if data != existing_data:
                raise VerificationError

    def verify_block(self, block, data):
        """Verify if memory block contains specified contents"""
        existing_data = self.read_block(block)
        print("Verifying...", end='')
        if existing_data != data:
            print(" VERIFICATION ERROR!", end='\n\n')
            raise VerificationError
        print(" VERIFICATION OK", end='\n\n')


class DumpFile:
    """Class representing BE2Works-compatible M37512 memory dump file"""

    def __init__(self, file_name, mode):
        self.file_name = file_name
        if mode == 'r':
            # read the existing file
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


def main():
    def help():
        print("Usage:")
        print("\t{0} <dump_file> <mem_operation> [mem_blocks]\n".format(sys.argv[0]))
        print("Arguments:")
        print("\t <dump_file>     - path to the memory dump file (local image of the flash)")
        print("\t <mem_operation> - operation to be done on the M37512 flash:")
        print("\t                   * read   - dump flash memory contents into the file;")
        print("\t                   * write  - store contents from the dump file to the flash;")
        print("\t                   * verify - check if the flash and dump file are the same")
        print("\t [mem_blocks]    - which memory blocks should be written/verified (AB0123)\n")

    # read command line arguments
    if len(sys.argv) < 3:
        help()
        return 1
    dump_file_name = sys.argv[1]
    operation = sys.argv[2]
    blocks = "AB0123" if len(sys.argv) == 3 else sys.argv[3].upper()

    # prepare for the job
    if operation == 'read':
        blocks = "AB0123"  # always read all blocks to make sure the dump file is complete
        f = DumpFile(dump_file_name, 'w')
        action = lambda dev, f, block: f.put_block(block, dev.read_block(block))
    elif operation == 'write':
        f = DumpFile(dump_file_name, 'r')
        action = lambda dev, f, block: dev.write_block(block, f.get_block(block))
    elif operation == 'verify':
        f = DumpFile(dump_file_name, 'r')
        action = lambda dev, f, block: dev.verify_block(block, f.get_block(block))
    else:
        help()
        raise ValueError("Invalid value of 'mem_operation' argument!")

    # and finally, do it
    dev = M37512Flash(_i2c_dev, _bat_addr)
    for block in blocks:
        if block in _memmap:
            action(dev, f, block)
        else:
            print("Ignoring wrong block name: {0}".format(block))

    # save the file if we were writing data from memory to it
    if operation == 'read':
        f.save()

    return 0


if __name__ == "__main__":
    sys.exit(main())
