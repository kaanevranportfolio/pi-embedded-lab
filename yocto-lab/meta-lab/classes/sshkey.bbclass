# Installs one public SSH key for root into the image.
# Set the key in local.conf (never commit it):
#   LAB_SSH_PUBKEY = "ssh-ed25519 AAAA... comment"
LAB_SSH_PUBKEY ?= ""
ROOTFS_POSTPROCESS_COMMAND += "install_ssh_key;"

install_ssh_key() {
    if [ -z "${LAB_SSH_PUBKEY}" ]; then
        bbfatal "LAB_SSH_PUBKEY is empty: set it in local.conf (see local.conf.sample)"
    fi
    install -d -m 700 ${IMAGE_ROOTFS}/home/root/.ssh
    echo "${LAB_SSH_PUBKEY}" > ${IMAGE_ROOTFS}/home/root/.ssh/authorized_keys
    chmod 600 ${IMAGE_ROOTFS}/home/root/.ssh/authorized_keys
}
