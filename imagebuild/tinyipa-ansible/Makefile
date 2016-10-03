.PHONY: all dependencies rebuild devstack clean
all: dependencies rebuild

dependencies:
	./install-deps.sh
rebuild:
	./rebuild-tinyipa.sh
devstack: dependencies
	./prepare-devstack.sh
clean:
	sudo -v
	sudo rm -rf rebuild
	rm -f *.initramfs
	rm -f *.gz
	rm -rf build_files/cache/*
