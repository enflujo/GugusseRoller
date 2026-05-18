import json
from picamera2 import Picamera2
from picamera2.previews.qt import QGlPicamera2
from time import sleep, time
import os
from threading import Thread
import CameraSettings
from libcamera import Transform
from ConfigFiles import ConfigFiles

defaultValues = {"fps": 10}
defaultCaptureTuning = {
    "mainSkipBuffers": 3,
    "rawSkipBuffers": 3,
}


def setMissingToDefault(settings):
    for key in defaultValues:
        if key not in settings:
            settings[key] = defaultValues[key]


class GCamera(Picamera2):
    def __init__(self, win):
        Picamera2.__init__(self)
        self.win = win
        setMissingToDefault(win.settings)
        self.fps = self.win.settings["fps"]
        self.framecount = 0
        self.captureModes = ConfigFiles("captureModes.json")
        self.captureTuning = dict(defaultCaptureTuning)

        vflip = False
        hflip = False
        if "hflip" in win.settings:
            hflip = win.settings["hflip"]
        if "vflip" in win.settings:
            vflip = win.settings["vflip"]
        transform = Transform(vflip=vflip, hflip=hflip)

        self.config = self.create_preview_configuration(
            main={"size": self.sensor_resolution},
            controls={
                "FrameRate": self.fps,
                "FrameDurationLimits": (1000, 1000000 // self.fps),
                "NoiseReductionMode": 0,
            },
            raw={"size": self.sensor_resolution},
            transform=transform,
        )

        print(self.config)
        self.configure(self.config)

    def getConfig(self):
        return self.config

    def createPreviewWidget(self):
        self.camWidget = CameraSettings.previewWindowWidget(self.win)

    def setFileIndex(self, newIndex):
        self.framecount = newIndex

    def setCaptureTuning(self, tuning=None):
        self.captureTuning = dict(defaultCaptureTuning)
        if tuning is None:
            return
        for key in defaultCaptureTuning:
            if key in tuning:
                self.captureTuning[key] = tuning[key]

    def skipBuffers(self, count, which):
        total_elapsed = 0.0
        while count > 0:
            start_time = time()
            buffers, metadata = self.capture_buffers([which])
            elapsed_time = time() - start_time
            sleep_time = max(0, (1.0 / self.fps) - elapsed_time)
            sleep(sleep_time)
            total_elapsed += elapsed_time + sleep_time
            count -= 1
        return total_elapsed

    def waitExposureChange(self, expected, maxSkip=24):
        skipCount = 0
        while skipCount < maxSkip:
            buffers, metadata = self.capture_buffers(["main"])
            skipCount += 1
            metaExp = metadata["ExposureTime"]
            if (float(abs(metaExp - expected)) / float(expected)) < 0.1:
                break
            sleep(1.0 / self.fps)
        print(f"took {skipCount} buffers")
        return buffers, metadata

    def captureCycle(self):
        captureMode = self.win.captureMode.currentText()
        cycle_start = time()
        stats = {
            "captureMode": captureMode,
            "skipBuffers": 0,
            "skip_s": 0.0,
            "buffer_s": 0.0,
            "save_s": 0.0,
            "rename_s": 0.0,
        }
        if captureMode == "singleJpg":
            skip_count = self.captureTuning["mainSkipBuffers"]
            stats["skipBuffers"] = skip_count
            stats["skip_s"] = self.skipBuffers(skip_count, "main")
            fn = "/dev/shm/{:05d}.jpg".format(self.framecount)
            fnComplete = "/dev/shm/complete/{:05d}.jpg".format(self.framecount)

            step_start = time()
            buffers, metadata = self.capture_buffers(["main"])
            stats["buffer_s"] = time() - step_start
            orig = self.helpers.make_image(buffers[0], self.config["main"]).convert(
                "RGB"
            )
            step_start = time()
            self.helpers.save(orig, metadata, fn)
            stats["save_s"] = time() - step_start
            step_start = time()
            os.rename(fn, fnComplete)
            stats["rename_s"] = time() - step_start

        elif captureMode == "bracketing":
            skip_count = self.captureTuning["mainSkipBuffers"]
            stats["skipBuffers"] = skip_count
            stats["skip_s"] = self.skipBuffers(skip_count, "main")
            shutterMid = self.win.settings["ExposureMicroseconds"]
            shutterLow = shutterMid // 2
            shutterHigh = shutterMid * 2

            fn = "/dev/shm/{:05d}_m.jpg".format(self.framecount)
            fnComplete = "/dev/shm/complete/{:05d}_m.jpg".format(self.framecount)
            buffers, metadata = self.waitExposureChange(shutterMid)
            self.set_controls({"ExposureTime": shutterLow})
            orig = self.helpers.make_image(buffers[0], self.config["main"]).convert(
                "RGB"
            )
            self.helpers.save(orig, metadata, fn)
            os.rename(fn, fnComplete)

            fn = "/dev/shm/{:05d}_l.jpg".format(self.framecount)
            fnComplete = "/dev/shm/complete/{:05d}_l.jpg".format(self.framecount)
            buffers, metadata = self.waitExposureChange(shutterLow)
            self.set_controls({"ExposureTime": shutterHigh})
            orig = self.helpers.make_image(buffers[0], self.config["main"]).convert(
                "RGB"
            )
            self.helpers.save(orig, metadata, fn)
            os.rename(fn, fnComplete)

            fn = "/dev/shm/{:05d}_h.jpg".format(self.framecount)
            fnComplete = "/dev/shm/complete/{:05d}_h.jpg".format(self.framecount)
            buffers, metadata = self.waitExposureChange(shutterHigh)
            self.set_controls({"ExposureTime": int(shutterMid)})
            orig = self.helpers.make_image(buffers[0], self.config["main"]).convert(
                "RGB"
            )
            self.helpers.save(orig, metadata, fn)
            os.rename(fn, fnComplete)

        elif captureMode == "DNG":
            skip_count = self.captureTuning["rawSkipBuffers"]
            stats["skipBuffers"] = skip_count
            stats["skip_s"] = self.skipBuffers(skip_count, "raw")
            fn = f"/dev/shm/{self.framecount:05d}.dng"
            fnComplete = f"/dev/shm/complete/{self.framecount:05d}.dng"
            step_start = time()
            buffers, metadata = self.capture_buffers(["raw"])
            stats["buffer_s"] = time() - step_start
            step_start = time()
            self.helpers.save_dng(buffers[0], metadata, self.config["raw"], fn)
            stats["save_s"] = time() - step_start
            step_start = time()
            os.rename(fn, fnComplete)
            stats["rename_s"] = time() - step_start

        self.framecount += 1
        stats["capture_s"] = time() - cycle_start
        return stats
