import json
import shutil


class ConfigFiles(dict):
    def __init__(self, filename):
        self.filename = filename
        self.config = {
            "ftp.json": self.getDefaultFtpSettings,
            "GugusseSettings.json": self.getDefaultGugusseSettings,
            "hardwarecfg.json": self.getDefaultHardwareSettings,
            "captureModes.json": self.getDefaultCaptureModes,
        }
        try:
            with open(filename, "rt") as h:
                data = json.load(h)
        except:
            data = self.config[filename]()
            with open(filename, "wt") as h:
                json.dump(data, h, indent=4)
        super(ConfigFiles, self).__init__(data)

    def save(self):
        with open(f"_{self.filename}", "wt") as h:
            json.dump(dict(self), h, sort_keys=True, indent=4)
        shutil.move(f"_{self.filename}", self.filename)

    def getDefaultFtpSettings(self):
        return {"passwd": "", "path": "", "server": "", "user": ""}

    def getDefaultGugusseSettings(self):
        return {
            "fps": 10,
            "ExposureMicroseconds": 30000,
            "ExposureCompensationStops": 0.0,
            "Exposure": "Manual",
            "ISO": 100,
            "WhiteBalanceMode": "Manual",
            "RedGain": 2.2,
            "BlueGain": 2.1,
            "WhileBalanceMode": "Auto",
            "vflip": False,
            "hflip": False,
            "ReelsDirection": "cw",
            "CaptureMode": "DNG",
        }

    def getDefaultCaptureModes(self):
        return {
            "DNG": {
                "description": "12bits DNGs",
                "suffix": "dng",
            },
            "singleJpg": {
                "description": "simple jpg",
                "suffix": "jpg",
            },
            "bracketing": {
                "description": "Bracketing (0,+1,-1) JPGs ",
                "suffix": "jpg",
            },
        }

    def getDefaultHardwareSettings(self):
        return {
            "feeder": {
                "DefaultTargetTime": 0.25,
                "invert": False,
                "maxSpeed": 20000,
                "minSpeed": 20,
                "name": "feeder",
                "pinDirection": 23,
                "pinEnable": 25,
                "pinStep": 24,
                "isFilmDrive": False,
                "stopPin": 6,
                "stopState": 1,
                "flags": ["pullUp"],
            },
            "filmFormats": {
                "16mm": {
                    "feeder": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 5,
                        "speed": 500.0,
                        "speed2": 50.0,
                        "targetTime": 0.33,
                    },
                    "filmdrive": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 900,
                        "speed": 4500.0,
                        "speed2": 500.0,
                        "targetTime": 0.4,
                    },
                    "pickup": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 5,
                        "speed": 1000.0,
                        "speed2": 50.0,
                        "targetTime": 0.33,
                    },
                },
                "16mmBigReels": {
                    "feeder": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 5,
                        "speed": 200.0,
                        "speed2": 50.0,
                        "targetTime": 0.45,
                    },
                    "filmdrive": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 900,
                        "speed": 4500.0,
                        "speed2": 500.0,
                        "targetTime": 0.4,
                    },
                    "pickup": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 5,
                        "speed": 500.0,
                        "speed2": 50.0,
                        "targetTime": 0.45,
                    },
                },
                "35mm": {
                    "feeder": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 10,
                        "speed": 250.0,
                        "speed2": 250.0,
                        "targetTime": 0.8,
                    },
                    "filmdrive": {
                        "faultTreshold": 7500,
                        "ignoreInitial": 2385,
                        "speed": 7000.0,
                        "speed2": 1000.0,
                        "targetTime": 0.85,
                    },
                    "pickup": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 10,
                        "speed": 500.0,
                        "speed2": 250.0,
                        "targetTime": 0.8,
                    },
                },
                "35mmBigReels": {
                    "feeder": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 10,
                        "speed": 100.0,
                        "speed2": 100.0,
                        "targetTime": 1.2,
                    },
                    "filmdrive": {
                        "faultTreshold": 7500,
                        "ignoreInitial": 2385,
                        "speed": 7000.0,
                        "speed2": 1000.0,
                        "targetTime": 0.85,
                    },
                    "pickup": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 10,
                        "speed": 250.0,
                        "speed2": 100.0,
                        "targetTime": 1.2,
                    },
                },
                "35mmSoundtrack": {
                    "feeder": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 10,
                        "speed": 200.0,
                        "speed2": 200.0,
                        "targetTime": 0.25,
                    },
                    "filmdrive": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 550,
                        "speed": 2000.0,
                        "speed2": 1000.0,
                        "targetTime": 0.4,
                    },
                    "pickup": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 10,
                        "speed": 200.0,
                        "speed2": 200.0,
                        "targetTime": 0.25,
                    },
                },
                "8mm": {
                    "feeder": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 5,
                        "speed": 400.0,
                        "speed2": 50.0,
                        "targetTime": 0.33,
                    },
                    "filmdrive": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 430,
                        "speed": 4000.0,
                        "speed2": 250.0,
                        "targetTime": 0.25,
                    },
                    "pickup": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 5,
                        "speed": 400.0,
                        "speed2": 50.0,
                        "targetTime": 0.33,
                    },
                },
                "pathex": {
                    "feeder": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 5,
                        "speed": 400.0,
                        "speed2": 50.0,
                        "targetTime": 0.33,
                    },
                    "filmdrive": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 900,
                        "speed": 6000.0,
                        "speed2": 1000.0,
                        "targetTime": 0.4,
                    },
                    "pickup": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 5,
                        "speed": 400.0,
                        "speed2": 50.0,
                        "targetTime": 0.33,
                    },
                },
                "super8": {
                    "feeder": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 0,
                        "speed": 400.0,
                        "speed2": 50.0,
                        "targetTime": 0.33,
                    },
                    "filmdrive": {
                        "faultTreshold": 8000,
                        "ignoreInitial": 475,
                        "speed": 2250.0,
                        "speed2": 200.0,
                        "targetTime": 0.4,
                    },
                    "pickup": {
                        "faultTreshold": 4000,
                        "ignoreInitial": 0,
                        "speed": 400.0,
                        "speed2": 50.0,
                        "targetTime": 0.33,
                    },
                },
            },
            "filmdrive": {
                "minSpeed": 20,
                "maxSpeed": 20000,
                "invert": False,
                "learnPin": 19,
                "name": "filmdrive",
                "pinDirection": 14,
                "pinEnable": 18,
                "pinStep": 15,
                "isFilmDrive": True,
                "stopPin": 26,
                "stopState": 1,
                "flags": [],
            },
            "lights": {"blue": 22, "green": 27, "red": 17},
            "pickup": {
                "invert": False,
                "maxSpeed": 20000,
                "minSpeed": 20,
                "name": "pickup",
                "pinDirection": 8,
                "pinEnable": 21,
                "pinStep": 7,
                "isFilmDrive": False,
                "stopPin": 13,
                "stopState": 1,
                "flags": ["pullUp"],
            },
        }
