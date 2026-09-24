import unittest
from unittest.mock import MagicMock, patch

import FtpThread


class Signal:
    def __init__(self):
        self.messages = []

    def emit(self, message):
        self.messages.append(message)


class FtpThreadTests(unittest.TestCase):
    @patch.object(FtpThread, "ConfigFiles")
    @patch.object(FtpThread, "FTP")
    def test_connection_uses_a_bounded_timeout(self, ftp_class, config_files):
        config_files.return_value = {
            "server": "ftp.example.test",
            "user": "user",
            "passwd": "secret",
            "path": ".",
        }
        ftp = ftp_class.return_value
        worker = FtpThread.FtpThread("project", "dng", Signal())

        worker.openConnection()

        ftp.connect.assert_called_once_with(
            "ftp.example.test", timeout=worker.default_timeout
        )
        ftp.login.assert_called_once_with(user="user", passwd="secret")

    @patch.object(FtpThread, "ConfigFiles")
    @patch.object(FtpThread, "FTP")
    def test_connection_timeout_can_be_configured(self, ftp_class, config_files):
        config_files.return_value = {
            "server": "ftp.example.test",
            "user": "user",
            "passwd": "secret",
            "path": ".",
            "timeout": 3,
        }
        worker = FtpThread.FtpThread("project", "dng", Signal())

        worker.openConnection()

        ftp_class.return_value.connect.assert_called_once_with(
            "ftp.example.test", timeout=3
        )

    def test_stop_closes_an_existing_connection(self):
        signal = Signal()
        worker = FtpThread.FtpThread("project", "dng", signal)
        worker.ftp = MagicMock()

        worker.stopLoop()

        self.assertFalse(worker.Loop)
        worker.ftp.close.assert_called_once_with()
        self.assertFalse(worker.connected)
        self.assertIn(
            "The FTP thread received the command to finish and stop", signal.messages
        )

    @patch.object(FtpThread, "FTP")
    def test_cancelled_worker_does_not_attempt_a_connection(self, ftp_class):
        worker = FtpThread.FtpThread("project", "dng", Signal())
        worker.Loop = False

        with self.assertRaisesRegex(InterruptedError, "cancelled"):
            worker.getStartPoint()

        ftp_class.assert_not_called()

    @patch.object(FtpThread, "listdir", return_value=[])
    def test_run_reuses_the_connection_opened_for_the_file_index(self, _listdir):
        worker = FtpThread.FtpThread("project", "dng", Signal())
        worker.ftp = MagicMock()
        worker.connected = True

        with patch.object(worker, "openConnection") as open_connection:
            with patch.object(
                FtpThread,
                "sleep",
                side_effect=lambda _delay: setattr(worker, "Loop", False),
            ):
                worker.run()

        open_connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
