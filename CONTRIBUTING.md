# Contributing

Thanks for taking an interest. This is a small project with a narrow purpose, so
the bar for changes is "does it make the VM easier to run on Windows".

---

## Getting set up

```bash
git clone https://github.com/nikhlgoel/ArchVM-manager.git
cd ArchVM-manager
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python app/run.py
```

Python 3.10 or newer. The app itself only needs `PySide6-Essentials` and
`pycdlib`; `Pillow` and `pyinstaller` are for building.

You do **not** need a working VM to develop the interface. The app starts, the
wizard runs and every page renders without QEMU installed — missing pieces are
reported as warnings, not crashes. Set `ARCHVM_ROOT` to a scratch directory so
nothing touches a real VM:

```bash
set ARCHVM_ROOT=C:\Temp\archvm-dev
```

---

## Before you open a pull request

```bash
python -m pyflakes app/archvm/*.py app/*.py app/tools/*.py manager/*.py
python -m compileall -q app manager
```

Both must be silent. There is no test suite yet; if you add one, put it in
`tests/` and wire it into the CI workflow.

Please also start the app and click through the pages your change touches. A
screenshot in the pull request is welcome for anything visual.

---

## House style

- **Line endings matter.** Everything in `seed/` must stay LF — CRLF breaks the
  scripts inside Linux with `$'\r': command not found`. `.gitattributes` enforces
  this, but configure your editor too.
- **Nothing may crash the app.** Host probing, registry reads, Win32 calls and
  config loading are all wrapped so a failure degrades to a default rather than a
  traceback. Keep it that way.
- **Every interactive widget needs an accessible name.** `widgets.button()` and
  `widgets.a11y()` do this for you. There is a post-build sweep that catches
  what you miss, but relying on it is not the intent.
- **Comments explain *why*, not *what*.** Match the density of the surrounding
  code.
- No new runtime dependencies without a good reason.

---

## Commit messages

Conventional commits, lowercase subject, imperative mood, no trailing period:

```
feat(ui): collapse the navigation rail below 900 px
fix(setup): retry the ISO download once on a truncated response
docs: explain the ARCHVM_ROOT fallback order
```

Types in use: `feat`, `fix`, `docs`, `build`, `refactor`, `chore`. Scope is
optional. Explain the reasoning in the body when the subject cannot carry it.

---

## Things that will be declined

- **GPU passthrough.** It is not possible on a Windows host. See the README for
  why. Patches claiming otherwise will be closed.
- **Ports to Linux or macOS as a thin shim.** The app is built on winget, dism,
  the Windows registry and Win32 APIs. On Linux, use `virt-manager` — it is
  better at this than a port of this app would be. A genuine platform
  abstraction layer is a different conversation and worth having first in an
  issue.
- Bundling the Arch ISO or the desktop configuration. Both are downloaded from
  their sources, verified, and belong to their authors.

---

## Reporting bugs

Open an issue with the version from **About**, your Windows edition, and the
contents of the **Logs** page. If it is a setup failure, the wizard's install log
is the useful part.
