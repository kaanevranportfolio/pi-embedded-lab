# Verified results

Raspberry Pi 3 Model B, wired network, 5 V / 2 A adapter, November 2026.

## Yocto systemd image (with camera modules)
- Boots to `systemctl is-system-running` = `running`, no failed units. Reaches SSH about one minute after power-on.
- `undervolt-watch.service` is enabled and active. Journal: watching `rpi_volt` (`in0_lcrit_alarm`) every 5 s, power-off on under-voltage disabled by default, voltage normal (flag 0). Only the normal state was seen on the hardware; a real under-voltage event was not provoked.
- `/sys/class/hwmon`: `cpu_thermal` and `rpi_volt`.
- `hello` and `gpioinfo-mini` run; `gpioinfo-mini` lists `gpiochip0` (pinctrl-bcm2835, 54 lines), `gpiochip1`, `gpiochip2`.
- USB camera (Logitech C270): detected through `uvcvideo`, `/dev/video0`. Captured MJPG 640x480 at about 27 fps with `v4l2-ctl`. The first frames are almost black until auto exposure settles, so skip the first 40 frames.
- Root partition: 175.8 MB, 86.7 MB used.

## Camera streaming and telemetry (640x480 MJPG, 2 minutes per run)
| Run | Temperature | Under-voltage flag | Load | Ethernet tx |
|---|---|---|---|---|
| idle, camera plugged in | 34.3 to 37.5 C | 0 | 0.01 | about 0 |
| stream, 15 fps | 38.6 to 40.7 C | 0 | 0.00 | 421 kB/s |
| stream, 30 fps | 41.3 to 42.9 C | 0 | 0.05 | 912 kB/s |

- The first stream ran at 15 fps because the C270 control `exposure_dynamic_framerate` lowers the frame rate in dim light. Switching it off gave 30.0 fps on average (minimum 27).
- The temperature rose from run to run because the Pi was still warming up after boot, so the heat caused by the camera could not be separated. The Pi has no current or power sensor; the under-voltage flag only says that the supply held up, not how many watts it delivered.
- YUYV 640x480 at 30 fps would be about 147 Mbit/s raw, more than the 100 Mbit/s Ethernet of the Pi 3 (calculated, not measured).

## Belt counter (`belt_counter` plus `belt_ui.py`)
- Self-test with synthetic frames (`belt_counter --selftest`): noise only gives 0, three objects moving left give left=3, one moving right gives right=1, exposure drift from 235 to 175 does not disturb a count, a large dark band (sheet edge) is ignored. All pass on the PC and on the Pi.
- On the Pi with the camera: 30 messages per second, about 6.4 ms of processing per frame, about 20 % of one core, about 10 % of the whole CPU (with 15 images per second sent), 46.6 C, under-voltage flag 0. Stop leaves no process behind.
- One real run (see the clip in the README): three objects counted, no extra count. A large shadowed area of the sheet was tracked as an object but never crossed the line.
- Not tested: repeatability, speed limits, the opposite direction with real objects, objects very close together.

## SPI loopback (earlier Yocto image with SysVinit)
- One jumper, MOSI (pin 19) to MISO (pin 21).
- `spi_loopback` PASS at 0.5, 1, 4 and 16 MHz on `/dev/spidev0.0` and at 1 MHz on `/dev/spidev0.1`.
- Negative control: with the jumper removed, MISO read all zeros and the program printed FAIL (exit 1) at 1 and 4 MHz, so the PASS was not vacuous.
- A loopback proves the controller, driver, device node and the two pins. It says nothing about a real SPI device (mode, chip-select polarity, level shifting).
- Not repeated on the systemd image.

## Serial console
- 3.3 V FTDI adapter on the Pi header: GND pin 6, Pi TX pin 8 to adapter RX, Pi RX pin 10 to adapter TX, adapter VCC not connected.

## Not verified
- Behaviour of `undervolt-watch` during a real under-voltage event.
- Clock: there is no RTC. Journal timestamps right after boot can be far off, and I did not check which service sets the time.
- Buildroot image feature parity with the Yocto image.
