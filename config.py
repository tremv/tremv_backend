import os
import sys
import json
import logging

#a wrapper around the json config
class config:
    def __init__(self, filename):
        self.filename = filename
        self.stamp = 0
        self.config = None
        self._read()

    def __getitem__(self, key):
        return self.config[key]

    def _read(self):
        try:
            config_file = open(self.filename, "r")
            self.config = json.loads(config_file.read())
            config_file.close()
        except:
            logging.error("Please define a config.json file.")
            sys.exit(1)


    def reload(self):
        stamp = os.stat(self.filename).st_mtime

        if(stamp != self.stamp):
            self._read()
            self.stamp = stamp
