#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Boot a prepared synthetic installed update with its existing software TPM.

No networking, physical block device or owner data. The input disk and TPM are
copied; every observation finishes and is collected within this invocation.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import time

s=importlib.util.spec_from_file_location("mq",Path(__file__).with_name("migration-qemu.py"))
q=importlib.util.module_from_spec(s); s.loader.exec_module(q)


def boot_identity(image, work, label):
    """Check bytes, not whether OVMF happened to print a GPT GUID in its log."""
    with image.open("rb") as f: gpt=q.m.read_gpt(f.fileno())
    initrd=work/f"{label}-boot-initrd.img"
    q.m.run("mcopy","-i",f"{image}@@{q.m.extent(gpt['rows'][0])[0]}",
            "::/ruby/initrd-serial-logs.img",initrd)
    _,params=q.m.parse_initrd(initrd.read_bytes())
    q.m.require(params.get("androidboot.boot_part_uuid")==gpt["rows"][0]["partuuid"]
                and params.get("androidboot.openbook.ruby_installed")=="1"
                and params.get("androidboot.selinux")=="enforcing"
                and params.get("androidboot.veritymode")=="enforcing",
                "Installed disk-bound boot identity failed")
    return q.sha(initrd)


def nvme_selection(text):
    return all(value in text for value in (
        "metadata -> /dev/block/nvme0n1p7","super -> /dev/block/nvme0n1p8",
        "userdata -> /dev/block/nvme0n1p9","/dev/block/nvme0n1p7 /metadata ext4"))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("input","tpm-state-from","qemu","out"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--seconds",type=int,default=480)
    a=p.parse_args()
    q.m.require(Path("/.dockerenv").exists(),"Container only; no owner data")
    q.m.require(120<=a.seconds<=1800,"Bounded observation required")
    q.m.require(a.input.is_file() and not a.input.is_symlink(),"Regular synthetic image only")
    for path in (a.input,a.out,a.qemu,a.tpm_state_from):
        q.m.require(not any(c in str(path) for c in ",\n\r"),"Unsupported QEMU path")
    before=q.sha(a.input)
    tpm_before={f.name:q.sha(f) for f in a.tpm_state_from.iterdir() if f.is_file()}
    a.out.mkdir(mode=0o700)
    w=a.out.resolve()
    disk=w/"installed.img"
    q.m.run("cp","--reflink=auto",a.input,disk)
    source_keys=q.metadata_key_hashes(disk,w,"before")
    q.menu_default(disk,"ruby-serial-logs.conf",w)
    boot_before=boot_identity(disk,w,"before")
    shutil.copyfile("/usr/share/edk2/x64/OVMF_VARS.4m.fd",w/"vars.fd")
    with disk.open("rb") as f: gpt=q.m.read_gpt(f.fileno())
    esp_uuid=gpt["rows"][0]["partuuid"]
    cmd=[str(a.qemu),"-accel","tcg","-cpu","max","-machine","q35","-smp","4","-m","8192",
         "-display","none","-nic","none","-monitor","none","-no-reboot",
         "-drive","if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd",
         "-drive",f"if=pflash,format=raw,file={w}/vars.fd",
         "-device","virtio-vga","-device","qemu-xhci,id=xhci","-device","usb-kbd,bus=xhci.0",
         "-drive",f"file={disk},format=raw,if=none,id=target",
         "-device","nvme,drive=target,serial=INPUTUPDATETEST,bootindex=1",
         "-serial",f"file:{w}/serial.log","-qmp","unix:android-qmp.sock,server=on,wait=off",
         "-chardev","socket,id=chrtpm,path=tpm.sock","-tpmdev","emulator,id=tpm0,chardev=chrtpm",
         "-device","tpm-crb,tpmdev=tpm0","-audiodev","none,id=audio0",
         "-device","intel-hda","-device","hda-duplex,audiodev=audio0"]
    (w/"command.json").write_text(json.dumps(cmd,indent=2)+"\n")
    start=time.monotonic()
    with q.r.tpm_backend(w,True,a.tpm_state_from), (w/"qemu.log").open("wb") as log:
        proc=subprocess.Popen(cmd,cwd=w,stdout=log,stderr=subprocess.STDOUT)
        try:
            completed,events=q.observe(proc,w/"android-qmp.sock",a.seconds,w)
        finally:
            q.stop(proc)
    text=(w/"serial.log").read_text(errors="replace").replace("\r","")
    after_keys=q.metadata_key_hashes(disk,w,"after")
    result=dict(schema="openbook-ruby-installed-update-rehearsal/1",
        source_sha256=before,source_unchanged=q.sha(a.input)==before,
        source_tpm_unchanged=tpm_before=={f.name:q.sha(f) for f in a.tpm_state_from.iterdir() if f.is_file()},
        observation_completed=completed,elapsed_s=round(time.monotonic()-start,1),
        boot_completed=q.r.boot_completed_reported(text),
        target_uuid_printed_in_serial=esp_uuid.lower() in text.lower(),
        disk_bound_bootconfig_unchanged=boot_before==boot_identity(disk,w,"after"),
        nvme_partition_selection_observed=nvme_selection(text),
        metadata_keys_identical=source_keys==after_keys,
        metadata_key_files=len(source_keys),
        runtime_findings=q.r.runtime_findings(text),qmp_events=events,
        hardware_tested=False,owner_credentials_tested=False)
    (w/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
    required=("source_unchanged","source_tpm_unchanged","observation_completed","boot_completed",
              "disk_bound_bootconfig_unchanged","nvme_partition_selection_observed","metadata_keys_identical")
    q.m.require(all(result[k] for k in required),"Installed update rehearsal failed")


if __name__=="__main__":
    main()
