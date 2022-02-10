#!/bin/bash
if (( $# != 1 )); then
	echo "you need to provide a server port"
else
	if ! screen -list | grep -q "tremv_logger$1"; then
		screen -S "tremv_logger$1" -dm python3 logger.py
	fi
	if ! screen -list | grep -q "tremv_server$1"; then
		screen -S "tremv_server$1" -dm python3 server.py $1
	fi
fi
