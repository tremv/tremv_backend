import os

#a wrapper around the json config
class config:
    def __init__(self):
        self.filename = "config.json"
        self.stamp = 0

        config_file = open(self.filename, "r")
        self.config = json.loads(config_file.read())
        config_file.close()

    def __getitem__(self, key):
        return self.config[key]

    def reload():
        stamp = os.stat(self.filename).st_mtime

        if(stamp != self.stamp):
            self.read()
            self.stamp = stamp
