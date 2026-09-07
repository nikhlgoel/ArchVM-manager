"""
Build seed.iso in-process.

This used to shell out to manager/build_seed.py, which only exists in a source
checkout - so a packaged build could never regenerate the ISO. pycdlib is
already a dependency, so do it here instead.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from . import paths

FILES = ("bootstrap.sh", "chroot-setup.sh", "firstboot.sh", "repair.sh", "vm.conf")


def build(dest: Path | None = None) -> tuple[bool, str]:
    """Write seed.iso from the scripts in the seed folder. Returns (ok, message)."""
    try:
        import pycdlib
    except ImportError:
        return False, "pycdlib is not available, so seed.iso cannot be built."

    out = Path(dest) if dest else (paths.ISO_DIR / "seed.iso")
    missing = [f for f in FILES if not (paths.SEED_DIR / f).exists()]
    if missing:
        return False, "Missing from the seed folder: " + ", ".join(missing)

    try:
        iso = pycdlib.PyCdlib()
        iso.new(interchange_level=3, joliet=3, rock_ridge="1.09",
                vol_ident="ARCHSEED")
        for name in FILES:
            data = (paths.SEED_DIR / name).read_bytes()
            # CRLF inside the guest produces "$'\r': command not found".
            data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            stem, _, ext = name.rpartition(".")
            stem = re.sub(r"[^A-Z0-9_]", "_", stem.upper())[:8]
            ext = re.sub(r"[^A-Z0-9_]", "_", ext.upper())[:3]
            iso.add_fp(io.BytesIO(data), len(data), f"/{stem}.{ext};1",
                       rr_name=name, joliet_path=f"/{name}")
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()
        iso.write(str(out))
        iso.close()
    except Exception as e:
        return False, f"Could not build seed.iso: {e}"

    return True, f"seed.iso rebuilt ({out.stat().st_size} bytes)"
