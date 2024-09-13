import os
import psutil
import subprocess
import time

def disable_network_adapters():
    print("Disabling network adapters...")
    for adapter in psutil.net_if_addrs():
        if 'Ethernet' in adapter or 'Wi-Fi' in adapter:
            disable_command = f'netsh interface set interface "{adapter}" admin=disable'
            subprocess.run(disable_command, shell=True)

def enable_network_adapters():
    print("Enabling network adapters...")
    for adapter in psutil.net_if_addrs():
        if 'Ethernet' in adapter or 'Wi-Fi' in adapter:
            enable_command = f'netsh interface set interface "{adapter}" admin=enable'
            subprocess.run(enable_command, shell=True)

def monitor_vpn():
    while True:
        vpn_connected = False
        for process in psutil.process_iter(['name']):
            if process.info['name'] == 'openvpn.exe':
                vpn_connected = True
                break

        if not vpn_connected:
            print("VPN connection lost. Disabling network adapters...")
            disable_network_adapters()
        else:
            print("VPN is connected. Network adapters are enabled.")
            enable_network_adapters()

        time.sleep(5)  

if __name__ == "__main__":
    monitor_vpn()
