import unittest
from unittest.mock import MagicMock, patch

from CaptureLoop import CaptureLoop


class Signal:
    def __init__(self):
        self.messages = []

    def emit(self, message):
        self.messages.append(message)


class WindowWithInvalidConfiguration:
    hwSettings = {}
    motors = {}


class CaptureLoopTests(unittest.TestCase):
    def test_export_initialization_error_preserves_motor_holding_state(self):
        win = MagicMock()
        motor_format = {"speed": 1}
        win.hwSettings = {"filmFormats": {"super8": {
            "feeder": motor_format, "filmdrive": motor_format, "pickup": motor_format,
        }}}
        win.filmFormat.currentText.return_value = "super8"
        win.captureMode.currentText.return_value = "DNG"
        win.projectName.text.return_value = "original"
        win.motors = {name: MagicMock() for name in ("feeder", "filmdrive", "pickup")}
        capture = CaptureLoop(win, Signal())
        with patch("CaptureLoop.FtpThread") as exporter:
            exporter.return_value.getStartPoint.side_effect = RuntimeError("Unassigned images")
            exporter.return_value.is_alive.return_value = False
            capture.run()
        for motor in win.motors.values():
            motor.motor.disable.assert_not_called()
            motor.motor.enable.assert_not_called()
            motor.motor.clearFault.assert_not_called()
            motor.motor.setDirection.assert_not_called()
        win.picam2.captureCycle.assert_not_called()
        exporter.return_value.start.assert_not_called()
        exporter.return_value.stopLoop.assert_called_once()

    def capture_with_exporter(self, pending=0):
        capture = CaptureLoop(WindowWithInvalidConfiguration(), Signal())
        capture.export = MagicMock()
        capture.export.is_alive.return_value = True
        capture.export.queue.files.return_value = ["image"] * pending
        return capture

    def test_dead_exporter_prevents_another_frame(self):
        capture = self.capture_with_exporter()
        capture.export.is_alive.return_value = False
        capture.export.failure = "550 Disk full"
        self.assertFalse(capture.waitForExportCapacity())
        self.assertFalse(capture.Loop)

    def test_full_queue_waits_until_uploads_recover_before_capturing(self):
        capture = self.capture_with_exporter(7)

        def recover(_):
            capture.export.queue.files.return_value = []

        with patch("CaptureLoop.sleep", side_effect=recover):
            self.assertTrue(capture.waitForExportCapacity())
        self.assertTrue(capture.Loop)

    def test_prolonged_outage_stops_capture_after_five_minutes(self):
        capture = self.capture_with_exporter(7)
        with patch("CaptureLoop.monotonic", side_effect=[0, 301]):
            self.assertFalse(capture.waitForExportCapacity())
        self.assertFalse(capture.Loop)

    def test_stop_interrupts_full_queue_wait(self):
        capture = self.capture_with_exporter(7)
        with patch("CaptureLoop.sleep", side_effect=lambda _: capture.stopLoop()):
            self.assertFalse(capture.waitForExportCapacity())
        self.assertFalse(capture.Loop)

    def test_permanent_failure_during_queue_wait_stops_without_waiting_timeout(self):
        capture = self.capture_with_exporter(7)

        def fail(_):
            capture.export.is_alive.return_value = False
            capture.export.failure = "550 Permission denied"

        with patch("CaptureLoop.sleep", side_effect=fail):
            self.assertFalse(capture.waitForExportCapacity())
        self.assertFalse(capture.Loop)

    def test_unhandled_failure_always_reports_capture_stopped(self):
        signal = Signal()
        capture = CaptureLoop(WindowWithInvalidConfiguration(), signal)

        capture.run()

        self.assertTrue(
            any(
                message.startswith("Capture failed:")
                for message in signal.messages
            )
        )
        self.assertEqual(signal.messages[-1], "Capture stopped!")

    def test_stop_cancels_an_exporter_that_has_not_started(self):
        signal = Signal()
        capture = CaptureLoop(WindowWithInvalidConfiguration(), signal)
        capture.export = MagicMock()
        capture.export.is_alive.return_value = False

        capture.stopLoop()

        self.assertFalse(capture.Loop)
        capture.export.stopLoop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
