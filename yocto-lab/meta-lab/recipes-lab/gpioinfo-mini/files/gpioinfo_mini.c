/* Lists all GPIO chips through the character-device interface (ioctl). */
#include <fcntl.h>
#include <linux/gpio.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(void) {
    char path[32];
    int found = 0;

    for (int i = 0; i < 16; i++) {
        snprintf(path, sizeof path, "/dev/gpiochip%d", i);
        int fd = open(path, O_RDONLY);
        if (fd < 0)
            continue;

        struct gpiochip_info info;
        memset(&info, 0, sizeof info);
        if (ioctl(fd, GPIO_GET_CHIPINFO_IOCTL, &info) == 0) {
            printf("%s: name=%s label=%s lines=%u\n",
                   path, info.name, info.label, info.lines);
            found++;
        } else {
            perror(path);
        }
        close(fd);
    }
    if (!found) {
        fprintf(stderr, "Keine GPIO-Chips gefunden.\n");
        return 1;
    }
    return 0;
}
