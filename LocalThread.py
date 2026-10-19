import filecmp
import os
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Thread, Event
from time import monotonic
from TransferQueue import TransferQueue, frame_index, sync_directory


class LocalThread(Thread):
    poll_delay = 0.2

    def __init__(self, subdir, fileExt, signal, basePath):
        super().__init__()
        self.subdir = subdir
        self.fileExt = fileExt
        self.Loop = True
        self.message = signal
        self.fileIndex = 0
        self.fullpath = (Path(basePath).expanduser() / subdir).resolve()
        self.queue = TransferQueue({"mode": "local", "path": str(self.fullpath)})
        self.failure = None
        self.stopped = Event()

    def forceStartPoint(self, start):
        self.fileIndex = start

    def getStartPoint(self):
        if not self.Loop:
            raise InterruptedError("Local export cancelled")
        self.queue.acquire()
        try:
            self.fullpath.mkdir(parents=True, exist_ok=True)
            self.fileIndex = max(
                self.queue.next_index(),
                max((frame_index(p.name) for p in self.fullpath.iterdir()
                     if p.suffix.lower() in (".jpg", ".dng")), default=-1) + 1,
            )
            return self.fileIndex
        except Exception:
            self.queue.release()
            raise

    def run(self):
        try:
            while self.Loop:
                if self.stopped.wait(self.poll_delay):
                    break
                for item in self.queue.files():
                    if not self.Loop:
                        break
                    source = self.queue.directory / item
                    destination = self.fullpath / item
                    start = monotonic()
                    self.message.emit(f"xfer,{destination}")
                    if destination.exists():
                        if not filecmp.cmp(source, destination, shallow=False):
                            raise FileExistsError(f"Refusing to overwrite {destination}")
                    else:
                        with NamedTemporaryFile(dir=self.fullpath, prefix=".gugusse-") as h:
                            with open(source, "rb") as original:
                                shutil.copyfileobj(original, h)
                            h.flush()
                            os.fsync(h.fileno())
                            os.link(h.name, destination)
                            sync_directory(self.fullpath)
                    self.queue.remove(item)
                    self.message.emit(
                        f"localstats,file={item},dt={monotonic() - start:.3f}s,"
                        f"queue={len(self.queue.files())}"
                    )
        except Exception as e:
            self.failure = f"{type(e).__name__}: {e}"
            self.message.emit(f"Local export stopped; pending images preserved: {self.failure}")
        finally:
            self.Loop = False
            self.queue.release()

    def stopLoop(self):
        self.Loop = False
        self.stopped.set()
        if not self.is_alive():
            self.queue.release()
