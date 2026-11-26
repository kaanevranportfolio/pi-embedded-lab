// SPI loopback test: connect MOSI (pin 19) to MISO (pin 21) with one jumper.
// Sends a known pattern, reads back what arrives on MISO, compares.
// Usage: spi_loopback [/dev/spidev0.0] [speed_hz]
#include <errno.h>
#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define LEN 16

int main(int argc, char **argv)
{
    const char *dev = argc > 1 ? argv[1] : "/dev/spidev0.0";
    uint32_t speed = argc > 2 ? (uint32_t)strtoul(argv[2], NULL, 10) : 1000000;
    uint8_t mode = SPI_MODE_0, bits = 8;

    int fd = open(dev, O_RDWR);
    if (fd < 0) {
        fprintf(stderr, "open %s: %s\n", dev, strerror(errno));
        return 2;
    }
    if (ioctl(fd, SPI_IOC_WR_MODE, &mode) < 0 ||
        ioctl(fd, SPI_IOC_WR_BITS_PER_WORD, &bits) < 0 ||
        ioctl(fd, SPI_IOC_WR_MAX_SPEED_HZ, &speed) < 0) {
        perror("spi config");
        return 2;
    }

    uint8_t tx[LEN], rx[LEN];
    for (int i = 0; i < LEN; i++)
        tx[i] = (uint8_t)(0xA5 ^ (i * 17));
    memset(rx, 0, sizeof rx);

    struct spi_ioc_transfer t = {
        .tx_buf = (unsigned long)tx,
        .rx_buf = (unsigned long)rx,
        .len = LEN,
        .speed_hz = speed,
        .bits_per_word = bits,
    };
    if (ioctl(fd, SPI_IOC_MESSAGE(1), &t) < 0) {
        perror("SPI_IOC_MESSAGE");
        return 2;
    }

    printf("%s  mode0  %u Hz\nTX:", dev, speed);
    for (int i = 0; i < LEN; i++) printf(" %02x", tx[i]);
    printf("\nRX:");
    for (int i = 0; i < LEN; i++) printf(" %02x", rx[i]);
    printf("\n");

    int ok = memcmp(tx, rx, LEN) == 0;
    printf(ok ? "RESULT: PASS (RX == TX)\n"
              : "RESULT: FAIL (RX != TX, check the jumper on pin 19-21)\n");
    close(fd);
    return ok ? 0 : 1;
}
