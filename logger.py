#Authors:
#Bethany Erin Vanderhoof
#Þórður Ágúst Karlsson

import os
import sys
import time
import schedule
import netCDF4 as netcdf
import obspy
from obspy.clients.seedlink.basic_client import Client as seedlinkClient
from obspy.clients.fdsn import Client as fdsnClient
from obspy import UTCDateTime
import common


""" Prints debugging info to stderr
"""
def debug_print(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)
    #print(*args, file=sys.stdout, **kwargs)


""" Apply lowpass filter to the data and downsample it from 100 points per minute
    to 20 per minute.
"""
def process_station_data(stations):
    result = stations.copy()

    #This is done in order to avoid the phase shift in the decimation process
    #It is only 10hz because otherwise we run in to aliasing, since we decimate after(nyquist-shannon theorem)
    result.filter("lowpass", freq=10.0, corners=2, zerophase=True)# this is super slow!
 
    #Down sample from 100hz to 20hz (100/5 = 20), no filter to avoid phase shift
    for trace in result:
        trace.decimate(5, no_filter=True)
 
    result.detrend("demean")

    return(result)


""" Iterate through each filter, applys it to each trace and adds the filtered
    trace to a list corresponding to the filter that the iteration is on.
"""
def apply_bandpass_filters(traces, filters):
    passbands = [{} for i in filters]
 
    for i in range(0, len(filters)):
        f = filters[i]
 
        for trace in traces:
            t = trace.copy()
            t.filter("bandpass", freqmin=float(f[0]), freqmax=float(f[1]), corners=4, zerophase=True)
            passbands[i][t.stats["station"]] = t

    return(passbands)


""" Applies rsam to a single trace.
    NOTE: This function assumes the given trace is 1 minute worth of data.
"""
def trace_average(trace):
    value_sum = 0
    pts_per_minute = int(trace.stats.sampling_rate * 60)

    for point in trace.data:
        value_sum += abs(point)

    return(value_sum/pts_per_minute)


""" Averages values for a given station over a minute and prepares the averages as
    an array of dictonaries whos length is equal to the number of filters provided.
    Each dictionary uses station names as keys and the corrsponding average is the value.
"""
def rsam_processing(per_filter_filtered_stations, filters, station_names, received_station_names):
    result = [{} for i in filters]

    for i in range(0, len(filters)):
        for name in station_names:
            result[i][name] = 0.0

    #Here we accumulate points
    for i in range(0, len(filters)):
        station_rsam_dict = result[i]
 
        for name in station_names:
            if(name in received_station_names):
                trace = per_filter_filtered_stations[i][name]
                average = trace_average(trace)
                station_rsam_dict[name] = average
            else:
                station_rsam_dict[name] = 0.0

    return(result)


