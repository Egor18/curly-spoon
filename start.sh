#!/usr/bin/env bash
if [ "$(id -u)" != "0" ]; then
   echo "You should run verifier with sudo privileges!"
   exit 1
fi
rm -f log.txt
sudo nohup python3 app.py > /dev/null 2>&1 &
sudo nohup python3 mailmon.py > /dev/null 2>&1 &
echo "Verifier started."
