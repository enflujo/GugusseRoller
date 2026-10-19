import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QWidget, QLineEdit, QDialog
from PyQt5.QtTest import QTest

import PendingImages
import TransferQueue
import recover_transfer_queue
from CaptureLoop import RunStopWidget, SnapshotWidget


class TestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.hwSettings = {}
        self.projectName = QLineEdit("current", self)
        self.messages = []
        self.runStop = MagicMock()
        self.runStop.isCapturing.return_value = False
        self.snapshot = MagicMock()
        self.snapshot.isCaptureInProgress.return_value = False
        self.motors = {name: MagicMock() for name in ("feeder", "filmdrive", "pickup")}

    def log(self, text):
        self.messages.append(text)


class PendingImagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.legacy = root / "legacy"
        self.legacy.mkdir()
        self.cfg = {"server": "server", "path": "/images", "user": "user", "passwd": "secret"}
        for patcher in (
            patch.object(TransferQueue, "SPOOL_ROOT", root / "spool"),
            patch.object(TransferQueue, "LEGACY_QUEUE", self.legacy),
            patch.object(recover_transfer_queue, "LEGACY_QUEUE", self.legacy),
            patch.object(PendingImages, "ConfigFiles", return_value=self.cfg),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.win = TestWindow()
        self.addCleanup(self.win.close)

    def pending(self, name, data=b"image"):
        (self.legacy / name).write_bytes(data)

    def dialog(self):
        dialog = PendingImages.PendingImagesDialog(self.win)

        def cleanup():
            if dialog.worker is not None:
                dialog.worker.wait(3000)
            dialog.close()

        self.addCleanup(cleanup)
        return dialog

    def await_assignment(self, dialog):
        deadline = time.monotonic() + 3
        while dialog.result() != QDialog.Accepted and time.monotonic() < deadline:
            QTest.qWait(10)
            if dialog.worker is not None and not dialog.worker.isRunning() and dialog.buttons.isEnabled():
                break

    def test_dialog_assigns_selected_files_to_original_project_without_capturing(self):
        self.pending("00001.dng", b"first")
        self.pending("00002.dng", b"second")
        dialog = self.dialog()
        dialog.project.setText("original")
        dialog.files.item(1).setCheckState(Qt.Unchecked)
        dialog.start_assignment()
        self.await_assignment(dialog)
        self.assertEqual(dialog.result(), QDialog.Accepted)
        queue = dialog.worker.queue
        self.assertEqual(queue.destination["project"], "original")
        self.assertEqual(queue.destination["server"], "server")
        self.assertNotIn("passwd", queue.destination)
        self.assertEqual((queue.directory / "00001.dng").read_bytes(), b"first")
        self.assertEqual((self.legacy / "00002.dng").read_bytes(), b"second")
        self.assertEqual(self.win.projectName.text(), "original")
        self.win.runStop.start.assert_not_called()
        for motor in self.win.motors.values():
            motor.motor.disable.assert_not_called()
            motor.motor.enable.assert_not_called()

    def test_cancel_keeps_images_and_project(self):
        self.pending("00001.dng")
        dialog = self.dialog()
        dialog.project.setText("different")
        dialog.reject()
        self.assertEqual(dialog.result(), QDialog.Rejected)
        self.assertTrue((self.legacy / "00001.dng").exists())
        self.assertEqual(self.win.projectName.text(), "current")
        self.assertIsNone(dialog.worker)

    def test_after_assigning_all_seven_button_reports_pending_uploads(self):
        for index in range(11108, 11115):
            self.pending(f"{index}.dng")
        dialog = self.dialog()
        dialog.project.setText("original")
        dialog.start_assignment()
        self.await_assignment(dialog)
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(list(self.legacy.iterdir()), [])
        with patch.object(PendingImages.QMessageBox, "information") as message:
            PendingImages.show_pending_assignment(self.win)
        text = message.call_args.args[2]
        self.assertIn("7 imágenes ya asignadas", text)
        self.assertIn("pendientes de envío", text)
        self.assertIn("original", text)
        self.assertEqual(len(dialog.worker.queue.files()), 7)

    def test_empty_queue_message_distinguishes_project_and_uploads(self):
        with patch.object(PendingImages.QMessageBox, "information") as message:
            PendingImages.show_pending_assignment(self.win)
        self.assertIn("ni envíos pendientes", message.call_args.args[2])
        self.assertIn("current", message.call_args.args[2])

    def test_invalid_project_or_empty_selection_does_not_start_assignment(self):
        self.pending("00001.dng")
        dialog = self.dialog()
        for project in ("", "../other", "project with spaces"):
            dialog.project.setText(project)
            dialog.start_assignment()
            self.assertIsNone(dialog.worker)
        dialog.project.setText("original")
        dialog.files.item(0).setCheckState(Qt.Unchecked)
        dialog.start_assignment()
        self.assertIsNone(dialog.worker)
        self.assertTrue((self.legacy / "00001.dng").exists())

    def test_conflict_is_visible_and_preserves_both_copies(self):
        self.pending("00001.dng", b"old")
        dialog = self.dialog()
        destination = dict(dialog.destination, project="current")
        queue = TransferQueue.TransferQueue(destination)
        queue.acquire(allow_legacy=True)
        source = queue.staging / "00001.dng"
        source.write_bytes(b"other")
        queue.publish(source)
        queue.release()
        dialog.start_assignment()
        self.await_assignment(dialog)
        self.assertNotEqual(dialog.result(), QDialog.Accepted)
        self.assertIn("No se completó", dialog.status.text())
        self.assertTrue(dialog.buttons.isEnabled())
        self.assertEqual((self.legacy / "00001.dng").read_bytes(), b"old")
        self.assertEqual((queue.directory / "00001.dng").read_bytes(), b"other")

    def test_local_destination_assignment_uses_current_base_path(self):
        self.pending("00001.jpg")
        self.win.hwSettings = {"saveMode": "local", "localFilePath": self.temp.name}
        dialog = self.dialog()
        dialog.project.setText("original")
        dialog.start_assignment()
        self.await_assignment(dialog)
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(dialog.worker.queue.destination, {
            "mode": "local", "path": str(Path(self.temp.name) / "original"),
        })

    def test_run_opens_assignment_before_starting_capture_or_touching_motors(self):
        self.pending("00001.dng")
        run = MagicMock()
        run.win = self.win
        run.running = False
        with patch.object(PendingImages, "show_pending_assignment") as show:
            with patch("CaptureLoop.CaptureLoop") as capture:
                RunStopWidget.handlePush(run)
        show.assert_called_once_with(self.win)
        capture.assert_not_called()
        run.captureWidgetsEnable.assert_not_called()
        self.assertFalse(run.running)

    def test_snapshot_opens_assignment_before_taking_photo(self):
        self.pending("00001.dng")
        snapshot = MagicMock()
        snapshot.win = self.win
        snapshot.ignore = False
        with patch.object(PendingImages, "show_pending_assignment") as show:
            with patch("CaptureLoop.singleShotEvent") as capture:
                SnapshotWidget.handle(snapshot)
        show.assert_called_once_with(self.win)
        capture.assert_not_called()
        snapshot.initialize.assert_not_called()

    def test_preflight_does_not_start_run_even_if_assignment_was_successful(self):
        self.pending("00001.dng")
        with patch.object(PendingImages, "show_pending_assignment") as show:
            self.assertFalse(PendingImages.prepare_pending_images(self.win))
        show.assert_called_once_with(self.win)


if __name__ == "__main__":
    unittest.main()
