# The GugusseGUI 2.0 software for the Gugusse Roller

Author: Denis-Carl Robidoux

The Gugusse Roller is a DIY project to make a machine that can
transfer films of all sizes between 8mm (included) and 35mm
(included) to digital. It comprises of:

- 3D printed parts
- A Raspberry Pi 4B (with 4GB)
- A Raspberry Pi HQ camera
- An Adafruit Metro Mini 5V 16Mhz (it's an Arduino)
- 3 stepper motors (bipolar 12V Nema 17, 34mm height)
- A longboard wheel
- Various small electronic parts.
- A reliable 5V and 12V power supply
- Led strips

You can find all the instructions, the files to make your 3D
printed parts and the one to make the PCB for free, no strings
attached, at www.deniscarl.com

## DEPENDENCIES

Raspbian Bulleyes. Use the 64bits version if you want support

The resulting machine is fully functional and stable but it
is still evolving. You can watch or participate this evolution at
https://www.facebook.com/Gugusse-Roller-2216783521714775/

The objectives of the software is to:

- Drive the 3 stepper motors
- Monitor the camera's output
- Adjust the various camera settings
- read the 3 discrete inputs:
    1. film hole detector
    2. left arm aligned in middle
    3. right arm aligned in middle
- capture each frame, save it as jpeg (or better as a 12bits raw DNG)
- transfer the file to a ftp server

## Getting started

Download the software:

```bash
git clone 
```

Install OpenCV if you want to use the focus peaking feature:

```bash
pip3 install opencv-python-headless
```

## Development

Install NPM and nodemon for reloading the application on file changes. You only need to do this once.

```bash
sudo apt update
sudo apt install npm -y
sudo npm install -g nodemon
```

Run the script with nodemon for hot-reloading.

```bash
nodemon --exec python3 GugusseGUI.py --watch .
```

## Estabilización de imagen

Luego de digitalizar se debe estabilizar la imagen y sincronizar el sonido (si tiene). En este video se puede ver el proceso completo: https://www.youtube.com/watch?v=5_hXPkGXYCw

### Mostrar solo las perforaciones para estabilizar

1. En ventana de Color:
   1. Decode using: **Clip**
   2. Activar: **Highlight Recovery**
   3. Shadows: **-100**
   4. Lift: **-100**
   5. Contrast: **100**
   6. Luego ajustar "Exposure" hasta que las perforaciones sean lo más brillante y la imagen completamente negra o lo más oscura posible.
