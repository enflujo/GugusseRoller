import unittest
from unittest.mock import MagicMock

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
