#Author: Þórður Ágúst Karlsson

import cherrypy
import os
import sys
import math
import datetime
import common
import config
import pytremlog#@IMO stuff
import obspy
from obspy.clients.fdsn import Client as fdsnClient
from obspy import UTCDateTime

class api(object):
    def __init__(self):
        self.standard_filters = [[0.5, 1.0], [1.0, 2.0], [2.0, 4.0]]
        self.config = config.config("config.json")#TODO: environment variable
        self.fdsn = fdsnClient(self.config["fdsn_address"])
        self.response_inv_filename = "inv.xml"#TODO: environment variable
        self.response_inv = None

        #we just need to do this once so we can get response info for old data
        print("Getting response_inv file...")
        if(os.path.exists(self.response_inv_filename)):
            self.response_inv = obspy.read_response_inv(self.response_inv_filename)
        else:
            inv = fdsn.get_stations(network=self.config["network"], station="*", level="response")
            inv.write(self.response_inv_filename, format="STATIONXML")
            self.response_inv = inv

    def jsonResult(self, filters):
        result = {}
        result["timestamps"] = []
        result["station_names"] = []
        result["data"] = [{} for x in filters]

        for i in range(0, len(filters)):
            result["data"][i]["filter"] = filters[i]
            result["data"][i]["stations"] = {}

        return result


    """ Return list of station names and a list of filters
    """
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def metadata(self):
        self.config.reload()
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

        self.config.reload()

        station_names = self.config["station_names"]
        filters = self.config["filters"]

        if("station_names" in query):
            if(len(query["station_names"]) > 0):
                station_names = query["station_names"]

        if("filters" in query):
            if(len(query["filters"]) > 0):
                filters = query["filters"]

        do_log_transform = False
        if("do_log_transform" in query):
            do_log_transform = query["do_log_transform"]

        result = self.jsonResult(filters)

        #NOTE: need to do this because javascript interprets 1.0 from the metadata response as an integer
        for i in range(0, len(filters)):
            filters[i][0] = float(filters[i][0])
            filters[i][1] = float(filters[i][1])

        #NOTE: Reading the entire file in for now. Prehaps this can be made more efficient via seeking in the file or something...
        date_now = datetime.datetime.now()
        #@Robustness:   if the request comes in at some minute timeframe and the data point is not ready
        #               (that is if we count the lines in the file and they are == the (minute of request - 1)),
        #               wait until it is ready and then send it

        #what minute should this be? might be off by one if not careful
        date = datetime.datetime(date_now.year, date_now.month, date_now.day,)
        folder_path = common.logger_output_path(date)

        for i in range(0, len(filters)):
            f = filters[i]
            if(f in self.config["filters"]):
                tremvlog_filename = common.generate_tremvlog_filename(date, f)
                path = folder_path + tremvlog_filename
                rsam_data = common.read_tremvlog_file(path)

                for name in station_names:
                    latest_value = 0.0
                    if(name in rsam_data):
                        latest_value = rsam_data[name][-1]

                        if(do_log_transform):
                            if(latest_value > 0.0):
                                latest_value = math.log(latest_value)*1000

                    result["data"][i]["stations"][name] = latest_value

        return(result)


    """ Reads tremvlogs based on provided date and filters, and returns the stations
        as a json.
    """
    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def range(self):
        query = cherrypy.request.json

        self.config.reload()

        station_names = self.config["station_names"]
        filters = self.config["filters"]

        if("station_names" in query):
            if(len(query["station_names"]) > 0):
                station_names = query["station_names"]

        if("filters" in query):
            if(len(query["filters"]) > 0):
                filters = query["filters"]

        do_log_transform = False
        if("do_log_transform" in query):
            do_log_transform = query["do_log_transform"]

        result = self.jsonResult(filters)

        #NOTE: need to do this because javascript interprets 1.0 from the metadata response as an integer
        for i in range(0, len(filters)):
            filters[i][0] = float(filters[i][0])
            filters[i][1] = float(filters[i][1])

        #TODO: make sure these are valid values...
        #keep the dates without minute info, and just keep the minutes as integers, which is easier
        date_start = datetime.datetime(query["rangestart"]["year"], query["rangestart"]["month"], query["rangestart"]["day"])
        date_end = datetime.datetime(query["rangeend"]["year"], query["rangeend"]["month"], query["rangeend"]["day"])

        #NOTE: for some reason "hour" and "minute" is a string?
        query_minute_start = int(query["rangestart"]["hour"]) * 60 + int(query["rangestart"]["minute"])
        query_minute_end = int(query["rangeend"]["hour"]) * 60 + int(query["rangeend"]["minute"])

        if(date_start > date_end):
            return(result)

        if(date_start == date_end):
            if(query_minute_start > query_minute_end):
                return(result)

        range_in_days = 1 + int((date_end - date_start) / datetime.timedelta(days=1))

        for i in range(0, range_in_days):
            date = date_start + datetime.timedelta(days=i)
            file_minute_start = 0
            file_minute_end = 60*24

            if(range_in_days == 1):
                file_minute_start = query_minute_start
                file_minute_end = query_minute_end+1#NOTE: +1 because it is up to and including the minute
            elif(i == 0):#start
                file_minute_start = query_minute_start
            elif(i == range_in_days-1):#end
                file_minute_end = query_minute_end+1#NOTE: +1 because it is up to and including the minute
            
            date_minute_increment = date + datetime.timedelta(minutes=file_minute_start)

            print("start: " + str(file_minute_start) + ", end: " + str(file_minute_end))
            for j in range(file_minute_start, file_minute_end):
                result["timestamps"].append(date_minute_increment.isoformat())
                date_minute_increment = date_minute_increment + datetime.timedelta(minutes=1)

            #use minutestart when we are reading the first file, use minuteend when we are reading the last file
            for j in range(0, len(filters)):
                f = filters[j]

                if(f in self.config["filters"]):
                    folder_path = common.logger_output_path(date)
                    filename = folder_path + common.generate_tremvlog_filename(date, f)
                    file_read = False

                    if(os.path.exists(filename)):
                        file_timestamp = os.stat(filename).st_mtime

                        sec_in_day = 60*60*24
                        midnight_timestamp = int(file_timestamp) // sec_in_day * sec_in_day#integer division with sec in day to get the days since epoch, then multiply back to get the timestamp at midnight

                        #if the file wasn't created within 30min from midnight, we default to the tremlogs
                        if(file_timestamp - midnight_timestamp < 60*30):
                            file_read = True
                            rsam_data = common.read_tremvlog_file(filename)
                            if(do_log_transform):
                                for name in station_names:
                                    if(name in rsam_data):
                                        for k in range(0, len(rsam_data[name])):
                                            if(rsam_data[name][k] > 0.0):
                                                rsam_data[name][k] = math.log(rsam_data[name][k])*1000

                    if(file_read == False):
                        tremlog = pytremlog.get(date.year, date.month, date.day, log_transform=do_log_transform)
                        #TODO: maybe not the most robust thing...
                        std_filter_index = self.standard_filters.index(f)
                        rsam_data = tremlog.values_z[std_filter_index]

                    for name in station_names:
                        if(name in rsam_data):
                            if(name not in result["station_names"]):
                                result["station_names"].append(name)

                            if(name not in result["data"][j]["stations"]):
                                result["data"][j]["stations"][name] = []

                            range_end = min(file_minute_end, len(rsam_data[name]))

                            for k in range(file_minute_start, range_end):
                                result["data"][j]["stations"][name].append(rsam_data[name][k])

        return(result)


class frontend(object):
    def __init__(self):
        pass

#TODO: support querying for an arbritrary date range, not just a specific date
if(__name__ == "__main__"):
    if(len(sys.argv) == 1):
        print("Server port argument is required.")
        sys.exit()

    cherrypy.server.socket_host = "0.0.0.0"
    cherrypy.server.socket_port = int(sys.argv[1])
    cherrypy.tree.mount(frontend(), "/plot", config="plot.config")
    cherrypy.tree.mount(frontend(), "/request", config="request.config")
    cherrypy.tree.mount(api(), "/api")

    if hasattr(cherrypy.engine, 'block'):
        # 3.1 syntax
        cherrypy.engine.start()
        cherrypy.engine.block()
    else:
        # 3.0 syntax
        cherrypy.server.quickstart()
        cherrypy.engine.start()
