VERSION = 0.0.0
SOURCES = emupgrade.sh

COMMIT := $(shell git log -n 1 --pretty=format:"%H")

all:

install:
	@mkdir -p ${DESTDIR}${PREFIX}/bin
	@cp -f ${SOURCES} ${DESTDIR}${PREFIX}/bin/
	@cd ${DESTDIR}${PREFIX}/bin/
	@chmod 755 ${SOURCES}

uninstall:
	@cd ${DESTDIR}${PREFIX}/bin/
	$(RM) ${SOURCES}


#dist:
#       git commit -a -m "emupgrade-$(VERSION)"
#       #       git tag -s -m -f "emupgrade-$(VERSION)" $(VERSION)
#       git archive --format=tar --prefix=emupgrade-$(VERSION)/ $(VERSION) | gzi
#       p -9 > emupgrade-$(VERSION).tar.gz
dist:
	git commit -a -C $(COMMIT) || echo "ignored git commit error"
	git archive --format=tar --prefix=emupgrade-$(VERSION)/ master | bzip2 > emupgrade-$(VERSION).tar.bz2

distclean:
	rm emupgrade-*.tar.bz2

.PHONY: all install uninstall dist distclean
