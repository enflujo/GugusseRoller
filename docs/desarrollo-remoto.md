# Desarrollo remoto de Gugusse Roller

La Raspberry Pi funciona como máquina de ejecución: controla la cámara, los
motores y la pantalla. El editor, el análisis de Python y las demás herramientas
pesadas deben correr en el computador de desarrollo.

La GUI siempre aparece en la pantalla HDMI de la Pi. No hace falta usar `ssh -X`
ni transmitir el escritorio por la red.

El escritorio de la Pi queda fijado en 1920×1080 a 60 Hz. El modo 4K a 30 Hz
cuadruplica el trabajo de composición y vuelve perceptiblemente más lento el
escritorio de una Pi 4, sin aportar una ventaja equivalente para los controles
de la aplicación.

Los servicios de impresión y ModemManager están desactivados porque esta Pi no
tiene impresoras ni módems. Bluetooth permanece activo para el mouse Satechi y
Avahi permanece activo para resolver `enflujo11.local`.

## 1. Configurar una llave SSH

En el computador de desarrollo:

```bash
ssh-keygen -t ed25519 -a 64 -f ~/.ssh/id_ed25519_gugusse
ssh-copy-id -i ~/.ssh/id_ed25519_gugusse.pub enflujo@enflujo11.local
ssh -i ~/.ssh/id_ed25519_gugusse enflujo@enflujo11.local
```

No se debe desactivar el acceso con contraseña hasta haber confirmado que la
llave funciona en una conexión nueva.

Añadir al archivo `~/.ssh/config` del computador:

```sshconfig
Host gugusse
    HostName enflujo11.local
    User enflujo
    IdentityFile ~/.ssh/id_ed25519_gugusse
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

`enflujo11.local` funciona dentro de la misma red gracias a Avahi. Desde otra
red se necesita una VPN o una dirección alcanzable; no se recomienda publicar
directamente el puerto 22 en Internet.

## 2. Controlar la aplicación

```bash
ssh gugusse
gugusse start
gugusse status
gugusse logs
gugusse follow
gugusse restart
gugusse stop
```

`start` y `restart` abren la ventana en la pantalla física de la Pi. `logs` y
`follow` permiten diagnosticar excepciones desde el computador remoto. La
aplicación también conserva sus logs de sesión en `logs/`.

`stop` y `restart` solicitan un cierre limpio: guardan ajustes pendientes,
detienen los hilos de captura, apagan las luces, detienen la cámara y deshabilitan
los motores antes de terminar el proceso.

El arranque automático está desactivado por seguridad, para que una edición con
errores no active inesperadamente cámara, luces o motores. Se puede habilitar
deliberadamente con `gugusse enable`.

## 3. Flujos de desarrollo

### Opción A: código local y sincronización (recomendada)

Clonar este repositorio en el computador y trabajar con cualquier editor. Para
enviar únicamente Python y recursos gráficos, sin sobrescribir la configuración
de hardware de la Pi:

```bash
./workstationScripts/deploy-dev
```

El script sincroniza los cambios, reinicia la GUI y muestra su estado. Para ver
el arranque en tiempo real, usar otra terminal:

```bash
ssh gugusse /home/enflujo/.local/bin/gugusse follow
```

### Opción B: VS Code Remote SSH

Instalar VS Code y la extensión Remote SSH únicamente en el computador. Abrir:

```text
Remote-SSH: Connect to Host... -> gugusse
```

Luego abrir `/home/enflujo/Desktop/GugusseRoller`. VS Code instalará un servidor
compatible en la Pi. En el entorno remoto conviene instalar solamente Python y
el formateador; Pylance, C++, Jupyter y asistentes de IA aumentan mucho el uso
de CPU, memoria, archivos y SD.

Remote SSH es cómodo, pero todavía ejecuta el servidor de extensiones en la Pi.
La sincronización con `deploy-dev` ofrece el menor consumo posible.

## 4. Edición de emergencia en la Pi

Geany y Mousepad están instalados. Para abrir el archivo principal en la
pantalla de la Pi, incluso desde SSH:

```bash
gugusse edit
```

Desde una terminal también están disponibles `nano` y `vi`.
