from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QPushButton
from threading import Thread
from time import sleep, time
from datetime import datetime
from json import load, dumps
from os import mkdir, listdir
from FtpThread import FtpThread
from LocalThread import LocalThread
from ConfigFiles import ConfigFiles

STEP_DOMAIN_FIELDS = ("speed", "speed2", "ignoreInitial", "faultTreshold")
MOTOR_NAMES = ("feeder", "filmdrive", "pickup")


def _scale_step_value(field, value, scale):
    if field in ("ignoreInitial", "faultTreshold"):
        scaled = int(round(value * scale))
        if field == "faultTreshold":
            return max(1, scaled)
        return max(0, scaled)
    return value * scale


def resolve_motor_format_cfg(cfg):
    special_keys = {"reference", "driverStepScale"}
    if "reference" not in cfg:
        return dict(cfg)

    resolved = dict(cfg["reference"])
    step_scale = cfg.get("driverStepScale", 1.0)
    if step_scale != 1.0:
        for field in STEP_DOMAIN_FIELDS:
            if field in resolved:
                resolved[field] = _scale_step_value(field, resolved[field], step_scale)
    for key, value in cfg.items():
        if key not in special_keys:
            resolved[key] = value
    return resolved


def resolve_film_format_cfg(raw_cfg):
    resolved = {}
    for key, value in raw_cfg.items():
        if key in MOTOR_NAMES:
            resolved[key] = resolve_motor_format_cfg(value)
        else:
            resolved[key] = value
    return resolved


class FrameTimingReporter:
    def __init__(self, signal, group_size=10):
        self.signal = signal
        self.group_size = group_size
        self.metrics = [
            "total_s",
            "settle_s",
            "capture_s",
            "skip_s",
            "buffer_s",
            "save_s",
            "rename_s",
            "reels_s",
            "filmdrive_s",
        ]
        self.accum = {metric: 0.0 for metric in self.metrics}
        self.frames = 0
        self.max_queue = 0

    def record(self, stats):
        self.frames += 1
        for metric in self.metrics:
            self.accum[metric] += stats.get(metric, 0.0)
        self.max_queue = max(self.max_queue, stats.get("queue_saturated", 0))
        if self.frames <= 3 or stats.get("queue_saturated", 0) > 0:
            self.signal.emit(
                "perf frame={:04d} total={:.3f}s capture={:.3f}s "
                "skip={:.3f}s save={:.3f}s reels={:.3f}s "
                "filmdrive={:.3f}s queue={}".format(
                    self.frames,
                    stats.get("total_s", 0.0),
                    stats.get("capture_s", 0.0),
                    stats.get("skip_s", 0.0),
                    stats.get("save_s", 0.0),
                    stats.get("reels_s", 0.0),
                    stats.get("filmdrive_s", 0.0),
                    stats.get("queue_saturated", 0),
                )
            )
        if self.frames % self.group_size != 0:
            return
        self.signal.emit(
            "perf avg{:02d} total={:.3f}s capture={:.3f}s "
            "skip={:.3f}s save={:.3f}s settle={:.3f}s "
            "reels={:.3f}s filmdrive={:.3f}s queue_max={}".format(
                self.group_size,
                self.accum["total_s"] / self.group_size,
                self.accum["capture_s"] / self.group_size,
                self.accum["skip_s"] / self.group_size,
                self.accum["save_s"] / self.group_size,
                self.accum["settle_s"] / self.group_size,
                self.accum["reels_s"] / self.group_size,
                self.accum["filmdrive_s"] / self.group_size,
                self.max_queue,
            )
        )
        self.accum = {metric: 0.0 for metric in self.metrics}
        self.max_queue = 0


