#!/bin/bash

echo "==> Instalando dependencias Python..."
sudo apt update
sudo apt install -y \
    python3-pip \
    libegl1-mesa-dev \
    libgles2-mesa-dev \
    libxkbcommon-dev \
    python3-pyqt5.qtquick \
    mesa-utils \
    python3-opengl

echo "==> Instalando dependencias de Python..."
pip3 install --user -r requirements.txt

echo "==> Verificando soporte OpenGL..."
glxinfo | grep "OpenGL version"

echo "==> Listo. Ahora puedes ejecutar la aplicación con:"
echo "     python3 main.py"
