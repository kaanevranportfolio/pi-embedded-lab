# Workspace layout

The lab lives under one fixed root, `$EMBEDDED_LAB` (default `~/embedded-lab`). Builds hold absolute paths and are tens of GB, so they are created where they will stay.

| Folder | What it is | Resume with |
|---|---|---|
| `yocto-lab/` | poky, meta-openembedded, meta-raspberrypi (cloned, not in this repo), own layer `meta-lab`, `build/` | `source poky/oe-init-build-env build && bitbake core-image-minimal` |
| `buildroot-lab/` | Buildroot 2026.02.3 (downloaded), `out/` build dir, overlay, board config | `make -C src/buildroot-2026.02.3 O=$PWD/out` |
| `piproj/` | CMake cross-compile project (aarch64) | `cmake --build build --target deploy` |
| `docs/` | write-ups | |
| `cache/` | shared Yocto `downloads` and `sstate-cache` | |

Notes
- Absolute paths: Yocto's `bblayers.conf`, Buildroot's `.config` and the CMake cache record absolute paths. After moving a tree, rewrite the old prefix and discard `tmp/` (Yocto) and the CMake `build/`.
- BitBake on Ubuntu 24.04 built here without changing `kernel.apparmor_restrict_unprivileged_userns` (it stayed at 1). An older note claiming that a sysctl was required after every reboot was wrong.
- Moving to an external SSD later: same layout, `export EMBEDDED_LAB=/media/$USER/<label>/embedded-lab` (ext4, USB 3.x).
