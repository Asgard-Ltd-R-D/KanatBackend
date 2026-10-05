# One-time (persists until reboot)
sudo route -n add -net 224.0.0.0/4 -interface en0

# Verify
netstat -nr -f inet | egrep '224|239'
