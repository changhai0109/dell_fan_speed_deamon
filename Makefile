install:
	mkdir -p /etc/fan-control/
	cp ./*.json /etc/fan-control/
	cp control_fan /usr/local/bin
	chmod a+x /usr/local/bin/control_fan
