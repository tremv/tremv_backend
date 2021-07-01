import cherrypy
import os
import sys
import datetime
import tremv_common as common

class server(object):
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

    """ Return list of station names and a list of filters
    """
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def metadata(self):
        self.reload_config()
        return({"filters": self.config["filters"], "station_names": self.config["station_names"]})


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
        folder_path = common.logger_output_path(date)

        for f in filters:
            if(f in self.config["filters"]):
                tremvlog_filename = common.generate_tremvlog_filename(date, f)
                path = folder_path + tremvlog_filename
                rsam_results = common.read_tremvlog_file(path)

                station_data = {}

                for name in station_names:
                    if(name in self.config["station_names"] and name in rsam_results):
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
    def range(self):
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

        #TODO: make sure these are valid values...
        #keep the dates without minute info, and just keep the minutes as integers, which is easier
        date_start = datetime.datetime(query["rangestart"]["year"], query["rangestart"]["month"], query["rangestart"]["day"])
        date_end = datetime.datetime(query["rangeend"]["year"], query["rangeend"]["month"], query["rangeend"]["day"])

        query_minute_start = query["rangestart"]["hour"] * 60 + query["rangestart"]["minute"]
        query_minute_end = query["rangeend"]["hour"] * 60 + query["rangeend"]["minute"]

        range_in_days = 1 + int((date_end - date_start) / datetime.timedelta(days=1))

        #use minutestart when we are reading the first file, use minuteend when we are reading the last file
        for f in filters:
            if(f in self.config["filters"]):
                for i in range(0, range_in_days):
                    date = date_start + datetime.timedelta(days=i)
                    folder_path = common.logger_output_path(date)
                    rsam_data = common.read_tremvlog_file(folder_path + common.generate_tremvlog_filename(date, f))

                    station_data = {}

                    for name in station_names:
                        if(name in self.config["station_names"] and name in rsam_results):
                            if(name not in station_data):
                                station_data[name] = []

                        file_minute_start = 0
                        file_minute_end = 60*24

                        if(range_in_days == 1):
                            file_minute_start = query_minute_start
                            file_minute_end = query_minute_end
                        elif(i == 0):#start
                            file_minute_start = query_minute_start
                        elif(i == range_in_days-1):#end
                            file_minute_end = query_minute_end

                        for j in range(minute_start, minute_end):
                            station_data[name].append(rsam_data[name][j])

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

        minute_of_day = 1440
        today = datetime.datetime.now()
        date = datetime.datetime(query["date"]["year"], query["date"]["month"], query["date"]["day"])

        if(date.year == today.year and date.month == today.month and date.day == today.day):
            minute_of_day = (today.hour * 60) + today.minute

        folder_path = common.logger_output_path(date)

        for f in filters:
            if(f in self.config["filters"]):
                tremvlog_filename = common.generate_tremvlog_filename(date, f)
                path = folder_path + tremvlog_filename
                rsam_results = common.read_tremvlog_file(path)

                station_data = {}

                for name in station_names:
                    if(name in self.config["station_names"] and name in rsam_results):
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

    #TODO: this shouldn't be required once we are hosting the api and the frontend at the same origin
    cherrypy.config.update({"tools.response_headers.on": True})
    cherrypy.config.update({"tools.response_headers.headers": [("Access-Control-Allow-Origin", "*")]})
    cherrypy.server.socket_host = "0.0.0.0"
    cherrypy.server.socket_port = int(sys.argv[1])
    cherrypy.quickstart(server())
