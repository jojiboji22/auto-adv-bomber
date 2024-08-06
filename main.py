import colorama
import asyncio
import yaml
import json
import requests
import os
import random
import time
from websockets.sync.client import connect
import threading
from datetime import datetime

colorama.init()

# Load configuration
try:
    with open('config.yml', "r") as file:
        config = yaml.load(file, Loader=yaml.FullLoader).get('default', {})
except Exception as e:
    print(f"{colorama.Fore.RED}Error loading config file: {e}{colorama.Fore.RESET}")
    exit()

user_id = ''
headers = {
    'Authorization': config.get('token', ''),
    'Content-Type': 'application/json'
}

def getWorkHours():
    global start_time, end_time
    if config.get('work_hours', {}).get('enabled', False):
        start_time = datetime.now().replace(hour=config.get('work_hours', {}).get('start_time', 0), minute=random.randint(0, 59))
        end_time = datetime.now().replace(hour=config.get('work_hours', {}).get('end_time', 23) - 1, minute=random.randint(0, 59))

async def checkWorkTime():
    global offline
    offline = False
    while True:
        now = datetime.now()
        if now.hour < start_time.hour or (now.hour == start_time.hour and now.minute < start_time.minute) or now.hour > end_time.hour or (now.hour == end_time.hour and now.minute > end_time.minute):
            if not offline:
                print(f' > Going offline until {start_time.hour}:{start_time.minute}')
                offline = True
            time.sleep(300)  # Check again after 5 minutes
        else:
            break

async def getChannelInfo(channel_id):
    channel = requests.get(f'https://discord.com/api/v9/channels/{channel_id}', headers=headers).json()
    guild = requests.get(f'https://discord.com/api/v9/guilds/{channel["guild_id"]}', headers=headers).json()

    channel_name = channel.get('name', channel_id)
    guild_name = guild.get('name', 'Unknown guild')

    return channel_name, guild_name

async def checkDoublePosting(channel_id, number):
    response = requests.get(f'https://discord.com/api/v9/channels/{channel_id}/messages?limit={number}', headers=headers).json()
    for i in range(number):
        if response and response[i] and 'author' in response[i] and response[i]['author']['id'] == user_id:
            return False
    return True

async def changeStatus():
    status_config = config.get('change_status', {})
    if not status_config.get('enabled', False):
        return
    print(f' > Changing status to {status_config.get("status", "online")}...')
    global ws
    while True:
        try:
            ws = connect('wss://gateway.discord.gg/?v=9&encoding=json')
            start = json.loads(ws.recv())
            heartbeat = start['d']['heartbeat_interval']
            auth = {
                "op": 2,
                "d": {
                    "token": config.get("token", ""),
                    "properties": {
                        "$os": "Windows 10",
                        "$browser": "Google Chrome",
                        "$device": "Windows"
                    },
                    "presence": {
                        "status": status_config.get("status", "online"),
                        "afk": False
                    }
                },
                "s": None,
                "t": None
            }
            ws.send(json.dumps(auth))
            online = {"op": 1, "d": "None"}
            time.sleep(heartbeat / 1000)
            ws.send(json.dumps(online))
        except Exception as e:
            print(f"{colorama.Fore.RED}Error in changeStatus: {e}{colorama.Fore.RESET}")
            time.sleep(10)

async def sendToChannel(channel_id, message, channel_name, guild_name):
    if config.get('avoid_spam', {}).get('enabled', False):
        amount = random.randint(config.get('avoid_spam', {}).get('minimum_messages', 1), config.get('avoid_spam', {}).get('maximum_messages', 5))
        can_post = await checkDoublePosting(channel_id, amount)
        if not can_post:
            if config.get('debug_mode', False):
                print(f' > Skipping "{channel_name}" in "{guild_name}" because you have "avoid_spam" enabled ({amount} messages)')
            return

    if isinstance(message, list):
        for msg_file in message:
            try:
                msg_content = open(os.path.join('messages', msg_file), "r", encoding="utf-8").read()
                requests.post(f'https://discord.com/api/v9/channels/{channel_id}/messages', json={'content': msg_content}, headers=headers)
            except Exception as e:
                print(f"{colorama.Fore.RED}Error reading file {msg_file}: {e}{colorama.Fore.RESET}")
    else:
        response = requests.post(f'https://discord.com/api/v9/channels/{channel_id}/messages', json={'content': message}, headers=headers).json()
        if 'code' in response:
            if response['code'] == 50013:  # Muted
                print(f'{colorama.Fore.RED} > There was a problem sending a message to "{channel_name}" in "{guild_name}" (MUTED){colorama.Fore.RESET}')
                return
            elif response['code'] == 20016:  # Slowmode
                return

    if config.get('debug_mode', False):
        print(f' > A message was sent to "{channel_name}" in "{guild_name}"')

