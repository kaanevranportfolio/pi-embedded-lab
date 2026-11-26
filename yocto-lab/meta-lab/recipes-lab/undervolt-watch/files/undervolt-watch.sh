#!/bin/sh
# Watches the Raspberry Pi firmware under-voltage flag exposed by the
# raspberrypi-hwmon driver (hwmon device "rpi_volt", file in0_lcrit_alarm)
# and writes changes to the journal (stdout).
#
# Settings (via /etc/default/undervolt-watch):
#   INTERVAL=5          seconds between reads
#   SHUTDOWN_AFTER=0    poweroff after this many consecutive alarm reads; 0 = never
#   ALARM_FILE=         override the flag file (used for testing without real under-voltage)

INTERVAL="${INTERVAL:-5}"
SHUTDOWN_AFTER="${SHUTDOWN_AFTER:-0}"

find_alarm_file() {
    for d in /sys/class/hwmon/hwmon*; do
        [ -r "$d/name" ] || continue
        if [ "$(cat "$d/name")" = "rpi_volt" ] && [ -r "$d/in0_lcrit_alarm" ]; then
            echo "$d/in0_lcrit_alarm"
            return 0
        fi
    done
    return 1
}

if [ -n "$ALARM_FILE" ]; then
    FILE="$ALARM_FILE"
else
    FILE=""
    tries=0
    while [ -z "$FILE" ] && [ "$tries" -lt 30 ]; do
        FILE="$(find_alarm_file)" || { tries=$((tries + 1)); sleep 2; }
    done
    if [ -z "$FILE" ]; then
        echo "undervolt-watch: no rpi_volt hwmon device found (is raspberrypi-hwmon loaded?)"
        exit 1
    fi
fi

echo "undervolt-watch: watching $FILE every ${INTERVAL}s (shutdown after: ${SHUTDOWN_AFTER})"

last=""
bad=0
while true; do
    val="$(cat "$FILE" 2>/dev/null)"
    if [ "$val" != "$last" ]; then
        if [ "$val" = "1" ]; then
            echo "undervolt-watch: UNDER-VOLTAGE flag set"
        else
            echo "undervolt-watch: voltage normal (flag=$val)"
        fi
        last="$val"
    fi
    if [ "$val" = "1" ]; then
        bad=$((bad + 1))
        if [ "$SHUTDOWN_AFTER" -gt 0 ] && [ "$bad" -ge "$SHUTDOWN_AFTER" ]; then
            echo "undervolt-watch: flag set for $bad reads, powering off"
            systemctl poweroff
            exit 0
        fi
    else
        bad=0
    fi
    sleep "$INTERVAL"
done
