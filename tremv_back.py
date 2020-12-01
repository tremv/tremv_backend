import cherrypy
import os
import sys
import datetime
import tremv_common as common

class backend(object):
    def __init__(self):
        self.config_stamp = 0
        self.config_filename = "tremv_config.json"
        self.config = {}


    """ Checks if the file timestamp has changed for the config file,
        and if so it reloads it. the conifguration dictionary is then returned.
    """
    def reload_config(self):
        stamp = os.stat(self.config_filename).st_mtime

        if(stamp != self.config_stamp):
            self.config = common.read_tremv_config(self.config_filename)
            self.config_stamp = stamp
        
        return(self.config)


    @cherrypy.expose
    def index(self):
        return "hello!"


    """ Return the most up to date list of stations as json.
    """
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def station_names(self):
        self.reload_config()

        return(self.config["station_names"])
    

    """ Return the most up to date list of filters as json.
    """
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def filters(self):
        self.reload_config()

        return(self.config["filters"])


    """ Reads the newest tremvlogs based on provided filters, and returns the latest
        values for each station that was asked for.
    """
    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def latest(self):
        result = []
        query = cherrypy.request.json

        self.reload_config()

        station_names = self.config["station_names"]
        filters = self.config["filters"]

        if("station_names" in query):
            if(len(query["station_names"]) > 0):
                station_names = query["station_names"]

        if("filters" in query):
            if(len(query["filters"]) > 0):
                filters = query["filters"]

        #NOTE: Reading the entire file in for now. Prehaps this can be made more efficient via seeking in the file or something...
        date = datetime.datetime.now()
        folder_path = common.generate_output_path(date)

        for f in filters:
            if(f in self.config["filters"]):
                tremvlog_filename = common.generate_tremvlog_filename(date, f)
                path = folder_path + tremvlog_filename
                rsam_results = common.read_tremvlog_file(path, station_names)

                station_data = {}

                for name in station_names:
                    if(name in self.config["station_names"]):
                        station_data[name] = rsam_results[name][-1]
                    else:
                        station_data[name] = 0.0

                result.append({"filter": f, "stations": station_data})

        return(result)


    """ Reads tremvlogs based on provided date and filters, and returns the stations
        as a json.
    """
    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def date(self):
        result = []
        query = cherrypy.request.json

        self.reload_config()

        station_names = self.config["station_names"]
        filters = self.config["filters"]

        if("station_names" in query):
            if(len(query["station_names"]) > 0):
                station_names = query["station_names"]

        if("filters" in query):
            if(len(query["filters"]) > 0):
                filters = query["filters"]

        date = datetime.datetime(query["date"]["year"], query["date"]["month"], query["date"]["day"])
        minute_of_day = (date.hour * 60) + date.minute

        folder_path = common.generate_output_path(date)

        for f in filters:
            if(f in self.config["filters"]):
                tremvlog_filename = common.generate_tremvlog_filename(date, f)
                path = folder_path + tremvlog_filename
                rsam_results = common.read_tremvlog_file(path, station_names)

                station_data = {}

                for name in station_names:
                    if(name in self.config["station_names"]):
                        station_data[name] = rsam_results[name]
                    else:
                        station_data[name] = [0.0 for x in range(0, minute_of_day)]

                result.append({"filter": f, "stations": station_data})

        return(result)

#TODO: support querying for an arbritrary date range, not just a specific date

if(__name__ == "__main__"):
    if(len(sys.argv) == 1):
        print("Server port argument is required.")
        sys.exit()

    cherrypy.server.socket_host = "0.0.0.0"
    cherrypy.server.socket_port = int(sys.argv[1])
    cherrypy.quickstart(backend())
