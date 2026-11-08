#!/bin/bash
# Runs inside the Db2 container after the instance is created: an OS user for the read-only question box.
id aqreader >/dev/null 2>&1 || useradd -M aqreader
echo "aqreader:${DB2_READER_PASSWORD}" | chpasswd
