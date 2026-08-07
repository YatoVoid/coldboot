# Contributing

## Setup

```bash
git clone https://github.com/YatoVoid/coldboot.git
cd coldboot
python3 configure.py
./setup.sh          # setup.ps1 on Windows
```

`./setup.sh --check` (`.\setup.ps1 -Check` on Windows) verifies an install
without changing anything, use it after any change to `setup.sh`/`setup.ps1`
instead of re-running the full install each time.

## Before opening a PR

- Test the platform you're changing. If you touch `setup.sh`, that means at
  least one real Linux distro, not just reading the package manager
  detection and assuming it's right.
- Config handling matters here: `config.json` is user-owned and untracked,
  `config.example.json` supplies fallbacks. If you add a setting, add its
  default to `config.example.json`, don't just read it with no fallback.
- `source` blocks are read exactly as written, not merged with the default.
  If you're adding a new source type, give it its own defaults rather than
  assuming it inherits from `hackernews` or `rss`.
- If a change affects render time or disk/RAM use, mention the numbers you
  saw and what hardware you tested on.

## Reporting a bug

OS and Python version, what step it failed on (setup, a specific script like
`sources.py` or `vidbot.py`), and the actual error output.
