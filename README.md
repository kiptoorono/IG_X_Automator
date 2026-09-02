# IG Automator

Windows automation tools for collecting and vetting Instagram reel leads, with
Twitter tooling included in the `Twitter/` folder.

## Repository name

Recommended name: `ig-automator`.

Other clear options:

- `social-media-lead-automator`
- `reels-lead-automator`

## Build

Run `./build_exe.ps1` in PowerShell. The portable release is written to
`dist/IG_Automator_windows/` and contains `IG_Automator.exe` plus the bundled
Android platform tools. The platform tools are tracked once in the root
`platform-tools/` directory; the copied build output is ignored.

The executable is tracked with Git LFS because it is larger than GitHub's
100 MB regular Git file limit.