import tempfile
import unittest
from ftplib import error_perm, error_temp
from pathlib import Path
from unittest.mock import MagicMock, patch

import FtpThread
import TransferQueue


class Signal:
    def __init__(self):
        self.messages = []

    def emit(self, message):
        self.messages.append(message)


class FakeServer:
    def __init__(self):
        self.files = {}
        self.connections = []
        self.stor_failures = []
        self.connect_failures = []
        self.rename_reply_lost = False
        self.uploads = []

    def client(self):
        server = self
        client = MagicMock()
        server.connections.append(client)
        client.nlst.side_effect = lambda: list(server.files)

        def connect(*args, **kwargs):
            if server.connect_failures:
                raise server.connect_failures.pop(0)

        def store(command, stream):
            name = command.split(" ", 1)[1]
            data = stream.read()
            server.uploads.append(data)
            if server.stor_failures:
                server.files[name] = data[:3]
                raise server.stor_failures.pop(0)
            server.files[name] = data

        def rename(source, target):
            server.files[target] = server.files.pop(source)
            if server.rename_reply_lost:
                server.rename_reply_lost = False
                raise TimeoutError("lost RNTO reply")

        def retrieve(command, callback):
            callback(server.files[command.split(" ", 1)[1]])

        client.connect.side_effect = connect
        client.storbinary.side_effect = store
        client.rename.side_effect = rename
        client.retrbinary.side_effect = retrieve
        return client


class FtpThreadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config = {"server": "ftp.example.test", "user": "user",
                       "passwd": "secret", "path": "."}
        self.server = FakeServer()
        for patcher in (
            patch.object(TransferQueue, "SPOOL_ROOT", root / "spool"),
            patch.object(TransferQueue, "LEGACY_QUEUE", root / "legacy"),
            patch.object(FtpThread, "ConfigFiles", side_effect=lambda _: self.config),
            patch.object(FtpThread, "FTP", side_effect=self.server.client),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def worker(self, project="project", initialize=True):
        worker = FtpThread.FtpThread(project, "dng", Signal())
        self.addCleanup(worker.stopLoop)
        if initialize:
            worker.getStartPoint()
        return worker

    def pending(self, worker, name="00001.dng", content=b"complete image"):
        source = worker.queue.staging / name
        source.write_bytes(content)
        worker.queue.publish(source)
        return worker.queue.directory / name

    def test_timeout_reconnects_and_resends_whole_file_to_temporary_name(self):
        worker = self.worker()
        self.pending(worker)
        self.server.stor_failures = [TimeoutError("timed out")]
        with patch.object(worker.stopped, "wait") as wait:
            self.assertTrue(worker.upload("00001.dng"))
        self.assertEqual(self.server.uploads, [b"complete image"] * 2)
        self.assertEqual(self.server.files, {"00001.dng": b"complete image"})
        self.assertEqual(len(self.server.connections), 2)
        wait.assert_called_once_with(1)
        self.assertTrue(worker.Loop)

    def test_failed_upload_never_publishes_partial_final_file(self):
        worker = self.worker()
        local = self.pending(worker)
        self.server.stor_failures = [TimeoutError("timed out")]
        with patch.object(worker.stopped, "wait", side_effect=lambda _: worker.stopLoop()):
            self.assertFalse(worker.upload("00001.dng"))
        self.assertTrue(local.exists())
        self.assertNotIn("00001.dng", self.server.files)
        self.assertEqual(self.server.files[".gugusse-00001.dng.upload"], b"com")

    def test_lost_rename_reply_verifies_existing_file_without_overwriting(self):
        worker = self.worker()
        self.pending(worker)
        self.server.rename_reply_lost = True
        with patch.object(worker.stopped, "wait"):
            self.assertTrue(worker.upload("00001.dng"))
        self.assertEqual(self.server.uploads, [b"complete image"])
        self.server.connections[-1].retrbinary.assert_called_once()

    def test_conflicting_existing_remote_file_is_preserved(self):
        self.server.files["00001.dng"] = b"other image"
        worker = self.worker()
        local = self.pending(worker)
        with self.assertRaises(FileExistsError):
            worker.upload("00001.dng")
        self.assertTrue(local.exists())
        self.assertEqual(self.server.files["00001.dng"], b"other image")
        self.assertEqual(self.server.uploads, [])

    def test_seven_assigned_images_survive_conflict_and_resume_after_resolution(self):
        self.server.files["11108.dng"] = b"previous interrupted upload"
        worker = self.worker()
        for index in range(11108, 11115):
            self.pending(worker, f"{index}.dng")
        worker.poll_delay = 0
        worker.run()
        self.assertIn("Conflicto FTP en 11108.dng", worker.failure)
        self.assertIn("ya está asignada", worker.failure)
        self.assertEqual(len(worker.queue.files()), 7)
        # An operator resolves the remote conflict. A new Run must reuse the
        # assigned queue, reserve the next frame and send all seven images.
        del self.server.files["11108.dng"]
        replacement = self.worker()
        self.assertEqual(replacement.fileIndex, 11115)
        replacement.poll_delay = 0
        original_remove = replacement.queue.remove

        def remove(name):
            original_remove(name)
            if not replacement.queue.files():
                replacement.Loop = False

        with patch.object(replacement.queue, "remove", side_effect=remove):
            replacement.run()
        self.assertEqual(replacement.queue.files(), [])
        self.assertEqual(set(self.server.files), {f"{i}.dng" for i in range(11108, 11115)})
        self.assertTrue(all(data == b"complete image" for data in self.server.files.values()))

    def test_existing_identical_remote_file_is_safe_to_acknowledge(self):
        self.server.files["00001.dng"] = b"complete image"
        worker = self.worker()
        self.pending(worker)
        self.assertTrue(worker.upload("00001.dng"))
        self.assertEqual(self.server.uploads, [])

    def test_short_matching_prefix_is_automatically_replaced_with_complete_image(self):
        for prefix in (b"", b"c", b"complete "):
            with self.subTest(prefix=prefix):
                self.server.files["00001.dng"] = prefix
                worker = self.worker()
                local = self.pending(worker)
                self.assertTrue(worker.upload("00001.dng"))
                self.assertEqual(self.server.files["00001.dng"], b"complete image")
                self.assertTrue(local.exists())  # run() removes only after upload returns.
                self.assertTrue(any("incompleto validado" in m for m in worker.message.messages))
                worker.queue.remove("00001.dng")
                worker.stopLoop()

    def test_shorter_unrelated_or_equal_length_different_or_longer_file_is_preserved(self):
        for remote in (b"different", b"complete imagX", b"complete image extra"):
            with self.subTest(remote=remote):
                self.server.files["00001.dng"] = remote
                worker = self.worker()
                self.pending(worker)
                with self.assertRaises(FileExistsError):
                    worker.upload("00001.dng")
                self.assertEqual(self.server.files["00001.dng"], remote)
                self.assertEqual(self.server.uploads, [])
                worker.queue.remove("00001.dng")
                worker.stopLoop()

    def test_failed_replacement_upload_keeps_old_prefix_and_local_image(self):
        self.server.files["00001.dng"] = b"complete "
        worker = self.worker()
        local = self.pending(worker)
        self.server.stor_failures = [TimeoutError("timed out")]
        with patch.object(worker.stopped, "wait", side_effect=lambda _: worker.stopLoop()):
            self.assertFalse(worker.upload("00001.dng"))
        self.assertEqual(self.server.files["00001.dng"], b"complete ")
        self.assertTrue(local.exists())

    def test_replacement_rename_denied_keeps_original_and_local_image(self):
        self.server.files["00001.dng"] = b"complete "
        worker = self.worker()
        local = self.pending(worker)
        worker.ftp.rename.side_effect = error_perm("550 Rename denied")
        worker.poll_delay = 0
        worker.run()
        self.assertIn("Rename denied", worker.failure)
        self.assertEqual(self.server.files["00001.dng"], b"complete ")
        self.assertEqual(self.server.files[".gugusse-00001.dng.upload"], b"complete image")
        self.assertTrue(local.exists())

    def test_failed_verification_is_not_mistaken_for_short_remote_file(self):
        self.server.files["00001.dng"] = b"complete image"
        worker = self.worker()
        local = self.pending(worker)

        def interrupted_retrieve(command, callback):
            callback(b"complete ")
            raise TimeoutError("lost verification completion")

        worker.ftp.retrbinary.side_effect = interrupted_retrieve
        with patch.object(worker.stopped, "wait", side_effect=lambda _: worker.stopLoop()):
            self.assertFalse(worker.upload("00001.dng"))
        self.assertEqual(self.server.uploads, [])
        self.assertEqual(self.server.files["00001.dng"], b"complete image")
        self.assertTrue(local.exists())

    def test_lost_rename_reply_after_repair_is_verified_without_resending(self):
        self.server.files["00001.dng"] = b"complete "
        worker = self.worker()
        self.pending(worker)
        self.server.rename_reply_lost = True
        with patch.object(worker.stopped, "wait"):
            self.assertTrue(worker.upload("00001.dng"))
        self.assertEqual(self.server.uploads, [b"complete image"])
        self.assertEqual(self.server.files["00001.dng"], b"complete image")

    def test_remote_comparison_handles_multiple_data_blocks(self):
        self.server.files["00001.dng"] = b"complete "
        worker = self.worker()
        self.pending(worker)

        def retrieve(command, callback):
            for block in (b"co", b"mpl", b"ete "):
                callback(block)

        worker.ftp.retrbinary.side_effect = retrieve
        self.assertTrue(worker.upload("00001.dng"))
        self.assertEqual(self.server.files["00001.dng"], b"complete image")

    def test_prolonged_outage_has_bounded_backoff_and_stop_retains_image(self):
        worker = self.worker()
        local = self.pending(worker)
        worker.closeConnection()
        self.server.connect_failures = [ConnectionRefusedError("offline")] * 8
        delays = []

        def wait(delay):
            delays.append(delay)
            if len(delays) == 8:
                worker.stopLoop()

        with patch.object(worker.stopped, "wait", side_effect=wait):
            self.assertFalse(worker.upload("00001.dng"))
        self.assertEqual(delays, [1, 2, 4, 8, 16, 30, 30, 30])
        self.assertTrue(local.exists())
        self.assertNotIn("00001.dng", self.server.files)

    def test_stop_during_connection_does_not_login_or_retry(self):
        worker = self.worker()
        self.pending(worker)
        worker.closeConnection()
        original = self.server.client

        def client():
            ftp = original()
            ftp.connect.side_effect = lambda *a, **kw: worker.stopLoop()
            return ftp

        with patch.object(FtpThread, "FTP", side_effect=client):
            self.assertFalse(worker.upload("00001.dng"))
        self.server.connections[-1].login.assert_not_called()

    def test_permanent_permission_failure_stops_worker_and_preserves_pending(self):
        worker = self.worker()
        local = self.pending(worker)
        self.server.stor_failures = [error_perm("550 Permission denied")]
        worker.poll_delay = 0
        worker.run()
        self.assertIn("550 Permission denied", worker.failure)
        self.assertFalse(worker.Loop)
        self.assertTrue(local.exists())
        self.assertIsNone(worker.queue.lock)

    def test_rename_permission_failure_keeps_local_image_and_remote_temporary(self):
        worker = self.worker()
        local = self.pending(worker)
        worker.ftp.rename.side_effect = error_perm("550 Rename denied")
        worker.poll_delay = 0
        worker.run()
        self.assertTrue(local.exists())
        self.assertNotIn("00001.dng", self.server.files)
        self.assertEqual(self.server.files[".gugusse-00001.dng.upload"], b"complete image")
        self.assertIn("Rename denied", worker.failure)

    def test_temporary_error_during_directory_setup_is_retried(self):
        worker = self.worker()
        self.pending(worker)
        worker.closeConnection()
        original = self.server.client
        count = 0

        def client():
            nonlocal count
            count += 1
            ftp = original()
            if count == 1:
                ftp.mkd.side_effect = error_temp("421 Service unavailable")
            return ftp

        with patch.object(FtpThread, "FTP", side_effect=client):
            with patch.object(worker.stopped, "wait"):
                self.assertTrue(worker.upload("00001.dng"))
        self.assertEqual(count, 2)

    def test_run_deletes_local_only_after_remote_publication(self):
        worker = self.worker()
        local = self.pending(worker)
        worker.poll_delay = 0
        original_remove = worker.queue.remove

        def remove(name):
            self.assertEqual(self.server.files[name], local.read_bytes())
            original_remove(name)
            worker.Loop = False

        with patch.object(worker.queue, "remove", side_effect=remove):
            worker.run()
        self.assertFalse(local.exists())
        self.assertIsNone(worker.queue.lock)

    def test_local_delete_failure_preserves_file_for_idempotent_restart(self):
        worker = self.worker()
        local = self.pending(worker)
        worker.poll_delay = 0
        with patch.object(worker.queue, "remove", side_effect=PermissionError("disk error")):
            worker.run()
        self.assertTrue(local.exists())
        replacement = self.worker()
        self.assertTrue(replacement.upload("00001.dng"))
        self.assertEqual(len(self.server.uploads), 1)

    def test_destination_is_frozen_while_configuration_changes(self):
        worker = self.worker()
        self.config.update(server="wrong-server", path="wrong-path", user="other")
        worker.openConnection()
        ftp = self.server.connections[-1]
        ftp.connect.assert_called_once_with("ftp.example.test", timeout=10)
        ftp.login.assert_called_once_with(user="user", passwd="secret")
        ftp.cwd.assert_called_once_with("project")

    def test_numeric_remote_maximum_includes_paths_and_other_capture_modes(self):
        self.server.files = {"/project/99999.dng": b"a", "100000_l.jpg": b"b",
                             "notes.txt": b"c", ".gugusse-999999.dng.upload": b"d"}
        worker = self.worker()
        self.assertEqual(worker.fileIndex, 100001)

    def test_restart_uses_pending_index_before_starting_uploader(self):
        worker = self.worker()
        self.pending(worker, "07619.dng")
        worker.stopLoop()
        self.server.files = {"07612.dng": b"old"}
        replacement = self.worker()
        self.assertEqual(replacement.fileIndex, 7620)

    def test_startup_failure_releases_lock_and_does_not_start_capture(self):
        worker = self.worker(initialize=False)
        self.server.connect_failures = [TimeoutError("offline")]
        with self.assertRaises(TimeoutError):
            worker.getStartPoint()
        self.assertIsNone(worker.queue.lock)
        self.assertFalse(worker.is_alive())
        self.worker()

    def test_timeout_is_bounded_and_configurable(self):
        self.config["timeout"] = 3
        worker = self.worker()
        worker.ftp.connect.assert_called_once_with("ftp.example.test", timeout=3)
        for invalid in (0, -1, 10000, float("inf"), float("nan")):
            self.config["timeout"] = invalid
            with self.assertRaises(ValueError):
                FtpThread.FtpThread("project", "dng", Signal())

    def test_cancelled_worker_does_not_connect(self):
        worker = self.worker(initialize=False)
        worker.stopLoop()
        with self.assertRaises(InterruptedError):
            worker.getStartPoint()
        self.assertEqual(self.server.connections, [])


if __name__ == "__main__":
    unittest.main()