print('\x1b[2J')  # Clear the console

print(colorama.Fore.RED + '''
     █████╗ ██╗   ██╗████████╗ ██████╗      █████╗ ██████╗ 
    ██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗    ██╔══██╗██╔══██╗
    ███████║██║   ██║   ██║   ██║   ██║    ███████║██║  ██║
    ██╔══██║██║   ██║   ██║   ██║   ██║    ██╔══██║██║  ██║
    ██║  ██║╚██████╔╝   ██║   ╚██████╔╝    ██║  ██║██████╔╝
    ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝     ╚═╝  ╚═╝╚═════╝ 
''' + colorama.Fore.RESET + '    by Bomber')

async def sendMessages():
    global last_message
    last_message = ""
    if config.get('multiple_messages', {}).get('enabled', False):
        message_folder = os.listdir('messages')
        mode = config.get('multiple_messages', {}).get('mode', 0)
        if mode == 0:
            if len(message_folder) > 1 and last_message != "":
                message_folder.remove(last_message)
            message_file = random.choice(message_folder)
            message = open(os.path.join('messages', message_file), "r").read()
            last_message = message_file
        elif mode == 1:
            message = sorted(message_folder)
    else:
        try:
            message = open("message.txt", "r").read()
        except Exception as e:
            print(f"{colorama.Fore.RED}Error reading message.txt: {e}{colorama.Fore.RESET}")
            message = ""

    if config.get('work_hours', {}).get('enabled', False):
        getWorkHours()
        await checkWorkTime()

    for channel_id in config.get('channels', []):
        try:
            channel_name, guild_name = await getChannelInfo(channel_id)
            await sendToChannel(channel_id, message, channel_name, guild_name)
        except Exception as e:
            print(f'{colorama.Fore.RED} > There was a problem sending a message to "{channel_id}" in "{guild_name}": {e}{colorama.Fore.RESET}')
            
        if config.get('wait_between_messages', {}).get('enabled', False):
            wait_time = random.randint(config.get('wait_between_messages', {}).get('minimum_interval', 1), config.get('wait_between_messages', {}).get('maximum_interval', 5))
            time.sleep(wait_time)

    delay = config.get('interval', 15)

    if config.get('randomize_interval', {}).get('enabled', False):
        min_interval = config.get('randomize_interval', {}).get('minimum_interval', 10)
        max_interval = config.get('randomize_interval', {}).get('maximum_interval', 30)
        if not min_interval > max_interval:
            delay = random.randint(min_interval, max_interval)
            if config.get('debug_mode', False):
                print(f' > Waiting {delay} minutes...')
    time.sleep(delay * 60)  # change 60 to 1 for testing
    await sendMessages()

async def start():
    global user_id
    response = ""
    try:
        user = requests.get('https://discord.com/api/v9/users/@me', headers=headers)
        response = user.text
        user_id = user.json().get('id', '')
        print(colorama.Fore.GREEN + ' > Token is valid!' + colorama.Fore.RESET)
    except Exception as e:
        print(colorama.Fore.RED + ' > Token is invalid!' + colorama.Fore.RESET)
        print(response)
        print(f"{colorama.Fore.RED}Error: {e}{colorama.Fore.RESET}")
        exit()
        
    if config.get('wait_before_start', 0) > 0:
        print(f' > Waiting {config["wait_before_start"]} minutes before starting...')
        time.sleep(config['wait_before_start'] * 60)  # change 60 to 1 for testing

    if config.get('change_status', {}).get('enabled', False):
        threading.Thread(target=asyncio.run, args=(changeStatus(),)).start()
    await sendMessages()

try:
    asyncio.run(start())
except KeyboardInterrupt:
    exit()
