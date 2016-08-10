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
SYNC_FIRMWARE_TEMPLATE="em_sync_firmware_*.bin"
ADC_FIRMWARE_TEMPLATE="em_adc_firmware_*.bin"
SAVE_CONFIG="$2"
PORTAGE=/usr/portage/packages
MOUNT_POINT=/mnt/upgrade
TAG="emupgrade"
DEBUG=2

packages=

clean() {
    # удалить дистрибутив
    rm ${DISTR_PATH} 2>/dev/null
    # удалить пакеты
    rm -r $PORTAGE/* 2>/dev/null
    umount ${MOUNT_POINT} 2>/dev/null
}

em_logger() {
    [ "${1}" ] && logger -t ${TAG} "${1}" 
	[ "${1}" -a ${DEBUG} -gt 1 ] && echo "${1}"
}

die() {
    [ -z "${1}" ] || em_logger "${1}"
    clean
    exit 0
}

install_tar_ball() {
    tar -xjf "${MOUNT_POINT}/${DISTR_PATH}"
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
		if [ ${#pkg[@]} -gt 1 ]; then
			fld=${pkg[-2]}
			pkg=${pkg[-1]}
			pkg=${pkg//.tbz2/}
			qmerge -KyO "$fld/$pkg" >/dev/null 2>&1
		fi
    done
}

sync_board_upgrade() {
	sync_file=$(ls ${SYNC_FIRMWARE_TEMPLATE} 2>/dev/null)
	if [ -e "${sync_file}" ]; then
		[ ${DEBUG} -gt 0 ] && em_logger "sync board upgrade with ${sync_file} ..."
		/usr/bin/emsyncupgrade.py "${PORTAGE}/${sync_file}"
		[ $? -lt 0 ] && em_logger "sync board upgrade failed!"
	fi
}

adc_board_upgrade() {
	adc_file=$(ls ${ADC_FIRMWARE_TEMPLATE} 2>/dev/null)
	if [ -e "${adc_file}" ]; then
		[ ${DEBUG} -gt 0 ] && em_logger "adc board upgrade with ${adc_file} ..."
		/usr/bin/emadcupgrade.py "${PORTAGE}/${adc_file}"
		[ $? -lt 0 ] && em_logger "adc board upgrade failed!"
	fi
}

[ ${DEBUG} -gt 0 ] && em_logger "upgrade started"
# usb устройство подключено
[ -b ${USB_DEV} ] || die ""
mkdir -p ${MOUNT_POINT}
mount ${USB_DEV} ${MOUNT_POINT} >/dev/null 2>&1
cd ${MOUNT_POINT}
DISTR_PATH=$(ls ${DISTR_TEMPLATE} 2>/dev/null)
[ -e ${DISTR_PATH} ] || die "Файл дистрибутива не найден"
# проверка дистрибутива
bzip2 --test "${DISTR_PATH}" 2>/dev/null || die "Файл дистрибутива ${DISTR_PATH} поврежден"
em_logger "Запуск обновления ..."
cd ${PORTAGE}
install_tar_ball || die "Ошибка распаковки архива ${DISTR_PATH}"
pkg_upgrade
em_logger $(echo $PWD)
sync_board_upgrade
adc_board_upgrade

sync
die "Установка обновления прошла успешно."
