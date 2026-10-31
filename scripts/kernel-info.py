#!/usr/bin/env python3
"""Decompress an x86 bzImage, print its version banner and dump the embedded .config (IKCONFIG).
Usage: kernel-info.py KERNEL OUT_DIR   (needs lz4/zstd/xz/gzip binaries on PATH)"""
import gzip, os, subprocess, sys

MAGICS = [(b'\x02\x21\x4c\x18', ['lz4', '-dc']), (b'\x28\xb5\x2f\xfd', ['zstd', '-dcq']),
          (b'\xfd7zXZ\x00', ['xz', '-dcq']), (b'\x1f\x8b\x08', ['gzip', '-dcq'])]

def main(kernel, out):
    data = open(kernel, 'rb').read()
    os.makedirs(out, exist_ok=True)
    for magic, cmd in MAGICS:
        off = data.find(magic)
        while off != -1:
            p = subprocess.run(cmd, input=data[off:], capture_output=True)
            vm = p.stdout
            if vm[:4] == b'\x7fELF':
                open(os.path.join(out, 'vmlinux'), 'wb').write(vm)
                i = vm.find(b'Linux version ')
                print(vm[i:vm.find(b'\n', i)].decode(errors='replace'))
                s = vm.find(b'IKCFG_ST')
                if s != -1:
                    e = vm.find(b'IKCFG_ED', s)
                    cfg = gzip.decompress(vm[s + 8:e])
                    open(os.path.join(out, 'config'), 'wb').write(cfg)
                    print(f'wrote {out}/config ({len(cfg)} bytes)')
                else:
                    print('no IKCONFIG in image')
                return
            off = data.find(magic, off + 1)
    sys.exit('no decompressible vmlinux payload found')

if __name__ == '__main__':
    main(*sys.argv[1:3])
