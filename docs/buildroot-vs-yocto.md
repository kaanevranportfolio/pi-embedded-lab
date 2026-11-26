# Buildroot vs Yocto on a Raspberry Pi 3: what I measured

Same board (Raspberry Pi 3 Model B, 64-bit), same host (Ubuntu 24.04), one small image each. The two images do **not** have the same feature set, so the sizes are a rough comparison, not a benchmark.

| | Buildroot 2026.02.3 | Yocto scarthgap 5.0 |
|---|---|---|
| Init | BusyBox init | systemd 255.22 |
| Image | `sdcard.img`, 159,384,064 bytes | `.wic.bz2`, 52,284,635 bytes compressed, 338,898,944 bytes unpacked |
| Root partition | ext2, 125,829,120 bytes (120 MiB) | ext4, about 187 MB, sized by the build |
| Extras in this build | i2c-tools, libgpiod tools, Dropbear | the same plus v4l-utils, UVC camera modules, own recipes, hwmon driver |
| Build directory | `out/` 4.7 GB (plus 704 MB source tree) | `build/` 25 GB (with `rm_work`) |
| Task count | not counted | 5,252 tasks for `core-image-minimal` |
| Incremental change | not measured | adding v4l-utils and the camera modules: 125 of 5,252 tasks re-ran, about 6 minutes |
| Full build time | "tens of minutes" on 12 cores, not timed precisely | not recorded |

## Things that behaved the same
- The kernel has the I2C/SPI drivers as modules, but nothing loads them, so `/dev/i2c-*` and `/dev/spidev*` were missing on first boot. Fix in Buildroot: a `modules-load.d` file in the overlay. Fix in Yocto: `kernel-module-*` packages plus `KERNEL_MODULE_AUTOLOAD`.
- Dropbear has no `scp` or `sftp-server`. Copy files with `ssh host 'cat > file' < file`.
- `/tmp` is a tmpfs on the Yocto image, so copied test binaries disappear on reboot.

## Things that differed
- Buildroot: one configuration (`defconfig` plus a small fragment and an overlay). Everything I changed fit in one fragment, one `config.txt` and one overlay folder.
- Yocto: changes go into `local.conf` and a layer with recipes. The first setup took more steps (layers, a class, package names), but adding a package later was a one-line change and a short rebuild.
- Yocto had no mDNS in this image, so the Pi was found by MAC address (`scripts/find_pi.sh` in the skill, not part of this repo).

## What this comparison does not show
Build times are not like-for-like (different caches, downloads, one machine). I did not measure boot time, RAM use or update workflows.
