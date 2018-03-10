import subprocess
import sys
import os
import time

if os.getuid() != 0:
    print('You should run verifier with sudo privileges!')
    sys.exit(1)

try:
    os.remove('log.txt')
except OSError:
    pass

p1 = subprocess.Popen(['python3', 'app.py'])
print('Verifier started.')
time.sleep(0.5)
p2 = subprocess.Popen(['python3', 'mailmon.py'])
print('Mail Monitor started.')
print('Press Ctrl+C or close console to stop.')

while True:
    try:
        time.sleep(0.25)
    except KeyboardInterrupt:
        print()
        p2.terminate()
        print('Mail Monitor stopped.')
        p1.terminate()
        print('Verifier stopped.')
        sys.exit(0)
