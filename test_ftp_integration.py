"""Exercise ftplib with actual control/data sockets and deliberately lost replies."""
import socket
import socketserver
import threading
import tempfile
import unittest
from ftplib import FTP
from pathlib import Path
from unittest.mock import patch

import FtpThread
import TransferQueue
from test_ftp_thread import Signal


class FtpHandler(socketserver.StreamRequestHandler):
    def reply(self, message):
        self.wfile.write((message + "\r\n").encode())
        self.wfile.flush()

    def handle(self):
        passive = None
        rename_from = None
        self.reply("220 Local test FTP")
        try:
            while line := self.rfile.readline():
                command, _, argument = line.decode().strip().partition(" ")
                if command == "USER":
                    self.reply("331 Password required")
                elif command == "PASS":
                    self.reply("230 Logged in")
                elif command in ("CWD", "TYPE"):
                    self.reply("200 OK")
                elif command == "MKD":
                    self.reply('257 "project" created')
                elif command == "PASV":
                    passive = socket.socket()
                    passive.settimeout(2)
                    passive.bind(("127.0.0.1", 0))
                    passive.listen(1)
                    port = passive.getsockname()[1]
                    self.reply(f"227 Entering Passive Mode (127,0,0,1,{port // 256},{port % 256})")
                elif command in ("NLST", "STOR", "RETR"):
                    self.reply("150 Opening data connection")
                    data, _ = passive.accept()
                    data.settimeout(2)
                    with data:
                        if command == "NLST":
                            names = "\r\n".join(self.server.files) + "\r\n"
                            data.sendall(names.encode() if self.server.files else b"")
                        elif command == "RETR":
                            data.sendall(self.server.files[argument])
                        else:
                            received = bytearray()
                            while block := data.recv(8192):
                                received.extend(block)
                            self.server.files[argument] = bytes(received)
                    passive.close()
                    passive = None
                    if command == "STOR" and self.server.lose_store_reply:
                        self.server.lose_store_reply = False
                        return  # Real socket EOF instead of 226 completion.
                    if command == "STOR" and self.server.hold_store_reply:
                        self.server.store_waiting.set()
                        self.server.release_store.wait(3)
                        return
                    self.reply("226 Transfer complete")
                elif command == "RNFR":
                    rename_from = argument
                    self.reply("350 Ready for destination")
                elif command == "RNTO":
                    self.server.files[argument] = self.server.files.pop(rename_from)
                    if self.server.lose_rename_reply:
                        self.server.lose_rename_reply = False
                        return
                    self.reply("250 Renamed")
                else:
                    self.reply("502 Unsupported command")
        finally:
            if passive is not None:
                passive.close()


class LocalFtpServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        # Stop deliberately shuts down sockets during FTP commands.
        pass


class FtpIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.server = LocalFtpServer(("127.0.0.1", 0), FtpHandler)
        self.server.files = {}
        self.server.lose_store_reply = False
        self.server.lose_rename_reply = False
        self.server.hold_store_reply = False
        self.server.store_waiting = threading.Event()
        self.server.release_store = threading.Event()
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.close_server)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        port = self.server.server_address[1]

        class Client(FTP):
            def connect(self, host, timeout):
                return super().connect(host, port, timeout=timeout)

        for patcher in (
            patch.object(TransferQueue, "SPOOL_ROOT", root / "spool"),
            patch.object(TransferQueue, "LEGACY_QUEUE", root / "legacy"),
            patch.object(FtpThread, "FTP", Client),
            patch.object(FtpThread, "ConfigFiles", return_value={
                "server": "127.0.0.1", "user": "u", "passwd": "p", "path": ".", "timeout": 1,
            }),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.worker = FtpThread.FtpThread("project", "dng", Signal())
        self.worker.getStartPoint()
        self.addCleanup(self.worker.stopLoop)
        staged = self.worker.queue.staging / "00001.dng"
        self.content = bytes(range(256)) * 4096
        staged.write_bytes(self.content)
        self.worker.queue.publish(staged)

    def close_server(self):
        self.server.release_store.set()
        self.server.shutdown()
        self.server.server_close()

    def test_real_ftp_recovers_from_lost_store_completion(self):
        self.server.lose_store_reply = True
        with patch.object(self.worker.stopped, "wait"):
            self.assertTrue(self.worker.upload("00001.dng"))
        self.assertEqual(self.server.files, {"00001.dng": self.content})

    def test_real_ftp_recovers_from_lost_rename_completion(self):
        self.server.lose_rename_reply = True
        with patch.object(self.worker.stopped, "wait"):
            self.assertTrue(self.worker.upload("00001.dng"))
        self.assertEqual(self.server.files, {"00001.dng": self.content})

    def test_real_ftp_replaces_verified_incomplete_image(self):
        self.server.files["00001.dng"] = self.content[:32769]
        self.worker.openConnection()
        self.assertTrue(self.worker.upload("00001.dng"))
        self.assertEqual(self.server.files, {"00001.dng": self.content})

    def test_real_ftp_recovers_when_replacement_rename_reply_is_lost(self):
        self.server.files["00001.dng"] = self.content[:32769]
        self.worker.openConnection()
        self.server.lose_rename_reply = True
        with patch.object(self.worker.stopped, "wait"):
            self.assertTrue(self.worker.upload("00001.dng"))
        self.assertEqual(self.server.files, {"00001.dng": self.content})

    def test_stop_interrupts_real_control_socket_and_preserves_pending_file(self):
        self.server.hold_store_reply = True
        self.worker.start()
        self.assertTrue(self.server.store_waiting.wait(2))
        self.worker.stopLoop()
        self.worker.join(timeout=2)
        self.assertFalse(self.worker.is_alive())
        self.assertTrue((self.worker.queue.directory / "00001.dng").exists())
        self.assertNotIn("00001.dng", self.server.files)


if __name__ == "__main__":
    unittest.main()
