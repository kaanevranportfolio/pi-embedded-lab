# Verified results

Raspberry Pi 3 Model B, wired network, 5 V / 2 A adapter, November 2026.

## Yocto systemd image (with camera modules)
- Boots to `systemctl is-system-running` = `running`, no failed units. Reaches SSH about one minute after power-on.
- `undervolt-watch.service` is enabled and active. Journal: watching `rpi_volt` (`in0_lcrit_alarm`) every 5 s, power-off on under-voltage disabled by default, voltage normal (flag 0). Only the normal state was seen on the hardware; a real under-voltage event was not provoked.
- `/sys/class/hwmon`: `cpu_thermal` and `rpi_volt`.
- `hello` and `gpioinfo-mini` run; `gpioinfo-mini` lists `gpiochip0` (pinctrl-bcm2835, 54 lines), `gpiochip1`, `gpiochip2`.
- USB camera (Logitech C270): detected through `uvcvideo`, `/dev/video0`. Captured MJPG 640x480 at about 27 fps with `v4l2-ctl`. The first frames are almost black until auto exposure settles, so skip the first 40 frames.
- Root partition: 175.8 MB, 86.7 MB used.

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
