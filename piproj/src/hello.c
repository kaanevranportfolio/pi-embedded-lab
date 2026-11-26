#include <stdio.h>
#include <sys/utsname.h>

int main(void) {
    struct utsname u;
    if (uname(&u) != 0) {
        perror("uname");
        return 1;
    }
    printf("Hello, world! machine: %s (%s)\n", u.nodename, u.machine);
    return 0;
}
