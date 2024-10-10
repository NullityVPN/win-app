import os
import subprocess
import requests
import sys
import json
import psutil
import threading
from tempfile import NamedTemporaryFile
import shutil
import ctypes
import time
import customtkinter as ctk
import urllib.request
import killswitch
import winreg
import pystray
from PIL import Image, ImageDraw

ICON_URL = "https://files.catbox.moe/feltfx.ico"
THEME_URL = "https://files.catbox.moe/m5941x.json"
INSTALLER_URL = "https://files.catbox.moe/nuj7xz.msi"

BASE_PATH = os.path.dirname(os.path.abspath(__file__)) 
ASSETS_DIR = os.path.join(BASE_PATH, 'assets')
THEMES_DIR = os.path.join(BASE_PATH, 'themes')
ICON_PATH = os.path.join(ASSETS_DIR, 'icon.ico')
THEME_PATH = os.path.join(THEMES_DIR, 'lavender.json')
CONFIG_FILE = os.path.join(BASE_PATH, 'config.json')

BASE_URL = 'https://nullityvpn.de/api'

def hide_console():
    if sys.platform == "win32":
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def request_admin_privileges():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)

def download_file(url, file_path):
    try:
        urllib.request.urlretrieve(url, file_path)
    except Exception as e:
        print(f"Failed to download {url}. Error: {e}")

def load_config():
    config = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\NullityVPN') as key:
            config['api_key'] = winreg.QueryValueEx(key, 'api_key')[0]
            config['killswitch'] = winreg.QueryValueEx(key, 'killswitch')[0]
            config['current_server'] = winreg.QueryValueEx(key, 'current_server')[0]
    except FileNotFoundError:
        pass
    return config

def save_config(config):
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\NullityVPN') as key:
            winreg.SetValueEx(key, 'api_key', 0, winreg.REG_SZ, config['api_key'])
            winreg.SetValueEx(key, 'killswitch', 0, winreg.REG_DWORD, int(config['killswitch']))
            winreg.SetValueEx(key, 'current_server', 0, winreg.REG_SZ, config.get('current_server', ''))
    except Exception as e:
        print(f"Failed to save config to registry: {e}")

def setup_directories():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(THEMES_DIR, exist_ok=True)

def setup_theme_and_icon():
    download_file(ICON_URL, ICON_PATH)
    download_file(THEME_URL, THEME_PATH)
    if not os.path.isfile(THEME_PATH):
        pass
    else:
        ctk.set_default_color_theme(THEME_PATH)
        ctk.set_appearance_mode("Dark")

