#!/usr/bin/env bash
set -euo pipefail
[[ $EUID == 0 ]] || exit 1
if [[ -f /etc/cpu-control/cpu_control.py ]]; then
    systemctl start cpu-control.service
    busctl --timeout=75 call org.local.CpuControl1 /org/local/CpuControl1 org.local.CpuControl1 RestoreAll
fi
systemctl disable --now cpu-control.service
rm -f /etc/cpu-control/cpu_control.py /etc/cpu-control/org.local.CpuControl1.xml
rmdir /etc/cpu-control 2>/dev/null || true
rm -f /etc/systemd/system/cpu-control.service /etc/dbus-1/system.d/org.local.CpuControl1.conf
rm -f /etc/polkit-1/actions/org.local.cpu-control.policy /etc/polkit-1/rules.d/49-cpu-control.rules
rm -f /run/cpu-control/topology.json /run/cpu-control/topology.tmp
rmdir /run/cpu-control 2>/dev/null || true
systemctl daemon-reload
busctl call org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus ReloadConfig
