SUMMARY = "Logs the Raspberry Pi under-voltage flag (systemd service)"
DESCRIPTION = "Reads in0_lcrit_alarm of the rpi_volt hwmon device and logs changes to the journal. Optional poweroff, off by default."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = " \
    file://undervolt-watch.sh \
    file://undervolt-watch.service \
    file://undervolt-watch.default \
"
S = "${WORKDIR}"

inherit systemd

SYSTEMD_SERVICE:${PN} = "undervolt-watch.service"
SYSTEMD_AUTO_ENABLE = "enable"

RDEPENDS:${PN} = "kernel-module-raspberrypi-hwmon"

do_install() {
    install -d ${D}${libexecdir}
    install -m 0755 ${WORKDIR}/undervolt-watch.sh ${D}${libexecdir}/undervolt-watch

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/undervolt-watch.service ${D}${systemd_system_unitdir}/

    install -d ${D}${sysconfdir}/default
    install -m 0644 ${WORKDIR}/undervolt-watch.default ${D}${sysconfdir}/default/undervolt-watch
}

CONFFILES:${PN} = "${sysconfdir}/default/undervolt-watch"
