#!/usr/bin/env python3
"""Build seed.iso containing the install scripts, attached to the VM as a 2nd CD-ROM."""
import io, re, pathlib, pycdlib

BASE = pathlib.Path(__file__).resolve().parent.parent
SEED = BASE / "seed"
OUT  = BASE / "iso" / "seed.iso"

FILES = ["bootstrap.sh", "chroot-setup.sh", "firstboot.sh", "vm.conf"]


def build():
    missing = [f for f in FILES if not (SEED / f).exists()]
    if missing:
        raise SystemExit(f"missing seed files: {missing}")

    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, rock_ridge="1.09", vol_ident="ARCHSEED")

    for name in FILES:
        data = (SEED / name).read_bytes()
        # normalise to LF - CRLF would break the scripts inside Linux
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        stem, _, ext = name.rpartition(".")
        # ISO9660 permits only A-Z 0-9 _ in names
        stem = re.sub(r"[^A-Z0-9_]", "_", stem.upper())[:8]
        ext = re.sub(r"[^A-Z0-9_]", "_", ext.upper())[:3]
        iso.add_fp(
            io.BytesIO(data), len(data),
            f"/{stem}.{ext};1",
            rr_name=name,
            joliet_path=f"/{name}",
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    iso.write(str(OUT))
    iso.close()
    return OUT


if __name__ == "__main__":
    out = build()
    print(f"built {out}  ({out.stat().st_size} bytes)")
    for f in FILES:
        print(f"   + {f}")
