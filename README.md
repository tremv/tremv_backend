# Tremv Backend
This is a pre-release version of the Tremv backend. It consists of two programs, tremv_logger.py and tremv_server.py.
Tremv Logger generates log files each day, reporting seismic activity averaged over 1 minute.
Tremv Server distributes this data in json format via HTTP, based on requests to it.

# Tremv Logger
The Tremv Logger connects to a Seedlink server and gathers raw data from the station network over the past minute.
It then applies a 20HZ low-pass filter, decimates and demeans the data, and finally applies bandpass filters provided
by the user. It then averages the filtered station data and writes each station to a csv-like file.
It relies on a configuration file, tremv_config.json, for the Seedlink address, network name and filters to write out to file.
It also relies on a list of station names found in the configuration file, as the seedlink connection does not always give back all stations that are available in the system.
The files are written out to the folder `logger_output` and are classified by bandpass filter.

# Tremv Server
The Tremv Server responds to HTTP requests made to it and returns data back as JSON. It also relies on the tremv_config.json file, but only for filters and station names.

# Setup
tremv_logger.py requires ObsPy and tremv_server.py requires CherryPy. These packages are available via `pip`.

tremv_logger.py:
```
pip3 install obspy
```
tremv_server.py:
```
pip3 install cherrypy
``` 

Before either program is started, a `tremv_config.json` file must be present. 

Example:
```
{
	"server": "rtserve.iris.washington.edu",
	"port": 18000,
	"network": "YN",
	"filters": [[0.5, 1.0], [1.0, 2.0], [2.0, 4.0]],
	"station_names": []
}
```

All parameters shown are required. The array in "station_names" must be filled with the stream names you want that are available in the network.
Once this file has been created, the programs can be start however the user desires. The programs are intended to run as daemons, but currently
there is no nice way of doing so without the use of external tool. We recommend using `screen -S session_name` where session_name is the name of
the session, and then running the program with the python interpreter.
