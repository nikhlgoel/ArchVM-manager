## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## Why

<!-- The reasoning. What was wrong with the previous behaviour? -->

## Checklist

- [ ] `python -m pyflakes app/archvm/*.py app/*.py app/tools/*.py manager/*.py` is silent
- [ ] `python -m compileall -q app manager` is silent
- [ ] I started the app and clicked through the pages this touches
- [ ] Any new interactive widget has an accessible name
- [ ] Files in `seed/` still have LF line endings
- [ ] Screenshot attached (for anything visual)
