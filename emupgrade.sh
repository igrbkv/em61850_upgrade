#!/bin/sh
# Пакетное обновление:
# 1. Развертывается архив.
# 2. Устанавливаются пакеты.
# 3. Удаляются архив и архивы пакетов(подпапки в /usr/portage/packages?)

EMCONF_DIR=/etc/opt/EM61850
SYSUPGRADE=${EMCONF_DIR}/sysupgrade.conf
MAKE_CONF=/etc/portage/make.conf
USB_DEV="/dev/sdb1"
DISTR_TEMPLATE="em61850-*.tar.bz2"
SAVE_CONFIG="$2"
PORTAGE=/usr/portage/packages
MOUNT_POINT=/mnt/upgrade

packages=

clean() {
    # удалить дистрибутив
    rm ${DISTR_PATH} 2>/dev/null
    # удалить пакеты
    rm -r $PORTAGE/* 2>/dev/null
    umount ${MOUNT_POINT} 2>/dev/null
}

die() {
    [ -z "${1}"] || logger "${1}"
    clean
    exit 0
}

install_tar_ball() {
    tar -xjf "$DISTR_PATH"
}

# Массив из:
# /usr/portage/packages/<dir>/<package>-<version>.tbz2
make_packages_list() {
    packages=($(find $PORTAGE -type f -name "*.tbz2")) 
}

pkg_upgrade() {
    export QMERGE=1
    make_packages_list
    for pkg in ${packages[*]}
    do
        pkg=(${pkg//\// })
        pkg=${pkg[-1]}
        pkg=${pkg//.tbz2/}
        qmerge -KyO $pkg >/dev/null 2>&1
    done
}

sync_board_upgrade() {
}

adc_board_upgrade() {
}

# usb устройство подключено
[ -b ${USB_DEV} ] || die ""
mkdir -p ${MOUNT_POINT}
mount ${USB_DEV} ${MOUNT_POINT} >/dev/null 2>&1
DISTR_PATH=$(ls "${USB_DEV}/${DISTR_TEMPLATE}" >/dev/null 2>&1)
[ "${DISTR_PATH}" ] || die "Файл дистрибутива не найден"
# проверка дистрибутива
bzip2 --test $DISTR_PATH 2>/dev/null || die "Файл дистрибутива поврежден"
logger "Запуск обновления ..."
cd ${PORTAGE}
install_tar_ball || die "Ошибка распаковки архива"
pkg_upgrade
sync_board_upgrade
adc_board_upgrade

logger "Установка обновления прошла успешно."
clean
sync

