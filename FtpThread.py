from ftplib import FTP
from os import listdir, makedirs, remove, path
from threading import Thread
from json import load
from time import sleep, time
from ConfigFiles import ConfigFiles


class FtpThread(Thread):
    poll_delay = 0.2
    default_timeout = 10

    def __init__(self, subdir, fileExt, signal):
        Thread.__init__(self)
        self.subdir = subdir
        self.fileExt = fileExt
        self.connected = False
        self.Loop = True
        self.message = signal
        self.fileIndex = 0
        self.ftp = None

    def forceStartPoint(self, start):
        self.fileIndex = start

    def getStartPoint(self):
        if not self.Loop:
            raise InterruptedError("FTP connection cancelled")
        if not self.connected:
            self.openConnection()
        listdir = []
        self.message.emit("listing remote (wait)".format(self.subdir))
        try:
            listdir = self.ftp.nlst("*.{}".format(self.fileExt))
        except Exception as e:
            msg = str(e)
            if msg != "450 No files found":
                self.message.emit(str(e))
                raise Exception(msg)
            self.message.emit("no {} in {}".format(self.fileExt, self.subdir))
            self.fileIndex = 0
            return 0
        if len(listdir) == 0:
            return 0
        self.message.emit("sorting list")
        listdir.sort()
        lastFile = listdir[len(listdir) - 1]
        self.message.emit("last file in {}={}".format(self.subdir, lastFile))
        self.fileIndex = 1 + int(lastFile.split(".")[0].split("_")[0], 10)
        self.message.emit("File index now at: {}".format(self.fileIndex))
        return self.fileIndex

    def openConnection(self):
        if not self.Loop:
            raise InterruptedError("FTP connection cancelled")
        cfg = ConfigFiles("ftp.json")
        if cfg["server"] == None or cfg["server"] == "":
            raise Exception("server not configured! Have you run MotorsAnFtpSetup.py?")
        timeout = cfg.get("timeout", self.default_timeout)
        self.message.emit(f"ftp settings:")
        self.message.emit(f"user={cfg['user']}, server={cfg['server']}")
        self.message.emit(f"path={cfg['path']}/{self.subdir}")
        self.message.emit(f"connecting to FTP (timeout: {timeout}s)")
        self.ftp = FTP()
        self.ftp.connect(cfg["server"], timeout=timeout)
        if not self.Loop:
            raise InterruptedError("FTP connection cancelled")
        self.ftp.login(user=cfg["user"], passwd=cfg["passwd"])
        if not self.Loop:
            raise InterruptedError("FTP connection cancelled")
        if cfg["path"] != "" and cfg["path"] != ".":
            self.ftp.cwd(cfg["path"])
        try:
            self.ftp.mkd(self.subdir)
        except Exception as e:
            msg = str(e)
            if not (
                msg.startswith("550 ")
                and ("File exists" in msg or "already exists" in msg)
            ):
                self.message.emit(str(e))
        self.ftp.cwd(self.subdir)
        self.connected = True

    def run(self):
        if not self.Loop:
            return
        try:
            # getStartPoint() already opens the connection. Reuse it instead of
            # making Run wait for a second connection to the same server.
            if not self.connected:
                self.openConnection()
            makedirs("/dev/shm/complete", exist_ok=True)
        except Exception as e:
            self.message.emit(str(e))
            self.connected = False
            self.message.emit("End of ftp thread")
            return
        while self.Loop:
            sleep(self.poll_delay)
            if not self.Loop:
                break
            file_list = sorted(listdir("/dev/shm/complete/"))
            for item in file_list:
                if not self.Loop:
                    break
                if path.isfile("/dev/shm/complete/{}".format(item)):
                    self.message.emit(f"xfer,{item}")
                    start = time()
                    try:
                        with open("/dev/shm/complete/{}".format(item), "rb") as h:
                            self.ftp.storbinary("STOR {}".format(item), h)
                    except Exception as e:
                        if self.Loop:
                            self.message.emit(f"FTP transfer failed: {e}")
                        self.Loop = False
                        break
                    remove("/dev/shm/complete/{}".format(item))
                    self.message.emit(
                        "ftpstats,file={},dt={:.3f}s,queue={}".format(
                            item, time() - start, len(listdir("/dev/shm/complete/"))
                        )
                    )
        self.message.emit("End of ftp thread")

    def stopLoop(self):
        self.message.emit("The FTP thread received the command to finish and stop")
        self.Loop = False
        # Closing the socket interrupts a pending FTP command (listing/upload/login).
        # connect() itself is bounded by default_timeout.
        try:
            if self.ftp is not None:
                self.ftp.close()
                self.connected = False
        except Exception:
            pass
