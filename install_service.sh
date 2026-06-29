#!/bin/bash
cat << 'EOF' > /etc/systemd/system/embercore.service
[Unit]
Description=EmberCore Game Server Panel
After=network.target

[Service]
Type=simple
User=masterburns
WorkingDirectory=/home/masterburns/Dokumente/EmberCore
ExecStart=/home/masterburns/Dokumente/EmberCore/.venv/bin/python /home/masterburns/Dokumente/EmberCore/backend/main.py --service
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable embercore.service
systemctl start embercore.service
echo 'EmberCore Service erfolgreich installiert und gestartet!'
