# Tremv Backend
This is a pre-release version of the Tremv backend. It consists of two programs, tremv_logger.py and tremv_server.py.
Tremv Logger generates log files each day, reporting seismic activity averaged over 1 minute.
Tremv Server distributes this data in json format via HTTP, based on requests to it.

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
there is no nice way of doing so without the use of external tools. We provide a bash script, `tremv_run.sh`, which relies on the program `screen`
to run the programs as daemons. Providing the script with a server port as an argument is neccessary for the server to run.

# Tremv Logger
The Tremv Logger connects to a Seedlink server and gathers raw data from the station network over the past minute.
It then applies a 20HZ low-pass filter, decimates and demeans the data, and finally applies bandpass filters provided
by the user. It then averages the filtered station data and writes each station to a csv-like file.
It relies on a configuration file, tremv_config.json, for the Seedlink address, network name and filters to write out to file.
It also relies on a list of station names found in the configuration file, as the seedlink connection does not always give back all stations that are available in the system.
The files are written out to the folder `logger_output` and are classified by bandpass filter.

# Tremv Server
The Tremv Server responds to HTTP requests made to it and returns data back as JSON. It also relies on the tremv_config.json file, but only for filters and station names.

## API
The server uses HTTP POST and GET requests to provide data to the user. The following request url strings are supported:

### station_names [GET]
Returns a list of stations that are available on the server.

Example response:
```
["gri", "hrn", "sig", "hla", "gra", "lei", "bre", "hed", "gil", "dim", "ski", "gha", "kvo", "ren", "mel", "grs"]
```

### filters [GET]
Returns a list of the bandpass filters available in the system.

Example response:
```
[[0.5, 1.0], [1.0, 2.0], [2.0, 4.0]]
```

### latest [POST]
Returns a list of dictionaries based on request parameters, with the latest data points. Each dictionary in the list of dictionaries corresponds to passband filters that were requested. 
The keys in each the dictionary are stations that were requested.

Example request:
```
{
	"station_names": ["gri", "gra", "ren", "skr"],
	"filters": [[0.5, 1.0], [1.0, 2.0]]
}
```
Both entries in the request object are optional, in which case all filters or all stations are included in the response.

Example response:
```
[
	{
		"filter": [0.5, 1.0],
		"stations": {
			"gri": 123.5453,
			"gra": 203.1168,
			"ren": 198.5443,
			"skr": 242.4200
		}
	},
	{
		"filter": [1.0, 2.0],
		"stations": {
			"gri": 223.6853,
			"gra": 173.2968,
			"ren": 218.1118,
			"skr": 201.6900
		}
	}
]
```

### date [POST]
This request is work similar to the `latest` request, except you provide a date parameter.
It then returns a the data for the whole day, in a similar response format to the `latest` request.

Example request:
```
{
	"date": {"year": 2020, "month": 11, "day": 26}
	"station_names": ["gri", "gra", "ren", "skr"],
	"filters": [[0.5, 1.0], [1.0, 2.0]]
}
```
Note that the date entry in the request body is **required**.

Example response:
```
[
	{
		"filter": [0.5, 1.0],
		"stations": {
			"gri": [123.5453, ...],
			"gra": [203.1168, ...],
			"ren": [198.5443, ...],
			"skr": [242.4200, ...]
		}
	},
	{
		"filter": [1.0, 2.0],
		"stations": {
			"gri": [223.6853, ...],
			"gra": [173.2968, ...],
			"ren": [218.1118, ...],
			"skr": [201.6900, ...]
		}
	}
]
```