class FrameSequence:
    def __init__(self, win, start_frame, signal, capture_tuning=None):
        self.win = win
        self.signal = signal
        self.filmdrive = self.win.motors["filmdrive"].motor
        self.feeder = self.win.motors["feeder"].motor
        self.pickup = self.win.motors["pickup"].motor
        self.lastNum = "0"
        try:
            mkdir("/dev/shm/complete")
        except Exception:
            pass
        self.cam = self.win.picam2
        self.cam.setFileIndex(start_frame)
        self.capture_tuning = capture_tuning or {}
        self.settle_delay = self.capture_tuning.get("settleDelay", 0.1)
        self.win.light_selector.signal.emit("on")
        self.feeder.enable()
        self.pickup.enable()
        self.signal.emit("syncMotors")

    def frameAdvance(self):
        frame_start = time()
        m1 = MotorThread(self.filmdrive)
        m2 = MotorThread(self.feeder)
        m3 = MotorThread(self.pickup)
        # self.cam.gcApplySettings()
        if m1.motor.fault or m2.motor.fault or m3.motor.fault:
            self.feeder.disable()
            self.filmdrive.disable()
            self.pickup.disable()
            self.signal.emit("syncMotors")
            self.signal.emit("turning lights off")
            self.signal.emit("---------------------------------------------")
            self.signal.emit('"Motor faults" are issues with the sequence')
            self.signal.emit("they could be triggered by obvious reasons")
            self.signal.emit("like film's end or a film break.")
            self.signal.emit("Or less obvious reasons like film stuck, film")
            self.signal.emit("loose, film missing static friction, too much")
            self.signal.emit("friction by under lubrified bearings, tape")
            self.signal.emit("over film holes, hole sensor misaligned, film")
            self.signal.emit("out of specs, lightpipes displaced, blocked")
            self.signal.emit("sensors, wire disconnected...")
            self.signal.emit("---------------------------------------------")
            raise Exception("Capture stopped by Motor Faults!")
        settle_start = time()
        sleep(self.settle_delay)
        settle_s = time() - settle_start
        try:
            capture_stats = self.cam.captureCycle()
        except Exception as e:
            self.feeder.disable()
            self.filmdrive.disable()
            self.pickup.disable()
            self.signal.emit("Failure to capture image: {}".format(e))
            self.signal.emit("syncMotors")
            self.signal.emit("turning lights off")
            raise Exception("Stop")
        reels_start = time()
        m2.start()
        m3.start()
        m3.join()
        m2.join()
        reels_s = time() - reels_start
        filmdrive_start = time()
        m1.start()
        m1.join()
        filmdrive_s = time() - filmdrive_start
        return {
            "settle_s": settle_s,
            "capture_s": capture_stats.get("capture_s", 0.0),
            "skip_s": capture_stats.get("skip_s", 0.0),
            "buffer_s": capture_stats.get("buffer_s", 0.0),
            "save_s": capture_stats.get("save_s", 0.0),
            "rename_s": capture_stats.get("rename_s", 0.0),
            "reels_s": reels_s,
            "filmdrive_s": filmdrive_s,
            "queue_saturated": len(listdir("/dev/shm/complete")),
            "total_s": time() - frame_start,
        }


class MotorThread(Thread):
    def __init__(self, motor):
        Thread.__init__(self)
        self.motor = motor

    def run(self):
        self.motor.move()