""" Creates output files... (one per specified bandpass filter)
"""
def write_tremvlog_file(rsam_results, filters, station_names, timestamp):
    delimeter = " "
    path = common.logger_output_path(timestamp)

    if(os.path.exists(path) == False):
        os.makedirs(path)

    for filter_index in range(0, len(filters)):
        filename = common.generate_tremvlog_filename(timestamp, filters[filter_index])
        file_path = path + filename
        file_exists = os.path.exists(file_path)

        if(file_exists == False):
            f = open(file_path, "w")
            f.write("TIMESTAMP ")

            for i in range(0, len(station_names)):
                f.write(station_names[i])
                if(i == len(station_names)-1):
                    f.write("\n")
                else:
                    f.write(delimeter)

            minute_of_day = timestamp.minute + timestamp.hour * 60

            # Fill in empty values in the file if it isn't created at midnight.
            for i in range(0, minute_of_day):
                f.write(str(timestamp-60*(minute_of_day-i))+str(delimeter))
                for j in range(0, len(station_names)):
                    f.write(str(0.0))
                    if(j == len(station_names)-1):
                        f.write("\n")
                    else:
                        f.write(delimeter)
            f.close()

        tremvlog_file = open(file_path, "r")

        station_lists_differ = False # For added stations
        stations_removed = False # For removed stations
        station_names_in_file = tremvlog_file.readline().split(delimeter)
        station_names_in_file = station_names_in_file[1:] # Remove "TIMESTAMP" text at position 0
        
        for i in range(0, len(station_names_in_file)):
            station_names_in_file[i] = station_names_in_file[i].rstrip()

        # Reads most recent timestamp to back fill zeros below
        # [this line of code is here to read while file is already open]
        if(file_exists != False):
            last_line = tremvlog_file.readlines()[-1]
            last_timestamp = last_line[0:27]

            # Read list of specific timestamps for file rewrite with station addition/removal
            timestamps = common.read_tremvlog_timestamps(file_path)
        
        tremvlog_file.close()

        # For added stations:
        # Determine if there is difference between the station_names list we provide and the one in the file...
        added_stations = []
        i = 0
        for name in station_names:
            # Checks if config file station names are same as data file station names
            if(name not in station_names_in_file):
                station_lists_differ = True
                added_stations.append(name)
            else:
                pass
            i += 1

        # For removed stations:
        # Data and station header will remain in output file until next day.
        # Will not change column position in file to match config file order unless stations subsequently added.
        removed_stations = []
        i = 0
        for name in station_names_in_file:
            # Checks if station names in file are same as config file station names
            if(name not in station_names):
                stations_removed = True
                removed_stations.append(name)
            else:
                pass
            i += 1
        
        # Since they differ we will have to read the whole file in and re-write it:
        if(station_lists_differ == True):
            data_in_file = common.read_tremvlog_file(file_path) # AKA "result"
            minute_count = len(data_in_file[station_names_in_file[1]]) # At 1 to ignore TIMESTAMP + stat names (first line)            
            
            #Writes to an different file so that if the code crashes here the information isn't lost
            temp_path = path + "temp" + common.generate_tremvlog_filename(timestamp, filters[filter_index])
            output = open(temp_path, "w")

            #account for stations that are not present in the file and fill those with zeroes in dictionary
            for i in range(0, len(station_names)):
                name = station_names[i]

                if(name not in station_names_in_file):
                    station_names_in_file.insert(i, name)
                    data_in_file[name] = []

                    for j in range(0, minute_count):
                        data_in_file[name].append(0.0)

            output.write("TIMESTAMP ")
            for i in range(0, len(station_names)):
                output.write(station_names[i])
                
                if(i == len(station_names)-1):
                    output.write("\n")
                else:
                    output.write(delimeter)

            for i in range(0, minute_count):
                output.write(timestamps[i] + delimeter) # adds timestamp at beginning of lines in new file

                for j in range(0, len(station_names)):
                    name = station_names[j]
                    output.write(str(data_in_file[name][i]))

                    if(j == len(station_names)-1):
                        output.write("\n")
                    else:
                        output.write(delimeter)

            output.close()
            
            #swap files
            os.rename(file_path, file_path + "old")
            os.rename(temp_path, file_path)
            os.remove(file_path + "old")

        #do the actual appending of new data...
        output = open(file_path, "a")

        start_timestamp = str(timestamp) # string of UTC starttime

        if(file_exists != False):

            last_timestamp_min = int(last_timestamp[14:16]) # most recently written timestamp minute
            timestamp_min = int(start_timestamp[14:16]) # current timestamp minute to be written
            check_timestamp_min = last_timestamp_min + 1 # should be equal to timestamp_min if one minute has passed

            last_timestamp_hr = int(last_timestamp[11:13]) # most recently written timestamp hour
            timestamp_hr = int(start_timestamp [11:13]) # current timestamp hour to be written
            check_timestamp_hr = last_timestamp_hr + 1 # should be equal to timestamp_hr if one hour has passed

            #check difference between current timestamp and file timestamp 
            min_since_last_write = (timestamp_min - last_timestamp_min) + (timestamp_hr - last_timestamp_hr)*60 - 1
            

            # accounts for uninterrupted data progression
            if(timestamp_min == check_timestamp_min and timestamp_hr == last_timestamp_hr):
                pass
            
            # accounts for uninterrupted hour boundry
            elif(timestamp_min == 00 and last_timestamp_min == 59 and timestamp_hr == check_timestamp_hr):
                pass
            
            elif(timestamp_min != check_timestamp_min or timestamp_hr != check_timestamp_hr):
                i = min_since_last_write
                
                while i != 0:
                    output.write(str(timestamp - i*60) + str(delimeter))
                    i = i - 1
                    
                    for j in range(0, len(station_names_in_file)):
                        output.write(str(0.0))
                        
                        if(j == len(station_names_in_file)-1):
                            output.write("\n")
                        else:
                            output.write(delimeter)
                

        # Writes current RSAM data
        output.write(str(timestamp)+str(delimeter))
        for i in range(0, len(station_names_in_file)):
            
            name = station_names_in_file[i]
            result_dict = rsam_results[filter_index]
            
            if(name in result_dict):
                output.write(str(result_dict[name]))   
            else:
                output.write(str(0.0))
                
            if(i == len(station_names_in_file)-1):
                output.write("\n")
            else:
                output.write(delimeter)

        output.close()
        
    if(station_lists_differ == True):
        debug_print("Added stations: " + str(added_stations))
    if(stations_removed == True):
        debug_print("Removed stations: " + str(removed_stations))


