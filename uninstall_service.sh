#!/bin/bash
systemctl stop embercore.service
systemctl disable embercore.service
rm -f /etc/systemd/system/embercore.service
systemctl daemon-reload
echo 'Service erfolgreich entfernt!'
