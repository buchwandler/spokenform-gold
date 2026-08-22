# Scripts

Operational helper scripts for spokenform-gold production. None of these are
part of the core Python package — they are standalone tools meant to be run
directly.

---

## setup-source-cache.py

Bootstrap the external source cache on a new machine.

The three upstream repositories (Async TN, PolyNorm, Proteno) are **not**
committed to Git. This script clones them at the exact revisions pinned in
[`sources/manifest.json`](../sources/manifest.json) and verifies that the
expected upstream files are present.

### Quick start

```bash
# From the repository root:
python scripts/setup-source-cache.py
```

This creates two sibling directories next to your checkout:

```
spokenform-gold/                  ← your Git checkout
spokenform-gold-source-cache/     ← cloned upstream repos (disposable, not in Git)
spokenform-gold-work/             ← production work directory (disposable, not in Git)
```

### After the script finishes

Export the environment variables that the production tooling expects:

```bash
export SPOKENFORM_GOLD_SOURCE_CACHE="$(cd ../spokenform-gold-source-cache && pwd)"
export SPOKENFORM_GOLD_WORK="$(cd ../spokenform-gold-work && pwd)"
```

Add these to your shell profile (`.bashrc`, `.zshrc`, etc.) if you work in
this repository regularly.

### Options

| Flag | Default | Description |
|---|---|---|
| `--cache-root PATH` | `../spokenform-gold-source-cache` | Where to clone upstream repos |
| `--work-root PATH` | `../spokenform-gold-work` | Disposable work directory |
| `--verify-only` | — | Only verify existing checkouts; don't clone or fetch |
| `--skip-work-dir` | — | Don't create the work directory |

### Verify an existing cache

```bash
python scripts/setup-source-cache.py --verify-only
```

### Requirements

- git ≥ 2.20
- Python ≥ 3.10 (standard library only, no pip install needed)

### Notes

- **Async TN** is hosted on Hugging Face Spaces. If the Space is private you
  may need to run `huggingface-cli login` first.
- **PolyNorm** and **Proteno** are public GitHub repositories.
- The script uses shallow clones where possible and falls back to a full clone
  if the host doesn't support shallow clone by arbitrary SHA.
- Re-run the script at any time to fetch and checkout the pinned revision
  (useful after a manifest re-pin).
