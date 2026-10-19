# quired 0.3.0 into the G14's existing Linux environment (2026-10-19 14:04Z)

A new guest image would replace the person's Linux files, so the package was upgraded in place, typed into the laptop's
Terminal over adb: the `.deb` built with the VM's image (`quired_0.3.0_amd64.deb`, sha256 `e0d86a59…3ad8`) was
served once on the LAN for the download, checked against that sha256 in the guest, installed with `dpkg -i`, and
`quired` restarted. The Terminal printed `/tmp/q.deb: OK`, `Unpacking quired (0.3.0) over (0.2.1)`, `quired 0.3.0`,
`active`. This host's firewall dropped the first port; a read-only container on another port served it.