def start_openvpn(config_content):
    def run_openvpn():
        with NamedTemporaryFile(delete=False, suffix=".ovpn") as temp_config:
            temp_config.write(config_content.encode())
            temp_config_path = temp_config.name

        config_name = os.path.basename(temp_config_path)
        openvpn_config_dir = r"C:\Program Files\OpenVPN\config"
        target_config_path = os.path.join(openvpn_config_dir, config_name)
        shutil.move(temp_config_path, target_config_path)

        try:
            profile_name = os.path.splitext(config_name)[0]
            openvpn_command = f'"C:\\Program Files\\OpenVPN\\bin\\openvpn-gui.exe" --silent_connection 1 --command connect {profile_name}'
            subprocess.run(openvpn_command, shell=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.CalledProcessError as e:
            print(f"Failed to start OpenVPN: {e}")
        finally:
            if os.path.exists(target_config_path):
                os.remove(target_config_path)

    threading.Thread(target=run_openvpn, daemon=True).start()

def stop_openvpn():
    kill_openvpn_process()
    if app.connected_server_label:
        app.connected_server_label.configure(text="Connected Server: --")
    if app.vpn_client:
        app.vpn_client.current_server = None
        app.config_data['current_server'] = ''
        save_config(app.config_data)

def kill_openvpn_process():
    for process in psutil.process_iter(['pid', 'name']):
        if process.info['name'] in ['openvpn.exe', 'openvpn-gui.exe']:
            try:
                print(f"Killing {process.info['name']} (PID: {process.info['pid']})")
                process.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
                print(f"Failed to kill {process.info['name']}: {e}")

def is_vpn_connected():
    for process in psutil.process_iter(['pid', 'name']):
        if process.info['name'] == 'openvpn.exe':
            return True
    return False

def get_current_vpn_server():
    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
        if process.info['name'] == 'openvpn.exe':
            cmdline = process.info['cmdline']
            for arg in cmdline:
                if arg.endswith('.ovpn'):
                    server_name = os.path.splitext(os.path.basename(arg))[0]
                    return server_name
    return None

def monitor_vpn_killswitch():
    while True:
        if app.killswitch_enabled:
            if not is_vpn_connected():  
                print("VPN disconnected! Running killswitch...")
                start_killswitch()  
            else:
                print("VPN is connected.")
        time.sleep(5)

def start_killswitch():
    subprocess.Popen([sys.executable, os.path.join(BASE_PATH, 'killswitch.py')])

def start_killswitch_monitor():
    monitor_thread = threading.Thread(target=monitor_vpn_killswitch, daemon=True)
    monitor_thread.start()

class VPNClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.current_server = None

    def list_servers(self):
        params = {'api_key': self.api_key}
        response = requests.get(BASE_URL, params=params)
        if response.status_code == 200:
            servers = response.json()
            if 'error' in servers:
                print(f"Error: {servers['error']}")
            else:
                return self.group_servers_by_country(servers)
        else:
            print("Failed to list VPN servers.")
            return {}

    def group_servers_by_country(self, servers):
        grouped_servers = {}
        for server in servers:
            if isinstance(server, dict):
                server_name = server.get('name', 'Unknown Server')
            else:
                server_name = server

            country = server_name.split(' - ')[0]
            if country not in grouped_servers:
                grouped_servers[country] = []
            grouped_servers[country].append(server_name)
        return grouped_servers

    def connect_to_server(self, server_name):
        kill_openvpn_process()  # Kill OpenVPN before connecting to a new server
        params = {'api_key': self.api_key, 'connect': server_name}
        response = requests.get(BASE_URL, params=params)
        if response.status_code == 200:
            server_config = response.json()
            if 'error' in server_config:
                print(f"Error: {server_config['error']}")
            else:
                self.current_server = server_name
                app.config_data['current_server'] = server_name
                save_config(app.config_data)
                print(f"Connecting to {server_name}...")
                start_openvpn(server_config['server_config'])
        else:
            print("Failed to connect to the server.")

class Nullity(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Nullity VPN")
        self.geometry("450x400")
        self.iconbitmap(ICON_PATH)  
        self.config_data = load_config()
        self.vpn_client = None
        self.upload_speed_label = None
        self.download_speed_label = None
        self.connected_server_label = None
        self.killswitch_enabled = self.config_data.get('killswitch', False)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        start_killswitch_monitor()

        if 'api_key' not in self.config_data:
            self.setup_api_key()
        else:
            self.api_key = self.config_data['api_key']
            self.vpn_client = VPNClient(self.api_key)
            if not self.check_api_key_validity():
                print("Invalid or expired API key.")
                self.setup_api_key()
            else:
                self.create_main_gui()

        current_server = self.config_data.get('current_server') or get_current_vpn_server()
        if current_server:
            self.connected_server_label.configure(text=f"Connected Server: {current_server}")
            self.vpn_client.current_server = current_server

    def on_closing(self):
        self.destroy()

    def update_network_stats(self):
        previous_sent = psutil.net_io_counters().bytes_sent
        previous_recv = psutil.net_io_counters().bytes_recv
        while True:
            time.sleep(1)
            current_sent = psutil.net_io_counters().bytes_sent
            current_recv = psutil.net_io_counters().bytes_recv
            upload_speed = (current_sent - previous_sent) / 1024 / 1024 * 8
            download_speed = (current_recv - previous_recv) / 1024 / 1024 * 8
            previous_sent = current_sent
            previous_recv = current_recv

            try:
                if self.upload_speed_label:
                    self.upload_speed_label.configure(text=f"Upload Speed: {upload_speed:.2f} Mbps")
                if self.download_speed_label:
                    self.download_speed_label.configure(text=f"Download Speed: {download_speed:.2f} Mbps")
                if self.vpn_client and self.vpn_client.current_server:
                    if self.connected_server_label:
                        self.connected_server_label.configure(text=f"Connected Server: {self.vpn_client.current_server}")
                else:
                    if self.connected_server_label:
                        self.connected_server_label.configure(text="Connected Server: --")
            except ctk.TclError:
                break

    def setup_api_key(self):
        self.clear_frame()
        self.api_key_label = ctk.CTkLabel(self, text="Enter the API key you received upon signup or from your dashboard.\nThis key is used to authenticate and communicate with the API.")
        self.api_key_label.pack(pady=10)
        self.api_key_entry = ctk.CTkEntry(self, width=300)
        self.api_key_entry.pack(pady=10)
        self.save_button = ctk.CTkButton(self, text="Save", command=self.save_api_key)
        self.save_button.pack(pady=10)

    def save_api_key(self):
        self.api_key = self.api_key_entry.get()
        self.config_data['api_key'] = self.api_key
        save_config(self.config_data)
        self.api_key_label.destroy()
        self.api_key_entry.destroy()
        self.save_button.destroy()
        self.vpn_client = VPNClient(self.api_key)
        if not self.check_api_key_validity():
            print("Invalid or expired API key.")
            self.setup_api_key()
        else:
            self.create_main_gui()

    def create_main_gui(self):
        self.content_frame = ctk.CTkFrame(self)
        self.content_frame.pack(side="top", fill="both", expand=True, padx=20, pady=20)
        self.connected_server_label = ctk.CTkLabel(self.content_frame, text="Connected Server: --", font=("Arial", 16))
        self.connected_server_label.pack(pady=10)
        self.connect_button = ctk.CTkButton(self.content_frame, text="Connect", command=self.show_servers)
        self.connect_button.pack(pady=10)
        self.stop_button = ctk.CTkButton(self.content_frame, text="Stop VPN", command=stop_openvpn)
        self.stop_button.pack(pady=10)
        self.upload_speed_label = ctk.CTkLabel(self.content_frame, text="Upload Speed: -- Mbps")
        self.upload_speed_label.pack(pady=10)
        self.download_speed_label = ctk.CTkLabel(self.content_frame, text="Download Speed: -- Mbps")
        self.download_speed_label.pack(pady=10)
        self.monitor_thread = threading.Thread(target=self.update_network_stats, daemon=True)
        self.monitor_thread.start()
        self.create_footer()

    def create_footer(self):
        footer_frame = ctk.CTkFrame(self)
        footer_frame.pack(side="bottom", fill="x", padx=10, pady=10)
        about_label = ctk.CTkLabel(footer_frame, text="About", fg_color=None, cursor="hand2")
        about_label.pack(side="left", padx=5)
        about_label.bind("<Button-1>", lambda e: self.show_about())
        settings_label = ctk.CTkLabel(footer_frame, text="Settings", fg_color=None, cursor="hand2")
        settings_label.pack(side="right", padx=5)
        settings_label.bind("<Button-1>", lambda e: self.show_settings())

    def show_servers(self):
        self.clear_frame()
        self.server_list_frame = ctk.CTkFrame(self)
        self.server_list_frame.pack(fill="both", expand=True, padx=20, pady=20)

        servers = self.vpn_client.list_servers()

        if servers:
            for country, server_list in servers.items():
                country_label = ctk.CTkLabel(self.server_list_frame, text=country, font=("Arial", 14, "bold"))
                country_label.pack(pady=(10, 5))
                for server_name in server_list:
                    server_button = ctk.CTkButton(self.server_list_frame, text=server_name, 
                                                  command=lambda s=server_name: self.connect_to_server(s))
                    server_button.pack(pady=5)

        back_button = ctk.CTkButton(self.server_list_frame, text="Back", command=self.back_to_main)
        back_button.pack(pady=10)

    def show_settings(self):
        self.clear_frame()
        settings_frame = ctk.CTkFrame(self)
        settings_frame.pack(fill="both", expand=True, padx=20, pady=20)

        killswitch_header = ctk.CTkLabel(settings_frame, text="Killswitch Settings", font=("Arial", 14, "bold"))
        killswitch_header.pack(pady=(10, 5))
        killswitch_toggle = ctk.CTkCheckBox(settings_frame, text="Enable Killswitch", command=self.toggle_killswitch)
        killswitch_toggle.pack(pady=10)
        killswitch_toggle.select() if self.killswitch_enabled else killswitch_toggle.deselect()

        api_key_header = ctk.CTkLabel(settings_frame, text="API Key Settings", font=("Arial", 14, "bold"))
        api_key_header.pack(pady=(20, 5))
        api_key_frame = ctk.CTkFrame(settings_frame)
        api_key_frame.pack(pady=5)
        api_key_label = ctk.CTkLabel(api_key_frame, text="API Key:")
        api_key_label.pack(side="left", padx=(0, 5))
        api_key_entry = ctk.CTkEntry(api_key_frame, width=200)
        api_key_entry.pack(side="left", padx=(0, 5))
        api_key_entry.insert(0, self.config_data.get('api_key', ''))
        save_api_key_button = ctk.CTkButton(api_key_frame, text="Save", command=lambda: self.save_api_key_from_settings(api_key_entry))
        save_api_key_button.pack(side="left")

        back_button = ctk.CTkButton(settings_frame, text="Back", command=self.back_to_main)
        back_button.pack(pady=10)

    def save_api_key_from_settings(self, api_key_entry):
        self.api_key = api_key_entry.get()
        self.config_data['api_key'] = self.api_key
        save_config(self.config_data)
        self.vpn_client = VPNClient(self.api_key)
        if not self.check_api_key_validity():
            print("Invalid or expired API key.")
            self.setup_api_key()
        else:
            self.back_to_main()

    def show_about(self):
        self.clear_frame()
        about_frame = ctk.CTkFrame(self)
        about_frame.pack(fill="both", expand=True, padx=20, pady=20)
        about_label = ctk.CTkLabel(about_frame, text="Nullity VPN v1.0\nDeveloped by nullityvpn.de\n\nGithub: github.com/NullityVPN\n\nTerms: nullityvpn.de/tos\nPrivacy: nullityvpn.de/privacy", font=("Arial", 16))
        about_label.pack(pady=10)
        back_button = ctk.CTkButton(about_frame, text="Back", command=self.back_to_main)
        back_button.pack(pady=10)

    def back_to_main(self):
        self.clear_frame()
        self.create_main_gui()

    def toggle_killswitch(self):
        self.killswitch_enabled = not self.killswitch_enabled
        self.config_data['killswitch'] = self.killswitch_enabled
        save_config(self.config_data)

    def clear_frame(self):
        for widget in self.winfo_children():
            widget.destroy()

    def connect_to_server(self, server_name):
        self.vpn_client.connect_to_server(server_name)
        self.connected_server_label.configure(text=f"Connected Server: {server_name}")
        self.back_to_main()


    def check_api_key_validity(self):
        servers = self.vpn_client.list_servers()
        if not servers:
            self.setup_api_key()
            return False
        return True



if __name__ == "__main__":
    if not is_admin():  
        print("Admin privileges are required. Requesting admin privileges...")
        request_admin_privileges()
        sys.exit()  
    else:
        print("Running with admin privileges.")

    hide_console()
    setup_directories()
    setup_theme_and_icon()
    app = Nullity()
    app.mainloop()