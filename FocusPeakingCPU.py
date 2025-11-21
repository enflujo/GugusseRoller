import sys
import numpy as np
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QFileDialog, QMainWindow
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QImage, QPixmap
from picamera2 import Picamera2
import cv2

class FocusPeakingApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.mode = "laplacian" # Default focus peaking mode
        self.peaking=True

        self.setWindowTitle("Focus Peaking Scanner")
        self.setGeometry(0, 0, 2028, 1520)

        
        self.last_blended_frame = None

        # Umbrales personalizables
        self.thresholds = {
            "laplacian": [80, 120],
            "tenengrad": [1e7, 2e7]
        }

        # Imagen
        self.label = QLabel(self)
        self.setCentralWidget(self.label)

        # Label de info
        self.info_label = QLabel(self)
        self.info_label.setStyleSheet("color: white; background-color: black; padding: 5px;")
        self.info_label.move(0, 10)
        self.info_label.resize(300, 25)

        # Botones de métrica
        self.btn_laplacian = QPushButton("Laplacian", self)
        self.btn_laplacian.move(10, 50)
        self.btn_laplacian.clicked.connect(lambda: self.setMode("laplacian"))

        self.btn_tenengrad = QPushButton("Tenengrad", self)
        self.btn_tenengrad.move(120, 50)
        self.btn_tenengrad.clicked.connect(lambda: self.setMode("tenengrad"))

        # Botón para guardar imagen
        self.btn_save = QPushButton("Save preview", self)
        self.btn_save.move(230, 50)
        self.btn_save.clicked.connect(self.save_image)

        # Inicializar cámara
        self.cam = Picamera2()
        config = self.cam.create_preview_configuration(main={"format": 'RGB888', "size": (2028, 1520)})
        self.cam.configure(config)
        self.cam.start()

        # Timer de actualización
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

    
    def setMode(self, mode):        
        self.mode = mode

    def save_image(self):
        if self.last_blended_frame is not None:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar imagen",
                "",
                "JPEG Files (*.jpg);;PNG Files (*.png)"
            )
            if path:
                # Asegurarse de que tenga una extensión válida
                if not (path.endswith(".jpg") or path.endswith(".jpeg") or path.endswith(".png")):
                    path += ".jpg"  # valor por defecto
                cv2.imwrite(path, cv2.cvtColor(self.last_blended_frame, cv2.COLOR_RGB2BGR))


    def update_frame(self):
        if not self.peaking:
            return
        
        frame = self.cam.capture_array()
        if frame is None:
            print("❌ No se pudo leer de la cámara")
            return

        # Reduce resolución para procesamiento (acelera todo)
        scale_factor = 0.25  # Reducción a 25% (puedes ajustar)
        small = cv2.resize(frame, (0, 0), fx=scale_factor, fy000=scale_factor)

        gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)

        if self.mode == "laplacian":
            focusResponse = cv2.Laplacian(gray, cv2.CV_8U)
            focusScore = focusResponse.var()
        else:
            sobelX = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
            sobelY = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
            focusResponse = np.sqrt(sobelX**2 + sobelY**2)
            focusScore = np.sum(focusResponse)

        low, high = self.thresholds[self.mode]

        if focusScore > high:
            color = (50, 168, 94)
        elif focusScore > low:
            t = (focusScore - low) / (high - low)
            red = int(217 * (1 - t))
            green = int(168 * t)
            color = (red, green, 0)
        else:
            color = (217, 48, 48)

        # Crear mapa de enfoque sobre imagen reducida
        focusMap = np.absolute(focusResponse).astype(np.uint8)
        normMap = cv2.normalize(focusMap, None, 0, 255, cv2.NORM_MINMAX)
        colorMap = cv2.applyColorMap(normMap, cv2.COLORMAP_JET)

        # Upsample para mezclar con imagen original
        colorMapFullSize = cv2.resize(colorMap, (frame.shape[1], frame.shape[0]))

        colorFrame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        blended = cv2.addWeighted(colorFrame, 0.6, colorMapFullSize, 0.4, 0)
        blended = cv2.cvtColor(blended, cv2.COLOR_BGR2RGB)

        h, w, ch = blended.shape
        blendedImage = QImage(blended.data, w, h, ch * w, QImage.Format_RGB888)


        self.label.setPixmap(QPixmap.fromImage(blendedImage))

        # Actualizar el texto y color de fondo
        self.info_label.setText(f"Focus level: {focusScore:.2f}")
        self.info_label.setStyleSheet(
            f"color: white; background-color: rgb({color[0]}, {color[1]}, {color[2]}); padding: 5px; font-weight: bold;"
        )
        self.info_label.adjustSize()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FocusPeakingApp()
    window.show()
    sys.exit(app.exec_())
