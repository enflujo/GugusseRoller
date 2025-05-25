import sys
import signal
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QLabel, QMainWindow, QPushButton,
    QWidget, QVBoxLayout, QHBoxLayout
)
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QImage, QPixmap
from picamera2 import Picamera2
import cv2
import RPi.GPIO as GPIO

# GPIO setup
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
up = GPIO.HIGH
dn = GPIO.LOW

lightPins = {
    "blue": 22,
    "green": 27,
    "red": 17
}

tab = {
    "on": [up, up, up],
    "off": [dn, dn, dn],
}


class ControlPanel(QWidget):
    def __init__(self, mainWindow):
        super().__init__()
        self.mainWindow = mainWindow

        layout = QVBoxLayout()

        self.imageWindow = QLabel("Focus Peaking")
        layout.addWidget(self.imageWindow)

        self.lightsBtn = QPushButton("Lights")
        self.lightsBtn.setCheckable(True)
        self.lightsBtn.setChecked(False)
        self.lightsBtn.clicked.connect(self.mainWindow.toggleLights)
        layout.addWidget(self.lightsBtn)

        self.aplacianBtn = QPushButton("Laplaciano")
        self.aplacianBtn.setCheckable(True)
        self.aplacianBtn.setChecked(True)
        self.aplacianBtn.clicked.connect(lambda: self.mainWindow.setMetric("laplacian"))
        layout.addWidget(self.aplacianBtn)

        self.tenengradBtn = QPushButton("Tenengrad")
        self.tenengradBtn.setCheckable(True)
        self.tenengradBtn.setChecked(False)
        self.tenengradBtn.clicked.connect(lambda: self.mainWindow.setMetric("tenengrad"))
        layout.addWidget(self.tenengradBtn)

        self.setLayout(layout)


class FocusPeakingWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Focus Peaking - Mapa de Enfoque")

        self.metric = "laplacian"
        self.lightsState = False

        for pin in lightPins.values():
            GPIO.setup(pin, GPIO.OUT, initial=dn)

        # Image preview window
        self.imageWindow = QLabel()
        self.imageWindow.setFixedSize(640, 480)

        # Score label
        self.scoreLabel = QLabel()
        self.scoreLabel.setStyleSheet("color: white; background-color: black; padding: 5px;")
        self.scoreLabel.setFixedHeight(25)

        # Main view (imagen + score)
        imageLayout = QVBoxLayout()
        imageLayout.addWidget(self.imageWindow)
        imageLayout.addWidget(self.scoreLabel)

        imageWidget = QWidget()
        imageWidget.setLayout(imageLayout)

        # Control panel
        self.controlPanel = ControlPanel(self)

        # Main layout
        mainLayout = QHBoxLayout()
        mainLayout.addWidget(imageWidget)
        mainLayout.addWidget(self.controlPanel)

        container = QWidget()
        container.setLayout(mainLayout)
        self.setCentralWidget(container)

        # Camera initialization
        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(main={"format": 'RGB888', "size": (640, 480)})
        self.picam2.configure(config)
        self.picam2.start()

        # Update timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

    def lightsOn(self):
        for pin in lightPins.values():
            GPIO.output(pin, up)
        self.controlPanel.lightsBtn.setChecked(True)

    def lightsOff(self):
        for pin in lightPins.values():
            GPIO.output(pin, dn)
        self.controlPanel.lightsBtn.setChecked(False)

    def toggleLights(self):
        if self.lightsState:
            self.lightsOff()
        else:
            self.lightsOn()
        self.lightsState = not self.lightsState

    def setMetric(self, metric):
        self.metric = metric
        self.controlPanel.aplacianBtn.setChecked(metric == "laplacian")
        self.controlPanel.tenengradBtn.setChecked(metric == "tenengrad")

    def update_frame(self):
        frame = self.picam2.capture_array()
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)

        # Calculate focus response
        if self.metric == "laplacian":
            focusResponse = cv2.Laplacian(gray, cv2.CV_64F)
            focusScore = focusResponse.var()
            scoreText = f"Laplacian: {focusScore:.2f}"

            if focusScore > 120:
                color = "green"
            elif focusScore > 80:
                color = "orange"
            else:
                color = "red"

        else:  # Tenengrad
            sobelX = cv2.Sobel(gray, cv2.CV_64F, 1, 0)
            sobelY = cv2.Sobel(gray, cv2.CV_64F, 0, 1)
            focusResponse = np.sqrt(sobelX ** 2 + sobelY ** 2)
            focusScore = np.sum(focusResponse)
            scoreText = f"Tenengrad: {focusScore:.2f}"

            if focusScore > 2e7:
                color = "green"
            elif focusScore > 1e7:
                color = "orange"
            else:
                color = "red"

        focusMap = np.absolute(focusResponse).astype(np.uint8)
        normMap = cv2.normalize(focusMap, None, 0, 255, cv2.NORM_MINMAX)

        # Umbral para detección de bordes/enfoque
        threshold = 100
        _, mask = cv2.threshold(normMap, threshold, 255, cv2.THRESH_BINARY)

        # Convertimos máscara a 3 canales para poder mezclar con la imagen color
        mask_color = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

        # Aplicamos el colormap sólo en zonas enfocadas
        colorMap = cv2.applyColorMap(normMap, cv2.COLORMAP_JET)
        colorFrame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # Mezcla: donde hay enfoque, usamos colorMap, sino usamos imagen original
        result = np.where(mask_color == 255, colorMap, colorFrame)

        # Convertimos a RGB para mostrar en Qt
        blended = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)

        h, w, ch = blended.shape
        bytesPerLine = ch * w
        qtImage = QImage(blended.data, w, h, bytesPerLine, QImage.Format_RGB888)
        self.imageWindow.setPixmap(QPixmap.fromImage(qtImage))

        self.scoreLabel.setText(f"Nivel de enfoque ({scoreText})")
        self.scoreLabel.setStyleSheet(
            f"color: white; background-color: {color}; padding: 5px; font-weight: bold;"
        )

    def cleanup(self):
        print("→ Turning lights off and cleaning resources...")
        self.timer.stop()
        self.picam2.stop()
        self.lightsOff()
        GPIO.cleanup()

    def closeEvent(self, event):
        self.cleanup()
        event.accept()


def signalHandler(sig, frame):
    print("\n→ CTRL+C detectado. Cerrando la app...")
    window.cleanup()
    app.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = FocusPeakingWindow()

    # Ctrl+C handler
    signal.signal(signal.SIGINT, signalHandler)

    window.show()
    sys.exit(app.exec_())
