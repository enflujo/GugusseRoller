#!/usr/bin/env python3
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from Lights import LightControlWidget

app = QApplication(sys.argv)
window = QMainWindow()
layout = QVBoxLayout()

# Test creating the widget
try:
    light_widget = LightControlWidget(window)
    print(f"Widget created: {light_widget}")
    print(f"Widget visible: {light_widget.isVisible()}")
    print(f"Widget enabled: {light_widget.isEnabled()}")
    print(f"Widget size: {light_widget.size()}")
    print(f"Widget has label: {light_widget.getLabel()}")
    
    layout.addWidget(light_widget)
    
    widget = QWidget()
    widget.setLayout(layout)
    window.setCentralWidget(widget)
    
    print("Widget added to layout successfully")
    
except Exception as e:
    print(f"Error creating widget: {e}")
    import traceback
    traceback.print_exc()

window.show()
print("Window shown")
