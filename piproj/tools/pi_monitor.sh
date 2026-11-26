#!/usr/bin/env bash
# Logs Pi temperature, under-voltage flag, load, CPU frequency and Ethernet rate every INTERVAL seconds.
# The Pi has no current/power sensor: this is indirect. The Pi clock is unreliable, so the PC adds the timestamps.
# Usage: PI_HOST=<pi address> pi_monitor.sh [SECONDS] [LABEL]      output: pimon-out/pimon-LABEL-*.csv
# Optional: PI_KEY (private key, default ~/.ssh/id_ed25519), PI_SSH_OPTS (extra ssh options).
set -u
host=${PI_HOST:?set PI_HOST to the Pi address}; secs=${1:-120}; label=${2:-run}
key=${PI_KEY:-$HOME/.ssh/id_ed25519}
interval=2
out="$(dirname "$0")/pimon-out/pimon-$label-$(date +%Y%m%d-%H%M%S).csv"
mkdir -p "$(dirname "$out")"
echo "time,temp_c,volt_flag,load1,cpu_khz,eth_rx_kBps,eth_tx_kBps" | tee "$out"
# shellcheck disable=SC2086  (PI_SSH_OPTS is meant to be split into words)
timeout "$secs" ssh -T -i "$key" -o IdentitiesOnly=yes -o BatchMode=yes -o LogLevel=ERROR ${PI_SSH_OPTS:-} "root@$host" '
  hw0=$(for d in /sys/class/hwmon/*; do [ "$(cat $d/name)" = cpu_thermal ] && echo $d; done)
  hw1=$(for d in /sys/class/hwmon/*; do [ "$(cat $d/name)" = rpi_volt ] && echo $d; done)
  f=/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
  set -- $(grep "eth0:" /proc/net/dev | tr ":" " ")
  prx=$2; ptx=${10}
  sleep '"$interval"'
  while true; do
    t=$(( $(cat $hw0/temp1_input) / 100 )); t="$((t/10)).$((t%10))"
    v=$(cat $hw1/in0_lcrit_alarm)
    l=$(cut -d" " -f1 /proc/loadavg)
    c=NA; [ -r $f ] && c=$(cat $f)
    set -- $(grep "eth0:" /proc/net/dev | tr ":" " ")
    rx=$2; tx=${10}
    echo "$t,$v,$l,$c,$(( (rx-prx)/'"$interval"'/1000 )),$(( (tx-ptx)/'"$interval"'/1000 ))"
    prx=$rx; ptx=$tx
    sleep '"$interval"'
  done' 2>/dev/null | while IFS= read -r line; do echo "$(date +%T),$line" | tee -a "$out"; done
echo "saved: $out" >&2
