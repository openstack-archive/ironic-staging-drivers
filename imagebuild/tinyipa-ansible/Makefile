.PHONY: all dependencies rebuild clean
all: dependencies rebuild

dependencies:
	./install-deps.sh
rebuild:
	./rebuild-tinyipa.sh
clean:
	sudo -v
	sudo rm -rf rebuild
	rm -f *.initramfs
	rm -f *.gz
	rm -rf build_files/cache/*
