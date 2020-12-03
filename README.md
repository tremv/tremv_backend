# Tremv Backend
This is a pre-release version of the Tremv backend. It consists of two programs, tremv_logger.py and tremv_server.py.
Tremv Logger generates log files each day, reporting seismic activity averaged over 1 minute.
Tremv Server distributes this data via HTTP in json format, based on requests to it.

# Tremv Logger
The Tremv Logger connects to a Seedlink server and gathers raw data from the station network over the past minute.
It then applies a 20HZ low-pass filter, decimates and demeans the data, and finally applies bandpass filters provided
by the user. It then averages the filtered station data and writes each station to a csv file.
It relies on a configuration file, tremv_config.json, for the Seedlink address, network name, filters and station names
to write out to file, as the seedlink connection does not always give back all stations that are available in the system.

# Tremv Server

# Setup 
tremv_logger.py requires obspy to run, simply install it with pip like so: `pip3 install obspy` 
