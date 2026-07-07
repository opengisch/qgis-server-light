#!/bin/bash
# we prepare the servers keys, if they did not exist already
if [ ! -f /etc/ssh/ssh_host_ed25519_key ]; then
  sudo ssh-keygen -A
fi
# in this container we need prepare for privilege separation
sudo mkdir -p /run/sshd
sudo chmod 0755 /run/sshd
# we start the ssh daemon
sudo /usr/sbin/sshd

# subsequent actions MUST NOT be run with sudo!
exec /bin/dev.start.sh
