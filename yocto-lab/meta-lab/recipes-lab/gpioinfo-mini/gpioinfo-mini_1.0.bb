SUMMARY = "Minimal GPIO chip lister using the character device ioctl"
DESCRIPTION = "Lists /dev/gpiochipN with name, label and line count. No libgpiod needed."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://gpioinfo_mini.c"
S = "${WORKDIR}"

do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} gpioinfo_mini.c -o gpioinfo_mini
}

do_install() {
    install -d ${D}${bindir}
    install -m 0755 gpioinfo_mini ${D}${bindir}/gpioinfo_mini
}
