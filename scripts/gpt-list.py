#!/usr/bin/env python3
"""List GPT partitions (name, type GUID, start, size) of a disk image without root."""
import struct, sys, uuid

def main(path):
    with open(path, 'rb') as f:
        f.seek(512)
        hdr = f.read(92)
        if hdr[:8] != b'EFI PART':
            sys.exit('no GPT header at LBA1')
        entries_lba, n, esz = struct.unpack_from('<QII', hdr, 72)
        f.seek(entries_lba * 512)
        raw = f.read(n * esz)
    print(f"{'#':>3} {'name':<20} {'start':>10} {'sectors':>10} {'MiB':>8}  type-guid")
    for i in range(n):
        e = raw[i * esz:(i + 1) * esz]
        tguid = uuid.UUID(bytes_le=e[0:16])
        if tguid.int == 0:
            continue
        first, last = struct.unpack_from('<QQ', e, 32)
        name = e[56:128].decode('utf-16-le').rstrip('\x00')
        sectors = last - first + 1
        print(f"{i+1:>3} {name:<20} {first:>10} {sectors:>10} {sectors*512/2**20:>8.1f}  {tguid}")

if __name__ == '__main__':
    main(sys.argv[1])
