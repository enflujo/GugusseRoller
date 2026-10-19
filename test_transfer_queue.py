import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import TransferQueue
import recover_transfer_queue
from LocalThread import LocalThread
from test_ftp_thread import Signal


class TransferQueueTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.legacy = self.root / "legacy"
        for patcher in (
            patch.object(TransferQueue, "SPOOL_ROOT", self.root / "spool"),
            patch.object(TransferQueue, "LEGACY_QUEUE", self.legacy),
            patch.object(recover_transfer_queue, "LEGACY_QUEUE", self.legacy),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def queue(self, project="one", **changes):
        destination = {"mode": "ftp", "server": "host", "path": ".",
                       "user": "u", "project": project}
        destination.update(changes)
        queue = TransferQueue.TransferQueue(destination)
        self.addCleanup(queue.release)
        return queue

    def publish(self, queue, name="00010.dng", content=b"image"):
        source = queue.staging / name
        source.write_bytes(content)
        queue.publish(source)

    def test_ready_files_survive_reopening_and_select_next_frame(self):
        queue = self.queue()
        queue.acquire()
        self.publish(queue)
        queue.release()
        replacement = self.queue()
        replacement.acquire()
        self.assertEqual(replacement.next_index(), 11)
        self.assertEqual((replacement.directory / "00010.dng").read_bytes(), b"image")

    def test_projects_servers_and_modes_have_separate_queues(self):
        original = self.queue()
        original.acquire()
        self.publish(original)
        for changes in ({"project": "two"}, {"server": "other"},
                        {"path": "other"}, {"user": "other"}, {"mode": "local"}):
            other = self.queue(**changes)
            other.acquire()
            self.assertNotEqual(other.directory, original.directory)
            self.assertEqual(other.files(), [])

    def test_same_destination_cannot_have_two_exporters(self):
        original = self.queue()
        original.acquire()
        second = self.queue()
        with self.assertRaisesRegex(RuntimeError, "Another exporter"):
            second.acquire()
        original.release()
        second.acquire()

    def test_publication_refuses_to_overwrite_ready_image(self):
        queue = self.queue()
        queue.acquire()
        self.publish(queue)
        with self.assertRaises(FileExistsError):
            self.publish(queue, content=b"different")
        self.assertEqual((queue.directory / "00010.dng").read_bytes(), b"image")
        self.assertEqual((queue.staging / "00010.dng").read_bytes(), b"different")

    def test_interrupted_frame_blocks_restart_even_after_its_images_were_sent(self):
        queue = self.queue()
        queue.acquire()
        queue.begin_frame(10)
        self.publish(queue)
        queue.remove("00010.dng")
        queue.release()
        with self.assertRaisesRegex(RuntimeError, "Unfinished capture"):
            self.queue().acquire()

    def test_completed_bracket_group_has_no_incomplete_marker(self):
        queue = self.queue()
        queue.acquire()
        queue.begin_frame(10)
        for exposure in ("m", "l", "h"):
            self.publish(queue, f"00010_{exposure}.jpg")
        queue.finish_frame()
        queue.release()
        replacement = self.queue()
        replacement.acquire()
        self.assertEqual(replacement.next_index(), 11)
        self.assertEqual(len(replacement.files()), 3)

    def test_low_disk_space_prevents_capture_before_creating_marker(self):
        queue = self.queue()
        queue.acquire()
        with patch.object(TransferQueue.shutil, "disk_usage", return_value=MagicMock(free=100)):
            with self.assertRaisesRegex(OSError, "256 MiB"):
                queue.begin_frame(1)
        self.assertEqual(list(queue.staging.iterdir()), [])

    def test_legacy_ram_files_block_automatic_assignment(self):
        self.legacy.mkdir()
        (self.legacy / "00010.dng").write_bytes(b"old image")
        with self.assertRaisesRegex(RuntimeError, "Unassigned images"):
            self.queue().acquire()
        self.assertTrue((self.legacy / "00010.dng").exists())

    def test_explicit_legacy_recovery_preserves_bytes_and_assigns_destination(self):
        self.legacy.mkdir()
        source = self.legacy / "00010.dng"
        source.write_bytes(b"old image")
        queue = self.queue()
        self.assertEqual(recover_transfer_queue.recover(queue), 1)
        self.assertEqual((queue.directory / source.name).read_bytes(), b"old image")
        self.assertFalse(source.exists())
        queue.acquire()
        self.assertEqual(queue.next_index(), 11)

    def test_legacy_recovery_conflict_keeps_both_copies(self):
        queue = self.queue()
        queue.acquire()
        self.publish(queue)
        queue.release()
        self.legacy.mkdir()
        source = self.legacy / "00010.dng"
        source.write_bytes(b"different")
        with self.assertRaises(FileExistsError):
            recover_transfer_queue.recover(queue)
        self.assertEqual(source.read_bytes(), b"different")
        self.assertEqual((queue.directory / source.name).read_bytes(), b"image")

    def local_worker(self):
        worker = LocalThread("project", "jpg", Signal(), str(self.root / "export"))
        self.addCleanup(worker.stopLoop)
        worker.getStartPoint()
        worker.poll_delay = 0
        return worker

    def test_local_export_also_refuses_different_existing_image(self):
        worker = self.local_worker()
        self.publish(worker.queue)
        destination = worker.fullpath / "00010.dng"
        destination.write_bytes(b"existing")
        worker.run()
        self.assertIn("Refusing to overwrite", worker.failure)
        self.assertEqual(destination.read_bytes(), b"existing")
        self.assertEqual(worker.queue.files(), ["00010.dng"])

    def test_local_export_safely_resumes_identical_already_delivered_file(self):
        worker = self.local_worker()
        self.publish(worker.queue)
        destination = worker.fullpath / "00010.dng"
        destination.write_bytes(b"image")
        original_remove = worker.queue.remove

        def remove(name):
            original_remove(name)
            worker.Loop = False

        with patch.object(worker.queue, "remove", side_effect=remove):
            worker.run()
        self.assertEqual(destination.read_bytes(), b"image")
        self.assertEqual(worker.queue.files(), [])

    def test_local_export_publishes_complete_file_before_deleting_original(self):
        worker = self.local_worker()
        self.publish(worker.queue)
        original_remove = worker.queue.remove

        def remove(name):
            self.assertEqual((worker.fullpath / name).read_bytes(), b"image")
            original_remove(name)
            worker.Loop = False

        with patch.object(worker.queue, "remove", side_effect=remove):
            worker.run()
        self.assertEqual(worker.queue.files(), [])
        self.assertIsNone(worker.queue.lock)


if __name__ == "__main__":
    unittest.main()