class CaptureLoop(QThread):
    def __init__(self, win, signal):
        QThread.__init__(self)
        self.signal = signal
        self.win = win
        self.Loop = True
        self.captureModes = ConfigFiles("captureModes.json")
        self.export = None

    def run(self):
        try:
            self.capture()
        except Exception as e:
            self.signal.emit(f"Capture failed: {e}")
            self.cleanupAfterInitializationFailure()

    def capture(self):
        # send msgs
        self.signal.emit("Capture loop start")
        rawFilmFormatCfg = self.win.hwSettings["filmFormats"][
            self.win.filmFormat.currentText()
        ]
        currentFilmFormatCfg = resolve_film_format_cfg(rawFilmFormatCfg)
        captureTuning = currentFilmFormatCfg.get("capture", {})
        self.win.motors["feeder"].motor.setFormat(currentFilmFormatCfg["feeder"])
        self.win.motors["filmdrive"].motor.setFormat(currentFilmFormatCfg["filmdrive"])
        self.win.motors["pickup"].motor.setFormat(currentFilmFormatCfg["pickup"])
        self.win.picam2.setCaptureTuning(captureTuning)
        self.reporter = FrameTimingReporter(self.signal)
        self.signal.emit(
            "perf profile format={} mode={} saveMode={} tuning={}".format(
                self.win.filmFormat.currentText(),
                self.win.captureMode.currentText(),
                self.win.hwSettings.get("saveMode", "ftp"),
                captureTuning,
            )
        )
        self.signal.emit(
            "perf motors format={} feeder={} filmdrive={} pickup={}".format(
                self.win.filmFormat.currentText(),
                currentFilmFormatCfg["feeder"],
                currentFilmFormatCfg["filmdrive"],
                currentFilmFormatCfg["pickup"],
            )
        )
        if rawFilmFormatCfg != currentFilmFormatCfg:
            self.signal.emit(
                "perf motor-profile format={} feeder={} filmdrive={} pickup={}".format(
                    self.win.filmFormat.currentText(),
                    rawFilmFormatCfg["feeder"],
                    rawFilmFormatCfg["filmdrive"],
                    rawFilmFormatCfg["pickup"],
                )
            )

        self.win.motors["feeder"].motor.enable()
        self.win.motors["filmdrive"].motor.enable()
        self.win.motors["pickup"].motor.enable()

        self.win.motors["feeder"].motor.clearFault()
        self.win.motors["filmdrive"].motor.clearFault()
        self.win.motors["pickup"].motor.clearFault()

        self.win.motors["feeder"].motor.setDirection(
            self.win.reelsDirection.currentText()
        )
        self.win.motors["filmdrive"].motor.setDirection("cw")
        self.win.motors["pickup"].motor.setDirection(
            self.win.reelsDirection.currentText()
        )

        if (
            "saveMode" in self.win.hwSettings
            and self.win.hwSettings["saveMode"] == "local"
        ):
            self.export = LocalThread(
                self.win.projectName.text(),
                self.captureModes[self.win.captureMode.currentText()]["suffix"],
                self.signal,
                self.win.hwSettings["localFilePath"],
            )
        else:
            self.export = FtpThread(
                self.win.projectName.text(),
                self.captureModes[self.win.captureMode.currentText()]["suffix"],
                self.signal,
            )
        try:
            if not self.Loop:
                raise InterruptedError("Capture cancelled")
            start = self.export.getStartPoint()
            if not self.Loop:
                raise InterruptedError("Capture cancelled")
            self.export.start()
            self.sequence = FrameSequence(
                self.win, start, self.signal, capture_tuning=captureTuning
            )
        except Exception as e:
            self.signal.emit(f"Export initialization failed: {e}")
            self.cleanupAfterInitializationFailure()
            return

        while self.Loop:
            try:
                frame_stats = self.sequence.frameAdvance()
                self.reporter.record(frame_stats)
            except Exception as e:
                self.signal.emit(str(e))
                self.stopLoop()
            if len(listdir("/dev/shm/complete")) > 6:
                self.signal.emit("too many files waiting")
                self.signal.emit("waiting up to 5 mins")
                timeout = time() + 300
                while (
                    self.Loop
                    and timeout > time()
                    and len(listdir("/dev/shm/complete")) > 6
                ):
                    sleep(0.1)
                if timeout <= time():
                    self.signal.emit("timeout xfer error")
                    self.stopLoop()
        self.signal.emit("waiting up to 2 minutes for transfer queue to be cleared")
        timeout = time() + 120
        while len(listdir("/dev/shm/complete")) > 0:
            sleep(0.1)
            if time() > timeout:
                self.signal.emit("TIMEOUT waiting for end")
                break

        self.signal.emit("stopping Export")
        self.export.stopLoop()
        self.export.join()
        self.signal.emit("Capture stopped!")

    def cleanupAfterInitializationFailure(self):
        try:
            if self.export is not None:
                self.export.stopLoop()
                if self.export.is_alive():
                    self.export.join()
        except Exception:
            pass
        for name in ["feeder", "filmdrive", "pickup"]:
            try:
                self.win.motors[name].motor.disable()
            except Exception:
                pass
        self.signal.emit("syncMotors")
        self.signal.emit("turning lights off")
        self.signal.emit("Capture stopped!")

    def stopLoop(self):
        self.signal.emit("Stopping Loop")
        self.Loop = False
        # Export initialization may be waiting on FTP. Ask it to close its socket
        # so Stop does not leave the button disabled until the network times out.
        try:
            if self.export is not None and not self.export.is_alive():
                self.export.stopLoop()
        except Exception:
            pass


