#Author: Þórður Ágúst Karlsson

import cherrypy
import os
import sys
import csv
import math
import datetime
import time
import common
import threading

import schedule
import obspy
from obspy.clients.fdsn import Client as fdsnClient
from obspy import UTCDateTime

"""
TODO:
    *   api fyrir cataloginn
"""

class api(object):
    def __init__(self):
        self.config = common.config("config.json")
        self.fdsn = fdsnClient(self.config["fdsn_address"])
        self.cached_station_metadata = {}
        self.exit = False

        self.cacheStations()

        schedule_thread = threading.Thread(target=self.scheduled_tasks)
        schedule_thread.name = "API_SCHEDULE_THREAD"
        schedule_thread.start()

    def scheduled_tasks(self):
        scheduler = schedule.Scheduler()
        scheduler.every(10).minutes.do(self.cacheStations)

        while(True):
            if(self.exit):
                sys.exit()
            scheduler.run_pending()
            time.sleep(1)

    def stop_handler(self):
        self.exit = True

    def dataResponse(self, filters):
        result_array = []

        for f in filters:
            result_array.append({"stations": {}, "filter": str(f[0]) + " - " + str(f[1])})

        return result_array
    
    def getNetworkStations(self, date_start, date_end):
        network_inv = self.fdsn.get_stations(network=self.config["network"], station="*", starttime=date_start, endtime=date_end)
        result = {}

        for s in network_inv[0]:
            result[s.code] = {}
            result[s.code]["latitude"] = s.latitude
            result[s.code]["longitude"] = s.longitude
            result[s.code]["site"] = s.site.name

        return result

    def cacheStations(self):
        self.cached_station_metadata = self.getNetworkStations(datetime.datetime.today(), datetime.datetime.today())

    def sortedStationNames(self):
        return sorted(list(self.cached_station_metadata.keys()))

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def station_metadata(self):
        return self.cached_station_metadata

    #TODO: HTTP error ef bilið er ekki viðeigandi
    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def stations_in_range(self):
        self.config.reload()

        query = cherrypy.request.json

        date_start = datetime.datetime(query["rangestart"]["year"], query["rangestart"]["month"], query["rangestart"]["day"])
        date_end = datetime.datetime(query["rangeend"]["year"], query["rangeend"]["month"], query["rangeend"]["day"])

        return self.getNetworkStations(date_start, date_end)

    """
    returns list of available stations and filters
    """
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def current_configuration(self):
        self.config.reload()
        return {"stations": self.sortedStationNames(), "filters": self.config["filters"]}
    
    #TODO:  þegar við erum ekki lengur að lesa úr csv skrá væri kannski hægt að gera eitthvað betra en að lesa
    #       alltaf skrána sem geymir öll gögnin bara til að ná í nýjustu mín?
    """
    Það sem plot forritið gerir er u.þ.b þetta: ná í metadata(var held ég filter og listi af stöðvum sem eru í boði)

    Síðan nær það í síðustu 24 tíma með range request

    Eftir það bíður forritið eftir því að maður fylli út þær stöðvar sem maður vill og ýti á form submit takkan og þá
    fer það í fyrirspurnar lykkju sem sækir nýjustu gagnapunktana á mín fresti
    """

    """ Reads the newest tremvlogs based on provided filters, and returns the latest
        values for each station that was asked for.
    """
    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def latest(self):
        self.config.reload()

        available_stations = self.sortedStationNames()
        stations = available_stations
        filters = self.config["filters"]
        query = cherrypy.request.json

        if("stations" in query):
            if(len(query["stations"]) > 0):
                stations = query["stations"]

                print(stations)
                for s in stations:
                    if(s not in available_stations):
                        raise cherrypy.HTTPError(406)#Not Acceptable

        #TODO: error fyrir filter ef hann er ekki til
        if("filters" in query):
            if(len(query["filters"]) > 0):
                filters = query["filters"]

        do_log_transform = False
        if("do_log_transform" in query):
            do_log_transform = query["do_log_transform"]

        result = self.dataResponse(filters)

        #NOTE: This is necessary because javascript interprets 1.0 an integer(client asks for available filters, )
        for i in range(0, len(filters)):
            filters[i][0] = float(filters[i][0])
            filters[i][1] = float(filters[i][1])

        #This is so the program doesn't skip the last minute of the day when datetime.datetime.now() would report the next day
        most_recent_timestamp = datetime.datetime.now() - datetime.timedelta(minutes=1)

        date = datetime.datetime(most_recent_timestamp.year, most_recent_timestamp.month, most_recent_timestamp.day)
        folder_path = common.logger_output_path(date)

        #TODO: print out the requested minute(the timestamp in the file...)
        for i in range(0, len(filters)):
            f = filters[i]
            if(f in self.config["filters"]):
                tremvlog_filename = common.generate_tremvlog_filename(date, f, "z")
                path = folder_path + tremvlog_filename
                rsam_data = common.read_tremvlog_file(path)

                for name in stations:
                    latest_value = 0.0
                    if(name in rsam_data):
                        latest_value = rsam_data[name][-1]

                        if(do_log_transform):
                            if(latest_value > 0.0):
                                latest_value = math.log(latest_value)*1000

                    result[i]["stations"][name] = latest_value

        return(result)


    """ Reads tremvlogs based on provided date and filters, and returns the stations
        as a json.
    """
    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def range(self):
        self.config.reload()

        filters = self.config["filters"]
        query = cherrypy.request.json

        #TODO: Error ef filter er ekki til
        if("filters" in query):
            if(len(query["filters"]) > 0):
                filters = query["filters"]

        do_log_transform = False
        if("do_log_transform" in query):
            do_log_transform = query["do_log_transform"]

        result = self.dataResponse(filters)

        #NOTE: need to do this because javascript interprets 1.0 from the metadata response as an integer
        for i in range(0, len(filters)):
            filters[i][0] = float(filters[i][0])
            filters[i][1] = float(filters[i][1])

        #TODO: make sure these are valid values...
        #keep the dates without minute info, and just keep the minutes as integers, which is easier
        date_start = datetime.datetime(query["rangestart"]["year"], query["rangestart"]["month"], query["rangestart"]["day"])
        date_end = datetime.datetime(query["rangeend"]["year"], query["rangeend"]["month"], query["rangeend"]["day"])

        available_stations = self.getNetworkStations(date_start, date_end)
        stations = available_stations

        if("stations" in query):
            if(len(query["stations"]) > 0):
                stations = query["stations"]
                for s in stations:
                    if(s not in available_stations):
                        raise cherrypy.HTTPError(406)#Not Acceptable

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

            #use minutestart when we are reading the first file, use minuteend when we are reading the last file
            for j in range(0, len(filters)):
                f = filters[j]

                if(f in self.config["filters"]):
                    folder_path = common.logger_output_path(date)
                    filename = folder_path + common.generate_tremvlog_filename(date, f, "z")
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
                                for name in stations:
                                    if(name in rsam_data):
                                        for k in range(0, len(rsam_data[name])):
                                            if(rsam_data[name][k] > 0.0):
                                                rsam_data[name][k] = math.log(rsam_data[name][k])*1000

                    if(file_read == False):
                        print("Could not find requested data.")

                    for name in list(available_stations.keys()):
                        if(name in rsam_data):
                            if(name not in result[j]["stations"]):
                                result[j]["stations"][name] = []

                            range_end = min(file_minute_end, len(rsam_data[name]))

                            for k in range(file_minute_start, range_end):
                                result[j]["stations"][name].append(rsam_data[name][k])

        return(result)

