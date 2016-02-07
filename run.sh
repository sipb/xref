#!/bin/bash

LOGDIR=~/logs
LOCKFILE=~/update.lock

export XREF_CONFIG=~/config
export XREF_SOURCES=/var/opengrok/src

lockfile "$LOCKFILE"

LOGFILE="${LOGDIR}/run_$(date +%Y-%m-%d_%H.%M.%S).log"
python update.py > "$LOGFILE" 2>&1

zcrypt -c xref-spew -i run < "$LOGFILE"

rm -f "$LOCKFILE"