""" Accumulate traces in a station that is found in a directory, handle gaps in
    data and append the output to a list of stations.
"""
def read_mseed_from_dir(path):
    stations = obspy.Stream()
    files = os.listdir(os.getcwd() + "/" + path)

    for f in files:
        station_in = obspy.read(path + "/" + f)
        trace_acc = station_in[0]

        #starts from one so we can splice the traces together with the + operator
        for i in range(1, len(station_in)):
            trace = station_in[i]
            trace_acc = trace_acc + trace

        #This creates a Stream object with one trace object that is gapless
        gapless_stream = trace_acc.split()
        stations.append(gapless_stream[0])

    return(stations)

#TODO: the name 'network' in the config file is ambiguous
class program:
    def __init__(self):
        self.config = common.read_tremv_config("config.json")
        self.seedlink = seedlinkClient(self.config["seedlink_address"], self.config["seedlink_port"], 5, False)
        self.fdsn = fdsnClient(self.config["fdsn_address"])

        #TODO: get response file every day?
        print("getting response inventory...")
        self.response_inventory = self.fdsn.get_stations(network=self.config["network"], station="*", level="response")#TODO station wildcard from config file?

    def main(self):
        self.config = common.read_tremv_config("tremv_config.json")
        fetch_starttime = UTCDateTime()
        data_starttime = fetch_starttime - 60

        stations_in_network = []

        #TODO: make this a little nicer
        fdsn_station_metadata = self.fdsn.get_stations(network=self.config["network"], station="*", starttime=data_starttime, endtime=fetch_starttime)
        for s in fdsn_station_metadata.networks[0]:
            if(s not in self.config["station_blacklist"]):
                stations_in_network.append(s.code)

        log_path = common.logger_output_path(fetch_starttime)

        if(os.path.exists(log_path) == False):
            os.makedirs(log_path)

        debug_print("\nFetch start time: " + str(fetch_starttime))
        debug_print("Data fetch duration: ", end="")

        received_station_waveforms = self.seedlink.get_waveforms(self.config["network"], self.config["station_wildcard"], self.config["location_wildcard"], self.config["selectors"], data_starttime, fetch_starttime)
        received_station_waveforms.remove_response(inventory=self.response_inventory)

        debug_print(str(UTCDateTime() - fetch_starttime))

        filters = self.config["filters"]
        rsam_st = UTCDateTime()

        pre_processed_stations = process_station_data(received_station_waveforms)
        per_filter_filtered_stations = apply_bandpass_filters(pre_processed_stations, filters)

        rsam_results = rsam_processing(per_filter_filtered_stations, filters, stations_in_network, received_station_names)

        debug_print("Rsam calculation duration: " + str(UTCDateTime() - rsam_st))

        write_tremvlog_file(rsam_results, filters, stations_in_network, data_starttime)

        datestr = str(data_starttime.year) + "." + str(data_starttime.month) + "." + str(data_starttime.day)
        debug_print("Wrote to files " + datestr + " at: " + str(UTCDateTime()))
        debug_print("Sleeping until next minute...")

if __name__ == "__main__":
    p = program()
    p.main()

    """
    scheduler = schedule.Scheduler()
    scheduler.every().minute.at(":00").do(p.main)

    while(True):
        scheduler.run_pending()
        time.sleep(1)
    """
