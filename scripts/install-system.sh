#!/usr/bin/env bash
set -euo pipefail
[[ $EUID == 0 && $# == 2 ]] || { echo 'Use scripts/install.sh.' >&2; exit 1; }
project=$1
desktop_user=$2
[[ $desktop_user =~ ^[a-z_][a-z0-9_-]*\$?$ ]] || { echo 'Invalid local user name.' >&2; exit 1; }
id "$desktop_user" >/dev/null
install -d -o root -g root -m 0755 /etc/cpu-control /etc/polkit-1/actions
install -o root -g root -m 0644 "$project/helper/cpu_control.py" "$project/helper/org.local.CpuControl1.xml" /etc/cpu-control/
install -o root -g root -m 0644 "$project/systemd/cpu-control.service" /etc/systemd/system/cpu-control.service
install -o root -g root -m 0644 "$project/systemd/org.local.CpuControl1.conf" /etc/dbus-1/system.d/org.local.CpuControl1.conf
install -o root -g root -m 0644 "$project/polkit/org.local.cpu-control.policy" /etc/polkit-1/actions/org.local.cpu-control.policy
rule=$(mktemp)
trap 'rm -f "$rule"' EXIT
sed "s/@USER@/$desktop_user/g" "$project/polkit/49-cpu-control.rules.in" > "$rule"
install -o root -g root -m 0644 "$rule" /etc/polkit-1/rules.d/49-cpu-control.rules
command -v restorecon >/dev/null && restorecon -RF /etc/cpu-control /etc/systemd/system/cpu-control.service /etc/dbus-1/system.d/org.local.CpuControl1.conf /etc/polkit-1/actions/org.local.cpu-control.policy /etc/polkit-1/rules.d/49-cpu-control.rules
systemctl daemon-reload
busctl call org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus ReloadConfig
for (( attempt=0; attempt<20; attempt++ )); do
    if pkaction --action-id org.local.cpu-control.configure >/dev/null 2>&1; then break; fi
    sleep 0.2
done
# polkit cannot watch an action directory that did not exist when it started.
if ! pkaction --action-id org.local.cpu-control.configure >/dev/null 2>&1; then
    systemctl restart polkit.service
fi
pkaction --action-id org.local.cpu-control.configure >/dev/null
systemctl enable cpu-control.service
systemctl restart cpu-control.service
# Explicit installation-time discovery; the service itself never probes by hotplug at boot.
busctl --timeout=75 call org.local.CpuControl1 /org/local/CpuControl1 org.local.CpuControl1 Discover
systemctl --no-pager --full status cpu-control.service
