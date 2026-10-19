# Capturas pendientes y recuperación de FTP

Las capturas nuevas se guardan en disco bajo `capture-spool/`, junto al código.
Cada destino tiene una carpeta identificada por un hash y un `destination.json`
con servidor, usuario, ruta y proyecto, sin contraseña. El directorio `ready/`
contiene imágenes completas pendientes; `staging/` contiene capturas en curso.
No borrar esta carpeta al actualizar el programa. El script `deploy-dev` solo
sincroniza código y recursos estáticos y no modifica estas capturas.

## Comportamiento de recuperación

| Situación | Comportamiento |
| --- | --- |
| FTP inaccesible al iniciar | Run/Snapshot falla antes de capturar o avanzar película. Se libera la conexión y el bloqueo de la cola. |
| Timeout, conexión cerrada o respuesta temporal durante el envío | Conserva la imagen, abre otra conexión y reenvía desde el principio. Reintentos a 1, 2, 4, 8, 16 y hasta 30 segundos. |
| Cola con más de seis archivos | Pausa antes de capturar otro fotograma. Retoma si baja la cola; se detiene después de cinco minutos sin recuperarse. |
| Contraseña incorrecta, permisos, disco remoto lleno u otro error permanente | Detiene el exportador y la captura conserva las pendientes. Corregir la causa y volver a dar Run. |
| Stop o cierre de la aplicación | Termina la captura en curso, cancela envíos y conserva pendientes en disco. No espera a vaciar la cola. Las operaciones de socket tienen timeout; cancelar el canal de datos puede tardar hasta ese timeout. |
| Nuevo Run | Calcula el siguiente número a partir de los archivos remotos y de las pendientes de ese destino, incluyendo JPG, DNG y bracketing. |
| Cambio de proyecto, servidor, usuario o ruta | Las pendientes permanecen asociadas al destino anterior. Seleccionarlo otra vez para continuar sus envíos. Las reconexiones usan la configuración fijada al comenzar Run/Snapshot. |
| Archivo remoto con el mismo nombre | Compara los bytes remotos con la copia local. Si coinciden y tienen igual tamaño, reconoce el envío. Si el remoto es más corto y todos sus bytes coinciden con el inicio del local, lo reemplaza automáticamente por la imagen completa. En cualquier otro caso, conserva ambas copias y muestra un conflicto. |
| Reinicio durante una captura | Una marca persistente impide continuar automáticamente un fotograma posiblemente incompleto. Requiere revisar la imagen y la posición física de la película. |
| Poco espacio local | Con menos de 256 MiB libres se rechaza la siguiente captura. Un error de escritura también detiene la secuencia antes de avanzar la película. |

FTP recibe primero `.gugusse-NOMBRE.upload`; solo después de confirmar el envío
lo renombra al nombre final. Al reparar una copia incompleta, mantiene el archivo
remoto anterior hasta completar el envío del reemplazo; no lo borra primero. Si
el servidor no permite reemplazar mediante renombrado, se detiene conservando
los archivos. Si se pierde la confirmación del renombrado, la
reconexión compara los bytes remotos antes de borrar la copia local. El servidor
necesita permitir listar, enviar, renombrar y leer archivos. Los temporales de
envíos interrumpidos se reutilizan al reanudar el mismo archivo.

Usar **un solo escritor por proyecto remoto**. El bloqueo evita exportadores
simultáneos en esta instalación, pero FTP no ofrece aquí un renombrado que
garantice rechazar reemplazos frente a otra máquina escribiendo simultáneamente.
El borrado o modificación externa de las imágenes tampoco se puede recuperar
automáticamente. La confirmación FTP no garantiza que el almacenamiento del
servidor sobreviva a una avería; mantener respaldos del destino.

## Pendientes de la versión anterior en RAM

Los archivos antiguos de `/dev/shm/complete` no identifican su proyecto. Al pulsar
Run o Snapshot, la aplicación abre el diálogo **Asignar imágenes pendientes**
antes de preparar los motores. También se puede abrir desde **Asignar pendientes**,
junto al nombre del proyecto.

1. Indicar el proyecto original de las imágenes seleccionadas.
2. Revisar el destino mostrado: corresponde a la configuración FTP o local actual.
3. Desmarcar las imágenes que pertenezcan a otros proyectos.
4. Pulsar **Asignar y guardar**. La copia se hace en segundo plano y no mueve la
   película ni se conecta al FTP. Solo borra la copia en RAM después de guardar
   y sincronizar la copia en disco.
5. Al terminar queda seleccionado el proyecto asignado. Pulsar **Run** por
   separado cuando se quiera continuar. Si quedan imágenes sin asignar,
   repetir la asignación para su proyecto correspondiente.

**Cancelar** no modifica las imágenes ni el proyecto seleccionado. Si hay un
conflicto, el diálogo conserva ambas copias y muestra el error. Mientras se está
copiando, no se permite cerrar el diálogo para evitar interrumpir el guardado.
Un error de preparación del destino conserva el estado de habilitación de los
motores y la tensión de la película; no se trata como un fallo de motores.

**No reiniciar la Raspberry Pi antes de guardar estas imágenes**: todavía están
en RAM. Si en el FTP quedó un archivo parcial de la versión anterior, la
comparación lo detectará al reanudar y lo reparará si es más corto y coincide
exactamente con el inicio de la imagen local. Si los bytes difieren, se conserva
el conflicto para revisión; un tamaño menor por sí solo no autoriza reemplazarlo.
La comparación debe terminar correctamente: un timeout al leer el remoto no se
interpreta como una copia incompleta.

## Captura incompleta

Si aparece `Unfinished capture files`, conservar `staging/` y `ready/`. Revisar
la marca `frame-in-progress`, los archivos y la posición de la película antes de
resolverlos. Un archivo a medio guardar no debe pasarse a `ready/` sin verificar
que sea una imagen completa. El programa no retrocede la película ni reconstruye
fotogramas sobrescritos por versiones anteriores.

El guardado persistente añade escrituras y sincronizaciones de disco. Antes de
una sesión larga, validar velocidad y espacio disponible en la Raspberry Pi con
la cámara y el FTP reales.

## Verificación

```sh
python3 -m unittest test_transfer_queue test_ftp_thread test_capture_loop test_pending_images test_ftp_integration -v
```

Las pruebas de integración usan exclusivamente un servidor FTP temporal en
`127.0.0.1` y comprueban pérdida de respuestas de STOR/RNTO y cancelación de sockets.
No escriben en el FTP de producción.
