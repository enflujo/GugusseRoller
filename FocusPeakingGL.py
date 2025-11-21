import numpy as np
import cv2
from picamera2 import Picamera2
import time

# Inicializa la cámara
picam2 = Picamera2()
picam2.configure(picam2.create_still_configuration())

# Inicia la cámara
picam2.start()

# Captura una imagen de la cámara
time.sleep(2)  # Espera para estabilizar la cámara
image = picam2.capture_array()

# Convierte la imagen a escala de grises
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Aplica el filtro de Sobel para detectar los bordes
grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)

# Calcula la magnitud del gradiente
magnitude = cv2.magnitude(grad_x, grad_y)

# Normaliza la magnitud para que los bordes sean resaltados
magnitude = cv2.normalize(magnitude, None, 0, 255, cv2.NORM_MINMAX)

# Realiza una umbralización para resaltar los bordes más importantes
_, thresholded = cv2.threshold(magnitude, 50, 255, cv2.THRESH_BINARY)

# Muestra la imagen procesada
cv2.imshow("Focus Peaking", thresholded)

cv2.waitKey(0)
cv2.destroyAllWindows()