#TODO: templating?
class catalog(object):
    @cherrypy.expose
    def default(self, *args):
        path = "tremor_catalog/"
        date = datetime.date.today()
        year = date.year
        month = date.month

        #You can append a subpath to the url with /year/month if you want to browse for a specific catalog(plus it doesn't reload)
        if(len(args) > 0):
            year = int(args[0])
            month = int(args[1])

        path += str(year) + "/" + str(year) + "." + str(month) + "_tremor_catalog.txt"

        with open(path) as f:
            catalog = csv.DictReader(f, delimiter="\t")

            html = """
            <html>
            <head>
                <style>
                body {
                    font-family: arial;
                    margin: 0 auto;
                    max-width: 1024px;
                }
                table {
                    table-layout: fixed;
                    width: 100%;
                    overflow-wrap: break-word;
                    border-collapse: collapse;
                    border: 2px solid;
                    text-align: center;
                }

                thead th:nth-child(1) {
                    width: 6%;
                }

                thead th:nth-child(2) {
                    width: 24%;
                }

                thead th:nth-child(3) {
                    width: 8%;
                }

                tbody tr:nth-child(odd) {
                    background-color: #EAEAEA;
                }

                td, th {
                    padding: 10px;
                }

                new_event {
                    background-color: #FFC8C8 !important;
                }


                </style>
                <script type="text/javascript">
                function createReloadTimer(sec) {
                    return setInterval(function() {window.location.reload(true)}, 1000*sec);
                }

                let reload_timer = null;
                if(window.location.pathname === "/catalog" || window.location.pathname === "/catalog/") {
                    let reload_timer = createReloadTimer(60);

                    document.onscroll = function() {
                        clearInterval(reload_timer);
                        reload_timer = createReloadTimer(60);
                        console.log("timer reset");
                    }
                }
                </script>
            </head>
            <body>
            """
            html += "<table>"
            html += "<thead>"
            html += "<tr>"
            for k in catalog.fieldnames:
                html += "<th>" + k + "</th>"
            html += "</tr>"
            html += "</thead>"

            lines = []

            for l in catalog:
                lines.append(l)

            for i in range(0, len(lines)):
                index = len(lines) - i - 1
                timestamp = common.parse_isoformat_to_datetime(lines[index]["TriggerTime"])
                delta = datetime.datetime.now() - timestamp

                if(int(delta.total_seconds()) // 60 <= 10):
                    html += "<tr class='new_event'>"
                else:
                    html += "<tr>"

                for k in catalog.fieldnames:
                    html += "<td>" + lines[index][k] + "</td>"
                html += "</tr>"

            html += "</table>"

            html += "</body></html>"

            return html

class frontend(object):
    @cherrypy.expose
    def default(self, *args):
        config = cherrypy.request.app.config
        root_dir = config["/"]["tools.staticdir.root"]
        filename = config["/"]["tools.staticdir.index"]
        return cherrypy.lib.static.serve_file(open(os.path.join(root_dir, filename)))

if(__name__ == "__main__"):
    cherrypy.config.update({
            "server.socket_host": "0.0.0.0",
            "log.error_file": "server_errors.log"
        })

    api_object = api()
    cherrypy.engine.subscribe("stop", api_object.stop_handler)

    cherrypy.tree.mount(api_object, "/api")
    cherrypy.tree.mount(catalog(), "/catalog")
    cherrypy.tree.mount(frontend(), "/plot", config="plot.config")

    if hasattr(cherrypy.engine, 'block'):
        # 3.1 syntax
        cherrypy.engine.start()
        cherrypy.engine.block()
    else:
        # 3.0 syntax
        cherrypy.server.quickstart()
        cherrypy.engine.start()
