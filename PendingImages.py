"""Assign legacy captures from the GUI, without moving film or contacting FTP."""
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QDialogButtonBox, QMessageBox, QPushButton,
)
from CaptureSettings import makeValidFilename
from ConfigFiles import ConfigFiles
from TransferQueue import TransferQueue, unassigned_files
from recover_transfer_queue import recover


def destination_for_project(win, project):
    if win.hwSettings.get("saveMode", "ftp") == "local":
        return {"mode": "local", "path": str(
            (Path(win.hwSettings["localFilePath"]).expanduser() / project).resolve()
        )}
    cfg = ConfigFiles("ftp.json")
    return {"mode": "ftp", "server": cfg["server"], "user": cfg["user"],
            "path": cfg["path"], "project": project}


class AssignmentWorker(QThread):
    result = pyqtSignal(int, str)

    def __init__(self, queue, filenames, parent=None):
        super().__init__(parent)
        self.queue = queue
        self.filenames = filenames

    def run(self):
        try:
            count = recover(self.queue, self.filenames)
        except Exception as e:
            self.result.emit(0, str(e))
        else:
            self.result.emit(count, "")


class PendingImagesDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.worker = None
        self.assigned_project = None
        self.setWindowTitle("Asignar imágenes pendientes")
        self.resize(600, 470)
        layout = QVBoxLayout(self)
        label = QLabel(
            "Selecciona las imágenes que pertenecen al mismo proyecto e indica su nombre.\n"
            "Se guardarán en disco. La película permanece quieta y no se envía nada al FTP."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(QLabel("Proyecto original de las imágenes seleccionadas:"))
        self.project = QLineEdit(win.projectName.text())
        layout.addWidget(self.project)
        if win.hwSettings.get("saveMode", "ftp") == "local":
            self.destination = {"mode": "local"}
            self.base_path = win.hwSettings["localFilePath"]
            destination_label = f"Destino local: {self.base_path} / proyecto"
        else:
            cfg = ConfigFiles("ftp.json")
            self.destination = {"mode": "ftp", "server": cfg["server"],
                                "user": cfg["user"], "path": cfg["path"]}
            destination_label = f"Destino FTP: {cfg['user']}@{cfg['server']}:{cfg['path']} / proyecto"
        label = QLabel(destination_label)
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.files = QListWidget()
        layout.addWidget(self.files)
        self.refresh_files()
        self.status = QLabel("Puedes desmarcar archivos de otros proyectos. Run se inicia por separado.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Asignar y guardar")
        self.buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self.start_assignment)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def refresh_files(self):
        self.files.clear()
        for filename in unassigned_files():
            item = QListWidgetItem(filename, self.files)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)

    def selected_files(self):
        return [self.files.item(i).text() for i in range(self.files.count())
                if self.files.item(i).checkState() == Qt.Checked]

    def start_assignment(self):
        project = self.project.text().strip()
        if not project or makeValidFilename(project) != project:
            self.status.setText("Indica un proyecto válido: letras, números, guiones o guiones bajos.")
            return
        names = self.selected_files()
        if not names:
            self.status.setText("Selecciona al menos una imagen para asignar.")
            return
        destination = dict(self.destination)
        if destination["mode"] == "ftp":
            destination["project"] = project
        else:
            destination["path"] = str((Path(self.base_path).expanduser() / project).resolve())
        self.project.setEnabled(False)
        self.files.setEnabled(False)
        self.buttons.setEnabled(False)
        self.status.setText("Guardando imágenes en disco…")
        self._project_to_assign = project
        self.worker = AssignmentWorker(TransferQueue(destination), names, self)
        self.worker.result.connect(self.assignment_result)
        self.worker.start()

    def assignment_result(self, count, error):
        # The result signal can be delivered just before QThread.run returns.
        self.worker.wait()
        if error:
            self.project.setEnabled(True)
            self.files.setEnabled(True)
            self.buttons.setEnabled(True)
            self.refresh_files()
            self.status.setText(f"No se completó la asignación: {error}")
            return
        self.assigned_project = self._project_to_assign
        self.win.projectName.setText(self.assigned_project)
        self.win.log(f"{count} imágenes asignadas al proyecto {self.assigned_project}. "
                     "Pulsa Run cuando quieras continuar.")
        self.accept()

    def reject(self):
        if self.worker is None or not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)


def show_pending_assignment(win):
    if win.runStop.isCapturing() or win.snapshot.isCaptureInProgress():
        win.log("Espera a que termine la captura antes de asignar imágenes pendientes.")
        return
    try:
        if not unassigned_files():
            project = win.projectName.text()
            queue = TransferQueue(destination_for_project(win, project))
            count = len(queue.files()) if queue.directory.exists() else 0
            if count:
                text = (
                    f"No hay imágenes sin proyecto.\n\n"
                    f"El proyecto {project} tiene {count} imágenes ya asignadas, "
                    "guardadas en disco y pendientes de envío.\n\n"
                    "Pulsa Run para enviarlas y continuar. Si el envío se detiene, "
                    "el registro indica la causa; no es necesario volver a asignarlas."
                )
            else:
                text = f"No hay imágenes sin proyecto ni envíos pendientes para el proyecto {project}."
            QMessageBox.information(win, "Estado de imágenes pendientes", text)
            return
        win.snapshot.disableExportIfRunning()
        PendingImagesDialog(win).exec_()
    except Exception as e:
        QMessageBox.warning(win, "Asignar imágenes pendientes", str(e))


def prepare_pending_images(win):
    """GUI-thread preflight. Assignment never starts capture as a side effect."""
    try:
        if not unassigned_files():
            return True
        show_pending_assignment(win)
    except Exception as e:
        QMessageBox.warning(win, "Imágenes pendientes", str(e))
    return False


class PendingImagesButton(QPushButton):
    def __init__(self, win):
        super().__init__("Asignar pendientes")
        self.clicked.connect(lambda: show_pending_assignment(win))
