#!/usr/bin/env bash
# Pull the latest code and restart the API. Run on the server: sudo /opt/spotter/deploy/ec2/update.sh
set -euo pipefail
cd /opt/spotter
git pull --ff-only
/opt/spotter/venv/bin/pip install --quiet -r backend/requirements.txt
systemctl restart spotter-api
sleep 2
curl -fsS http://127.0.0.1:8001/api/health && echo
