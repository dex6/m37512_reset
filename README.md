# m37512_reset


### 1. What This Is

This is simple python3 script which is hopefully able to read/write flash memory of M37512 MCU commonly used as a controller chip in some laptop batteries.


### 2. The Story

I've developed it while trying to re-cell my old battery (Lenovo T400, battery by LG) on my own and after discovering hard way that replacing the cells in not enough. The battery controller needs to be reset as well, and the M37512 which happened to sit in my battery pack happens to be quite tricky one.

After some hacking around, this is what I've ended up. The script is **NOT** able to reset the battery controller, despite project's name, sorry :) It's just reading and writing controller's flash memory. You may try to search for some distinctive values in the dump like Design Capacity or Last Full Capacity and change them, or just erase A/B blocks like some HOWTOs suggest.

However, in my case such simple attempts were not successful and I **did broke** my battery, by driving it to some "safe mode" and making it blow the fuse (see [1]). Not wanting to "fix" the problem by shorting the fuse with solder, I've given up and searched help from professional shop and have them fix the electronics for me for ~15$.

Since the project main goal was just *"my laptop having 3-4h of battery life again"*, this is where I've stopped it.


### 3. Usage

a) Are you sure you want to do this?

b) Really?

c) Okay, first please get familiar how laptop batteries work, google as much as possible about the M37512, search for other people's stories who tried similar deeds...

d) Analyze the script itself, it contains some information how to use it.

e) The script is intended to be run on RPi with python3 installed. I've used Arch Linux on RPi-1 model B+, but Raspbian and/or newer RPis should probably work as well. Please note that Raspberry's hardware I2C interface cannot handle clock-stretching feature extensively used by the battery controller, and thus using hardware I2C interface of RPi is not possible. I've ended up using Linux Kernel software I2C instead (i2c-gpio module).

f) The script requires the M37512 to run in "Boot Mode", it won't work with "Normal" mode. Therefore you will need to physically connect three pins of the M37512 together (see [2] section about Boot Mode). Soldering jumper wires there can be quite tricky given the pins size, but some of them may be connected to testpoints which makes this part easier. If possible, try to make that easy to disconnect-reconnect, since you may/will need to switch between "normal" and "boot" mode quite often. And as always, please be **extremely** careful not to short any other pins.

g) The script talks some undocumented proprietary SMBUS-based protocol to the M37512 running in Boot Mode. The protocol seems to be similar, but not identical, to procedures described in M37512 datasheet regarding the flash memory programming from the MCU itself. I imagine the protocol may be very firmware-dependent and thus the script may fail with your very M37512. My chip had been marked as "FC035" which is its LGC firmware version according to some resources. The script apparently worked for me, but unfortunately it doesn't mean it will work for you.


### 4. Project Status

Since I've reached my goal of having a working battery, this project is effectively an abandonware now. You may fork it, use as you like, or even take it over. Any contributions are still welcomed, but I may be sceptical to incorporate non-trivial changes, because I'm no longer able to run/test this software anyhow.


### 5. Disclaimer

As written in the licence: I'm not responsible for any damage this software or its clueless user can cause. Once again: **I DID BROKE MY BATTERY WITH IT.** Yet again: *YOU'RE ON YOUR OWN.*


### 6. References and Other Stuff That You May Find Interesting

[1] http://www.karosium.com/2016/09/the-weird-fuses-in-laptop-batteries.html (and related posts, and smbusb flasher tool)

[2] The M37512 datasheet

[3] Smart Battery System (SBS) standard (although not related to flashing itself, it's good to know how this thing operates in "normal" mode to analyze firmware image)

[4] Many blogs and forums posts you'll find with google (unfortunately not necessarily in English)

