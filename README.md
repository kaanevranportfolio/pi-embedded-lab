# pi-embedded-lab

Hands-on notes and code from building small Linux images for a Raspberry Pi 3 Model B, once with Yocto and once with Buildroot, and checking the hardware interfaces from userspace. Host: Ubuntu 24.04. The numbers below were measured on this setup; where something was not measured, it says so.

## What is here

| Path | Contents |
|---|---|
| `yocto-lab/meta-lab/` | A small Yocto layer (scarthgap): `hello`, `gpioinfo-mini`, `undervolt-watch` (systemd service that logs the Pi under-voltage flag) and a class that installs an SSH public key |
| `yocto-lab/local.conf.sample` | The `local.conf` lines this lab adds (systemd, I2C/SPI, hwmon, USB camera) |
| `buildroot-lab/` | Buildroot config fragment, firmware `config.txt`, rootfs overlay |
| `piproj/` | CMake aarch64 cross-compile project: `hello`, `gpioinfo_mini`, `spi_loopback` |
| `docs/` | [Buildroot vs Yocto](docs/buildroot-vs-yocto.md), [verified results](docs/results.md), [workspace layout](docs/workspace-layout.md) |

Not included: poky, meta-openembedded, meta-raspberrypi (clone them, see below), build output, downloads and images.

## Build the Yocto image

```bash
mkdir yocto-lab && cd yocto-lab
git clone -b scarthgap https://git.yoctoproject.org/poky
git clone -b scarthgap https://git.openembedded.org/meta-openembedded
git clone -b scarthgap https://git.yoctoproject.org/meta-raspberrypi
# put this repo's yocto-lab/meta-lab next to them
# last tested commits: poky 6b7c106, meta-openembedded 2db6aec, meta-raspberrypi 018d444
source poky/oe-init-build-env build
# add the layers to conf/bblayers.conf (meta-oe, meta-python, meta-networking, meta-raspberrypi, meta-lab)
# append the lines from local.conf.sample to conf/local.conf and set LAB_SSH_PUBKEY
bitbake core-image-minimal
```

`LAB_SSH_PUBKEY` must be set in your own `local.conf`; the class refuses to build without it, and no key is stored in this repo.

## Build the Buildroot image

```bash
# Buildroot 2026.02.3 unpacked next to this repo's buildroot-lab/ folder
LAB=$PWD/buildroot-lab; OUT=$LAB/out; BR=<path to buildroot-2026.02.3>
make -C $BR O=$OUT raspberrypi3_64_defconfig
sed "s|@LAB@|$LAB|g" $LAB/lab.fragment.in >> $OUT/.config
# put your public key in $LAB/overlay/root/.ssh/authorized_keys (mode 600), see authorized_keys.example
make -C $BR O=$OUT olddefconfig && make -C $BR O=$OUT -j$(nproc)
# result: $OUT/images/sdcard.img
```

## Cross-compile the test programs

```bash
cmake -S piproj -B piproj/build -DCMAKE_TOOLCHAIN_FILE=piproj/cmake/aarch64-linux-gnu.cmake
cmake --build piproj/build
```

The `deploy` target uses `scp`. The Yocto and Buildroot images here use Dropbear, which has no `scp`; copy with `ssh root@<ip> 'cat > /tmp/prog' < prog` instead.

## Safety habits used in this lab

- Before writing an SD card: check the device with `lsblk`, then write, then compare with `cmp`. A returned prompt is not proof of a good write.
- Public SSH key only, no passwords on the target.
- Security settings are measured first and only loosened when really needed.

## License

No license has been chosen yet.
