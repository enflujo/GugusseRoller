from ftplib import FTP, error_temp, error_proto, error_perm
import math
import socket
from threading import Thread, Event
from time import monotonic
from ConfigFiles import ConfigFiles
from TransferQueue import TransferQueue, frame_index


class FtpThread(Thread):
    poll_delay = 0.2
    default_timeout = 10
    retryable = (OSError, EOFError, error_temp, error_proto)

    def __init__(self, subdir, fileExt, signal):
        super().__init__()
        self.subdir = subdir
        self.fileExt = fileExt
        self.connected = False
        self.Loop = True
        self.message = signal
        self.fileIndex = 0
        self.ftp = None
        self.stopped = Event()
        # Freeze the destination: editing ftp.json during a retry must never
        # redirect images that have already been captured.
        self.cfg = dict(ConfigFiles("ftp.json"))
        timeout = float(self.cfg.get("timeout", self.default_timeout))
        if not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("FTP timeout must be between 0 and 60 seconds")
        self.timeout = timeout
        self.queue = TransferQueue({
            "mode": "ftp", "server": self.cfg["server"],
            "user": self.cfg["user"], "path": self.cfg["path"],
            "project": subdir,
        })
        self.failure = None
        self.remote_names = set()

    def forceStartPoint(self, start):
        self.fileIndex = start

    def getStartPoint(self):
        if not self.Loop:
            raise InterruptedError("FTP connection cancelled")
        self.queue.acquire()
        try:
            self.openConnection()
            # Numeric maximum also works after frame 99999, and NLST may
            # return paths instead of bare names. Include every capture mode.
            self.fileIndex = max(
                self.queue.next_index(),
                max((frame_index(n) for n in self.remote_names), default=-1) + 1,
            )
            self.message.emit(f"File index now at: {self.fileIndex}")
            self.message.emit(f"Persistent capture queue: {self.queue.directory}")
            return self.fileIndex
        except Exception:
            self.closeConnection()
            self.queue.release()
            raise

    def openConnection(self):
        if not self.Loop:
            raise InterruptedError("FTP connection cancelled")
        self.closeConnection()
        cfg = self.cfg
        if not cfg["server"]:
            raise ValueError("FTP server not configured")
        self.message.emit(f"connecting to FTP (timeout: {self.timeout}s)")
        self.ftp = FTP()
        self.ftp.connect(cfg["server"], timeout=self.timeout)
        self.checkRunning()
        self.ftp.login(user=cfg["user"], passwd=cfg["passwd"])
        self.checkRunning()
        if cfg["path"] not in ("", "."):
            self.ftp.cwd(cfg["path"])
        try:
            self.ftp.mkd(self.subdir)
        except error_perm:
            # CWD below verifies that the directory really exists and that we
            # may enter it; do not suppress transient/network errors here.
            pass
        self.ftp.cwd(self.subdir)
        self.checkRunning()
        try:
            names = self.ftp.nlst()
        except error_temp as e:
            if str(e) != "450 No files found":
                raise
            names = []
        self.remote_names = {
            n.rsplit("/", 1)[-1] for n in names
            if frame_index(n) >= 0 and n.lower().endswith((".jpg", ".dng"))
        }
        self.checkRunning()
        self.connected = True

    def checkRunning(self):
        if not self.Loop:
            raise InterruptedError("FTP connection cancelled")

    def closeConnection(self):
        self.connected = False
        if self.ftp is not None:
            try:
                # shutdown wakes a control-channel read even if ftplib's file
                # object still holds the socket open in another thread.
                sock = self.ftp.sock
                if sock is not None:
                    sock.shutdown(socket.SHUT_RDWR)
            except (OSError, AttributeError):
                pass
            try:
                self.ftp.close()
            except Exception:
                pass

    def existingFileMatches(self, item, stream):
        stream.seek(0, 2)
        local_size = stream.tell()
        stream.seek(0)
        remote_size = 0
        prefix_matches = True

        def compare(block):
            nonlocal remote_size, prefix_matches
            self.checkRunning()
            remote_size += len(block)
            if stream.read(len(block)) != block:
                prefix_matches = False

        # RETR must finish successfully, including its completion reply. A
        # timeout midway through verification is never evidence of truncation.
        self.ftp.retrbinary("RETR " + item, compare)
        stream.seek(0)
        if prefix_matches and remote_size == local_size:
            return True
        if prefix_matches and remote_size < local_size:
            self.message.emit(
                f"Archivo FTP incompleto validado: {item}, {remote_size} de {local_size} bytes. "
                "Se enviará la imagen completa antes de reemplazarlo."
            )
            return False
        raise FileExistsError(
            f"Conflicto FTP en {item}: el archivo remoto difiere de la copia local "
            "y no se pudo validar como una copia incompleta. "
            "La imagen ya está asignada a su proyecto. Se conservan ambas copias; "
            "hay que revisar el archivo remoto antes de continuar."
        )

    def upload(self, item):
        attempt = 0
        while self.Loop:
            with open(self.queue.directory / item, "rb") as h:
                try:
                    if not self.connected:
                        self.openConnection()
                    self.checkRunning()
                    if item in self.remote_names:
                        # RNTO may have succeeded before its reply was lost.
                        # Identical bytes acknowledge delivery. A verified
                        # shorter prefix is repaired using the same atomic
                        # publication as a new upload, preserving the old file
                        # until the complete replacement has reached the server.
                        if self.existingFileMatches(item, h):
                            return True
                    temporary = ".gugusse-" + item + ".upload"
                    self.ftp.storbinary("STOR " + temporary, h)
                    self.checkRunning()
                    # STOR success includes the server's completion reply.
                    # Publish only complete files under the final image name.
                    self.ftp.rename(temporary, item)
                    self.remote_names.add(item)
                    return True
                except FileExistsError:
                    raise
                except self.retryable as e:
                    self.closeConnection()
                    if not self.Loop:
                        return False
                    attempt += 1
                    delay = min(2 ** min(attempt - 1, 5), 30)
                    self.message.emit(
                        f"FTP retry,file={item},attempt={attempt},"
                        f"delay={delay}s,error={type(e).__name__}: {e}"
                    )
            self.stopped.wait(delay)
        return False

    def run(self):
        try:
            while self.Loop:
                if self.stopped.wait(self.poll_delay):
                    break
                for item in self.queue.files():
                    if not self.Loop:
                        break
                    self.message.emit(f"xfer,{item}")
                    start = monotonic()
                    if not self.upload(item):
                        break
                    self.queue.remove(item)
                    self.message.emit(
                        f"ftpstats,file={item},dt={monotonic() - start:.3f}s,"
                        f"queue={len(self.queue.files())}"
                    )
        except Exception as e:
            if self.Loop:
                self.failure = f"{type(e).__name__}: {e}"
                self.message.emit(f"FTP stopped; pending images preserved: {self.failure}")
        finally:
            self.Loop = False
            self.closeConnection()
            self.queue.release()
            self.message.emit("End of ftp thread")

    def stopLoop(self):
        self.message.emit("The FTP thread received the command to finish and stop")
        self.Loop = False
        self.stopped.set()
        self.closeConnection()
        if not self.is_alive():
            self.queue.release()
