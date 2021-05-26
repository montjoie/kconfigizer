# Kconfigizer in ncurses

Minimize or harden you config faster than light

## install
need kconfiglib, yaml and ncurses

## design
* Everything in line, faster view, no submenu
* highlight debug CONFIGs for easy removing
* highlight harden/security options
* custom highlight of needed options per defconfig (for preventing removing)

## Usage
./kconfigizer

./kconfigizer --arch arm

./kconfigizer --arch arm --defconfig multi_v7_defconfig

## Commands
* UP DOWN
* ESC to quit
* PAGE UP/DOWN
* y toogle =y
* n toogle =n
* r reset to default
* F5 filter only not "=n" configs
* search via / (next=',')
* s save result in config.out
* S save whole config in config.out
* o overwrite defconfig
