#!/bin/sh

# Программа обновления
# 1. Проверяет, что существует файл обновления
# 2. Расшифровывает его в папку /tmp, удаляет файл обновления
# 3. Тестирует архив, если ошибка удаляет
# 4. Разархивирует архив
# 5. Переписывает файлы конфигурации и др.

USB_DISTR_TEMPLATE="em61850-*.img"
EMCONF_DIR=/etc/opt/EM61850
TMP_UPGRADE_DIR=/tmp
DISTR=distr.tar.bz2
ENC_DISTR_PATH=/${DISTR}.cpt
DEC_DISTR_PATH=${TMP_UPGRADE_DIR}/distr.tar.bz2
TAG="emupgrade"
KEY=_em61850_
USB_MNT=/mnt/usbstick
DST_MNT=/mnt/upgrade
SYNC_FIRMWARE_DIR=${DST_MNT}${EMCONF_DIR}/sync_firmware
SYNC_VERSION_PATH=${DST_MNT}${EMCONF_DIR}/sync_board_version
ADC_FIRMWARE_DIR=${DST_MNT}${EMCONF_DIR}/adc_firmware

adc_ip=
sync_ip=

DEBUG=1

clean() {
    # удалить дистрибутив
    rm ${DISTR_PATH} 2>/dev/null
    # размонтировать boot
    unmount_boot_and_new_root
}

em_logger() {
    [ "${1}" ] && logger -t ${TAG} "${1}" 
	[ "${1}" -a ${DEBUG} -gt 1 ] && echo "${1}"
}

die() {
    if [ -z "${1}" ]; then
		[ ${DEBUG} -gt 0 ] && echo "${FUNCNAME[1]}() failed!"
	else
		em_logger "${1}"
	fi
    clean
	popd
    exit 0
}

ip_addresses() {
	local base_ip=($(ifconfig br0 | grep "inet "))
	base_ip=${base_ip[1]}
	arr=(${base_ip//./ })
	sufx=$((${arr[3]}+1))
	adc_ip="${arr[0]}.${arr[1]}.${arr[2]}.${sufx}"
	sufx=$((${arr[3]}+2))
	sync_ip="${arr[0]}.${arr[1]}.${arr[2]}.${sufx}"
}

test_tar_ball() {
	bzip2 --test "${DEC_DISTR_PATH}" 2>/dev/null || die "Файл дистрибутива поврежден"
}

test_version() {
	local ver_path=${EMCONF_DIR:1}/VERSION
    tar -xjf "${DEC_DISTR_PATH}" ${ver_path} || die "Ошибка распаковки дистрибутива"
	local new_ver=$(<${ver_path})
	local old_ver=$(<${EMCONF_DIR}/VERSION)
	[ "${new_ver}" == "${old_ver}" ] && die "Ошибка. Переустановка той же версии дистрибутива с usb-диска запрещена."
}

mountpoints() {
	src_dev=$(findmnt -n -o SOURCE /) || die
	if [ "${src_dev: -1}" == "3" ]; then
		sufx="4"
	else
		sufx="3"
	fi
	dst_dev="${src_dev:1:-1}${sufx}"
}

mount_boot_and_new_root() {
	mount ${dst_dev} ${DST_MNT} ||  die 
	mount /boot ||  die 
}

fmt_dst() {
	mkfs.ext4 "${DST_MNT}" || die
}

unpack() {
    tar -C ${DST_MNT} -xjf "${DEC_DISTR_PATH}" || die "Ошибка распаковки дистрибутива"
}

sync_board_upgrade() {
	local brd_ver=$(<${EMCONF_DIR}/sync_board_version)
	local fw_dir="${EMCONF_DIR}/sync_firmware/${brd_ver}"
	local old_fw=$(ls ${fw_dir} 2>/dev/null)
	local new_fw=$(ls "${DST_MNT}${fw_dir}" 2>/dev/null)

	if [ "${old_fw}" == "${new_fw}" ]; then
		return
	if [ -e "${new_fw}" ]; then
		em_logger "Прошивка платы синхронизации ..."
		emsyncupgrade.py "${new_fw}" || die "Ошибка. Не удалось перепрошить плату синхронизации"
	fi
}

adc_board_upgrade() {
	local fw_dir="${EMCONF_DIR}/adc_firmware"
	local old_fw=$(ls ${fw_dir} 2>/dev/null)
	local new_fw=$(ls "${DST_MNT}${fw_dir}" 2>/dev/null)
	if [ "${old_fw}" == "${new_fw}" ]; then
		return
	if [ -e "${new_fw}" ]; then
		em_logger "Прошивка платы АЦП ..."
		# перевести плату синронизации в режим 
		# работы от входного PPS, чтобы не мешала
		emsyncupgrade || die "Ошибка. Не установить режим работы платы синхронизации"
		emadcupgrade.py "${new_fw}" || die "Ошибка. Не удалось перепрошить плату АЦП"
	fi
}

change_boot()
{
    echo "Настройка загрузчика ..."
    umount /sys/firmware/efi/efivars &>/dev/null || die
    mount -t efivarfs -o rw,relatime efivarfs /sys/firmware/efi/efivars &>/dev/null || die

	boot_label=UEFI:EM61850

	# delete previous boot entrys
	boot_nums=$(efibootmgr | grep $boot_label | sed -e "s/$boot_label//")
	for boot_num in $boot_nums; do
		boot_num=${boot_num:4:4}
		efibootmgr -b $boot_num -B &>/dev/null || die "Ошибка очистки меню загрузки"
	done

    efibootmgr -c -d /dev/sda -l '\bzImage' -L $boot_label -u "root=${dst_dev} ro" &>/dev/null || die "Ошибка добавления в меню загрузки"
}

copy_configs() {
    sed -i "s#/dev/sdaX#${dst_dev}#" ${DST_MNT}/etc/fstab  || die "Ошибка записи точки монтирования корневого директория (файл /etc/fstab)"           
	cp ${EMCONF_DIR}/emd.conf ${EMCONF_DIR}/sync_board_version ${DST_MNT}${EMCONF_DIR}/

	mkdir -p /var/log/{emd,emupgrade}
	cp /var/log/emd/current ${DST_MNT}/var/log/emd/current
	cp -R /var/log/emupgrade/ ${DST_MNT}/var/log/
}

unmount_boot_and_new_root() {
    umount /boot 2>/dev/null
    umount ${dst_dev} 2>/dev/null
}

pushd

# обновление с usb?
usb_distr=($(ls "${USB_MNT}/${USB_DISTR_TEMPLATE}" 2>/dev/null))
[ "${usb_distr[0]}" ] && cp -f "${USB_MNT}/${usb_distr[0]}" ${ENC_DISTR_PATH} 2>/dev/null

[ -e ${ENC_DISTR_PATH} ] || die

em_logger "Обновление ПО..."
mv ${ENC_DISTR_PATH} ${TMP_UPGRADE_DIR}
cd ${TMP_UPGRADE_DIR}
ccdecrypt -K ${KEY} ${ENC_DISTR_PATH} || die "Ошибка расшифровки файла дистрибутива"
test_tar_ball
# чтобы не зацикливалась
[ "${usb_distr[0]}" ] && test_version
ip_addresses
mountpoints
mount
fmt_dst
unpack
sync_board_upgrade
adc_board_upgrade
change_boot
copy_configs
umount

reboot