class RunStopWidget(QPushButton):
    signal = pyqtSignal("PyQt_PyObject")

    def __init__(self, win):
        QPushButton.__init__(self, "Run")
        self.win = win
        self.clicked.connect(self.handlePush)
        self.signal.connect(self.handleSignal)
        self.running = False
        self.stopping = False
        self.run = None

    def captureWidgetsEnable(self, state):
        if state:
            self.win.reenableWidgetsAfterCapture()
        else:
            self.win.disableWidgetsWhenCapture()

    def handlePush(self):
        if not self.running:
            if self.win.snapshot.isCaptureInProgress():
                self.win.log(
                    "Snapshot in progress, wait for it to finish before starting Run"
                )
                return
            self.win.snapshot.disableExportIfRunning()
            self.captureWidgetsEnable(False)
            self.running = True
            self.stopping = False
            self.run = CaptureLoop(self.win, self.signal)
            self.run.start()
            self.setText("Stop")
        else:
            self.setEnabled(False)
            self.setText("Stopping!")
            self.stopping = True
            self.run.stopLoop()

    def isCapturing(self):
        return self.running

    def warnReelChange(self, direction):
        if self.running:
            self.win.motors["feeder"].motor.setDirection(direction)
            self.win.motors["pickup"].motor.setDirection(direction)
            self.win.log(f"Changing reels directions live to {direction}")

    def handleSignal(self, unfiltered):
        msg = str(unfiltered)
        if msg[0:4] == "xfer":
            s = msg.split(",")
            self.win.lastFileLabel.setText(
                f"{datetime.now().strftime('%H:%M:%S')} {s[1]}"
            )
            self.lastNum = s[1]
            return
        self.win.log(msg)
        if msg == "syncMotors":
            self.win.motors["feeder"].syncMotorStatus()
            self.win.motors["filmdrive"].syncMotorStatus()
            self.win.motors["pickup"].syncMotorStatus()
            return
        if msg == "turning lights off":
            self.win.light_selector.handleSignal("off")
            return
        if msg == "Capture stopped!":
            self.setText("Run")
            self.captureWidgetsEnable(True)
            self.running = False
            self.stopping = False
            self.run = None
            self.setEnabled(True)
        if msg == "Stopping Loop":
            self.setEnabled(False)
            self.setText("Stopping")


class singleShotEvent(QThread):
    def __init__(self, picam2, signal):
        QThread.__init__(self)
        self.picam2 = picam2
        self.signal = signal

    def run(self):
        try:
            self.picam2.captureCycle()
            self.signal.emit("captureDone")
        except Exception as e:
            self.signal.emit(f"captureFailed,{e}")


class SnapshotWidget(QPushButton):
    signal = pyqtSignal("PyQt_PyObject")

    def __init__(self, win):
        QPushButton.__init__(self)
        self.win = win
        self.setIcon(QIcon("camera.png"))
        self.clicked.connect(self.handle)
        self.projectName = None
        self.export = None
        self.captureModes = ConfigFiles("captureModes.json")
        self.signal.connect(self.signalHandle)
        self.ignore = False
        self.lastNum = 0
        self.trigger = None

    def isCaptureInProgress(self):
        return self.ignore or (
            self.trigger is not None and self.trigger.isRunning()
        )

    def initialize(self):
        self.disableExportIfRunning()
        self.projectName = self.win.projectName.text()
        try:
            if (
                "saveMode" in self.win.hwSettings
                and self.win.hwSettings["saveMode"] == "local"
            ):
                self.export = LocalThread(
                    self.win.projectName.text(),
                    self.captureModes[self.win.captureMode.currentText()]["suffix"],
                    self.signal,
                    self.win.hwSettings["localFilePath"],
                )
            else:
                self.export = FtpThread(
                    self.win.projectName.text(),
                    self.captureModes[self.win.captureMode.currentText()]["suffix"],
                    self.signal,
                )
            self.win.picam2.setFileIndex(self.export.getStartPoint())
            self.export.start()
        except Exception:
            self.export = None
            raise

    def disableExportIfRunning(self):
        if self.export != None:
            self.export.stopLoop()
            self.export.join()
            self.export = None

    def handle(self):
        if self.win.runStop.isCapturing():
            self.win.log("Snapshot is disabled while the capture loop is running")
            return
        if self.ignore:
            self.win.log("Too early to click again for a snapshot!")
            return
        try:
            if self.export == None or self.win.projectName.text() != self.projectName:
                self.initialize()
        except Exception as e:
            self.win.log(f"Snapshot initialization failed: {e}")
            return
        self.trigger = singleShotEvent(self.win.picam2, self.signal)
        self.ignore = True
        self.win.runStop.setEnabled(False)
        self.trigger.start()

    def signalHandle(self, unfiltered):
        msg = str(unfiltered)
        if msg == "captureDone":
            self.ignore = False
            self.trigger = None
            if not self.win.runStop.isCapturing():
                self.win.runStop.setEnabled(True)
        elif msg[0:4] == "xfer":
            self.lastNum = msg.split(",", 1)[1].split("/")[-1]
            self.win.lastFileLabel.setText(
                f"LAST: {datetime.now().strftime('%H:%M:%S')} {self.lastNum}"
            )
        elif msg[0:14] == "captureFailed,":
            self.ignore = False
            self.trigger = None
            if not self.win.runStop.isCapturing():
                self.win.runStop.setEnabled(True)
            self.win.log(msg.split(",", 1)[1])
        else:
            self.win.log(msg)
