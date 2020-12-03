#!/bin/bash
if ! screen -list | grep -q "tremv_logger"; then
	screen -S tremv_logger -dm python3 tremv_logger.py
fi
if ! screen -list | grep -q "tremv_server"; then
	screen -S tremv_server -dm python3 tremv_server.py
fi
