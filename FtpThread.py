from ftplib import FTP
from os import listdir, makedirs, remove, path
from threading import Thread
from json import load
from time import sleep
from ConfigFiles import ConfigFiles


class FtpThread(Thread):
    def __init__(self, subdir, fileExt, signal):
        Thread.__init__(self)
        self.subdir = subdir
        self.fileExt = fileExt
        self.connected = False
        self.Loop = True
        self.message = signal
        self.fileIndex = 0

    def forceStartPoint(self, start):
        self.fileIndex = start

    def getStartPoint(self):
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
        cfg = ConfigFiles("ftp.json")
        self.ftp = FTP(cfg["server"])
        self.message.emit(f"ftp settings:")
        self.message.emit(f"user={cfg['user']}, server={cfg['server']}")
        self.message.emit(f"path={cfg['path']}/{self.subdir}")
        if cfg["server"] == None or cfg["server"] == "":
            raise Exception("server not configured! Have you run MotorsAnFtpSetup.py?")
        self.ftp.login(user=cfg["user"], passwd=cfg["passwd"])
        if cfg["path"] != "" and cfg["path"] != ".":
            self.ftp.cwd(cfg["path"])
        try:
            self.ftp.mkd(self.subdir)
        except Exception as e:
            msg = str(e)
            if msg != "550 {}: File exists".format(self.subdir):
                self.message.emit(str(e))
        self.ftp.cwd(self.subdir)
        self.connected = True

    def run(self):
        self.Loop = True
        localLoop = True
        if self.connected:
            self.ftp.close()
            self.connected = False
        try:
            self.openConnection()
            makedirs("/dev/shm/complete", exist_ok=True)
        except Exception as e:
            msg = str(e)
            self.message.emit(str(e))
        while localLoop:
            if self.Loop == False:
                localLoop = False
            sleep(1)
            file_list = sorted(listdir("/dev/shm/complete/"))
            for item in file_list:
                if path.isfile("/dev/shm/complete/{}".format(item)):
                    self.message.emit(f"xfer,{item}")
                    a = open("/dev/shm/complete/{}".format(item), "rb")
                    self.ftp.storbinary("STOR {}".format(item), a)
                    a.close()
                    remove("/dev/shm/complete/{}".format(item))
        self.message.emit("End of ftp thread")

    def stopLoop(self):
        self.message.emit("The FTP thread received the command to finish and stop")
        self.Loop = False
