#!/bin/sh
# Сборка обновления
# 1. Переходит в /usr/portage/packages.

# 2. Формирует список файлов:
# Packages
# <dir>/*.tbz2
# em_sync_firmware*.bin
# em_adc_firmware*.bin

# 3. Создает архив в em61850-<номер_версии>.tar.bz2
# <номер версии> находится в /home/igor/workspace/EM61850/version

if (( EUID != 0 )); then
    echo "You must be root to do this." 1>&2
    exit 1
fi
VERSION_PATH=/home/igor/workspace/EM61850/emupgrade/version
PACKAGES_DIR=/usr/portage/packages

get_version() {
    local v=($(<$VERSION_PATH))
    v=(${v//./ })
    VERSION="${v[0]}.${v[1]}.${v[2]}"
}    

create_archive() {
    DISTR="em61850-${VERSION}"
	cd ${PACKAGES_DIR}
	echo "Upgrade of existing packages"
	LIST_PATH="list-${VERSION}.txt"
	echo -e "Packages\n" > $LIST_PATH
	packages=$(find . -type f -name "*.tbz2")
	echo -e "${packages// /\n}" >> $LIST_PATH
	packages=$(find . -type f -name "em_*.bin")
	echo -e "${packages// /\n}" >> $LIST_PATH
	tar -cjf ${DISTR}.tar.bz2 -T $LIST_PATH
	md5sum ${DISTR}.tar.bz2 > ${DISTR}.md5sums
}

get_version
create_archive
