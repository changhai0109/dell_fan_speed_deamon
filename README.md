# r720_fan_speed_deamon
Just a python script which can run as deamon and controls your ~~dell r720 server fan speed~~ for now any dell servers with idrac, or c6220 (maybe other c-series modular), in order to balance temperature and noise.
Please modify the ~~previous few lines~~ json files and systemd service module to fit your situation. Use ``sudo make install`` can install all files except service module, and you need to add service module by yourself.
