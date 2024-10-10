import os
import psutil
import subprocess
import time

def disable_network_access():
    print("Disabling network access...")
    subprocess.run(['netsh', 'advfirewall', 'firewall', 'add', 'rule', 
                    'name="KillSwitch Block Internet"', 'dir=out', 'action=block', 'enable=yes'])
    subprocess.run(['netsh', 'advfirewall', 'firewall', 'add', 'rule', 
                    'name="KillSwitch Block Internet"', 'dir=in', 'action=block', 'enable=yes'])

def enable_network_access():
    print("Enabling network access...")
    subprocess.run(['netsh', 'advfirewall', 'firewall', 'delete', 'rule', 
                    'name="KillSwitch Block Internet"', 'dir=out'])
    subprocess.run(['netsh', 'advfirewall', 'firewall', 'delete', 'rule', 
                    'name="KillSwitch Block Internet"', 'dir=in'])

def monitor_vpn():
    vpn_processes = ['openvpnserv.exe']  
    
    while True:
        vpn_connected = False
        for process in psutil.process_iter(['name']):
            if process.info['name'] in vpn_processes:
                vpn_connected = True
                break

        if not vpn_connected:
            print("VPN connection lost. Disabling network access...")
            disable_network_access()
        else:
            print("VPN is connected. Network access is enabled.")
            enable_network_access()

        time.sleep(1)  

if __name__ == "__main__":
     enable_network_access()
