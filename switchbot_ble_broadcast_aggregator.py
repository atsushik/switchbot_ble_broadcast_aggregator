#!/usr/bin/env python3
# Copyright 2017-present WonderLabs, Inc. <support@wondertechlabs.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import pexpect
import sys
from bluepy.btle import Scanner, DefaultDelegate
import binascii
import copy
import datetime
import time

# import paho.mqtt.mqtt_client as mqtt
from paho.mqtt import client as mqtt_client
from uuid import getnode as get_mac
import random
import fcntl
import socket
import struct

def getHwAddr(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    info = fcntl.ioctl(s.fileno(), 0x8927,  struct.pack('256s', bytes(ifname, 'utf-8')[:15]))
    return ':'.join('%02x' % b for b in info[18:24])

# ブローカーに接続できたときの処理
def on_connect(mqtt_client, userdata, flag, rc):
    if rc == 0: 
        print ( "0: Connection successful ")
    elif rc == 1: 
        print ( "1: Connection refused – incorrect protocol version")
    elif rc == 2: 
        print ( "2: Connection refused – invalid mqtt_client identifier")
    elif rc == 3: 
        print ( "3: Connection refused – server unavailable")
    elif rc == 4:
        print (  "4:Connection refused – bad username or password")
    elif rc == 5:
        print (  "5:Connection refused – not authorised")

# ブローカーが切断したときの処理
def on_disconnect(mqtt_client, userdata, rc):
    print("Unexpected disconnection.")
    mqtt_connect(mqtt_client=mqtt_client, mqtt_server=mqtt_server)

def on_message(mqtt_client, userdata, msg):
    print(msg.topic+" "+str(msg.payload))

def on_publish(mqtt_client,userdata,result):             #create function for callback
    print("data published \n")
    pass
    return result

def mqtt_connect(mqtt_client = None, mqtt_server = None ):
    while 1:
        try:
            mqtt_client.connect(mqtt_server, 1883, 30)  # 接続先は自分自身
        except ConnectionRefusedError as err:
            print ( err )
            rc = -1
            print("failed to connect")
        else:
            print("Connected to mqtt server")
            rc = 0
            return rc
        time.sleep ( 3 )

# mac = get_mac()
# print ( hex(mac) ) 
# mac_str = ':'.join(("%012X" % mac)[i:i+2] for i in range(0, 12, 2))
mac_str = getHwAddr('wlan0')
print ( mac_str )

# MQTTの接続設定
mqtt_server = "homeassistant.local"
mqtt_user = "sensor"
mqtt_password = "sensor"

mqtt_topic_root = "home/sensors/"

client_id = f'mac_str-{random.randint(0, 1000)}'

mqtt_client = mqtt_client.Client(client_id)                 # クラスのインスタンス(実体)の作成
mqtt_client.username_pw_set(mqtt_user, password=mqtt_password)
mqtt_client.on_connect = on_connect         # 接続時のコールバック関数を登録
mqtt_client.on_disconnect = on_disconnect   # 切断時のコールバックを登録
mqtt_client.on_message = on_message         # メッセージ到着時のコールバック

mqtt_connect(mqtt_client=mqtt_client, mqtt_server=mqtt_server)

mqtt_client.loop_start()


class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)


class DevScanner(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)
        # print('Scanner inited')

    def dongle_start(self):
        self.con = pexpect.spawn('hciconfig hci0 up')
        time.sleep(1)

    def dongle_restart(self):
        print('restart bluetooth dongle')
        self.con = pexpect.spawn('hciconfig hci0 down')
        time.sleep(3)
        self.con = pexpect.spawn('hciconfig hci0 up')
        time.sleep(3)

    def scan_loop(self):
        service_uuid = 'cba20d00-224d-11e6-9fb8-0002a5d5c51b'
        company_id = '6909'  # actually 0x0969
        dev_list = []
        bot_list = []
        meter_list = []
        curtain_list = []
        contact_list = []
        motion_list = []
        param_list = []
        plug_list = []

        pir_tip = ['No movement detected', 'Movement detected']
        hall_tip = ['Door closed', 'Door opened', 'Timeout no closed']
        light_tip = ['Dark', 'Bright']
        plug_sw = ['Off', 'On']

        self.con = pexpect.spawn('hciconfig')
        pnum = self.con.expect(['hci0', pexpect.EOF, pexpect.TIMEOUT])
        if pnum == 0:
            self.con = pexpect.spawn('hcitool lescan')
            # self.con.expect('LE Scan ...', timeout=5)
            scanner = Scanner().withDelegate(DevScanner())
            devices = scanner.scan(3.0)
            print('Scanning...')
        else:
            raise Error('no bluetooth error')

        for dev in devices:
            mac = 0
            param_list[:] = []
            print ( dev )
            broadcastMessageDict = {}
            for (adtype, desc, value) in dev.getScanData():
                # print(adtype, desc, value)
                broadcastMessageDict[desc] = [adtype, value]
            for (adtype, desc, value) in dev.getScanData():
                # print(adtype, desc, value)
                if desc == '16b Service Data':
                    # https://github.com/OpenWonderLabs/SwitchBotAPI-BLE#device-type
                    dev_type = binascii.a2b_hex(value[4:6])
                    if dev_type == b'H':
                        # Bot
                        param_list.append(binascii.a2b_hex(value[6:8]))
                    elif dev_type == b'T':
                        print ( 'found switchbot Meter' )
                        # Meter
                        # celsius
                        tempFra = int(value[11:12].encode('utf-8'), 16) / 10.0
                        tempInt = int(value[12:14].encode('utf-8'), 16)
                        if tempInt < 128:
                            tempInt *= -1
                            tempFra *= -1
                        else:
                            tempInt -= 128
                        param_list.append(tempInt + tempFra)
                        param_list.append(
                            int(value[14:16].encode('utf-8'), 16) % 128)
                        # print('meter:', param1, param2)
                        v = broadcastMessageDict['16b Service Data'][1]
                        m = dev.addr

                        # 000d 54 10 64 07 98 3d
                        import pprint
                        pprint.pprint ( broadcastMessageDict )
                        pprint.pprint ( [v, m] )
                        pprint.pprint ( binascii.a2b_hex(v[4:6]) )
                        battery_level = int(v[8:10], base=16) & 0b01111111
                        pprint.pprint ( ["battery", battery_level]  )

                        temperature_decimal = int(v[10:12], base=16) & 0b00001111
                        temperature_int = int(v[12:14], base=16) & 0b01111111
                        temperature_posNegFlag = (int(v[12:14], base=16) & 0b10000000) >> 7
                        temperature = temperature_int + temperature_decimal / 10
                        if temperature_posNegFlag == 0:
                            temperature *= -1
                        pprint.pprint ( ["temperature", temperature]  )

                        temperature_scale = (int(v[14:16], base=16) & 0b10000000) >> 7
                        if temperature_scale == 0:
                            temperature_scale = "Celsius scale (°C)"
                        else:
                            temperature_scale = "Fahrenheit scale (°F)"
                        pprint.pprint ( ["temperature_scale", temperature_scale]  )

                        humidity = int(v[14:16], base=16) & 0b01111111
                        pprint.pprint ( ["humidity", humidity]  )

                        mac_address = dev.addr
                        pprint.pprint ( ["mac_address", mac_address]  )

                        topic = mqtt_topic_root + 'temperature/' + mac_address + "/value"
                        rc = mqtt_client.publish(topic, temperature)
                        if rc[0] == 0:
                            print("data published : %s\n" % topic)
                        else:
                            print("failed to publish : %s\n" % topic)
                            mqtt_connect(mqtt_client=mqtt_client, mqtt_server=mqtt_server)

                        topic = mqtt_topic_root + 'humidity/' + mac_address + "/value"
                        rc = mqtt_client.publish(topic, humidity)
                        if rc[0] == 0:
                            print("data published : %s\n" % topic)
                        else:
                            print("failed to publish : %s\n" % topic)
                            mqtt_connect(mqtt_client=mqtt_client, mqtt_server=mqtt_server)

                        topic = mqtt_topic_root + 'battery_level/' + mac_address + "/value"
                        rc = mqtt_client.publish(topic, battery_level)
                        if rc[0] == 0:
                            print("data published : %s\n" % topic)
                        else:
                            print("failed to publish : %s\n" % topic)
                            mqtt_connect(mqtt_client=mqtt_client, mqtt_server=mqtt_server)

                        topic = mqtt_topic_root + 'rssi/' + mac_address + "/value"
                        rc = mqtt_client.publish(topic, dev.rssi)
                        if rc[0] == 0:
                            print("data published : %s\n" % topic)
                        else:
                            print("failed to publish : %s\n" % topic)
                            mqtt_connect(mqtt_client=mqtt_client, mqtt_server=mqtt_server)


                    elif dev_type == b'd':
                        # Contact Sensor
                        # print(adtype, desc, value)
                        pirSta = (
                            int(value[6:7].encode('utf-8'), 16) >> 2) & 0x01
                        # TODO:
                        # diffSec = (
                        #     int(value[10:11].encode('utf-8'), 16) >> 2) & 0x02
                        diffSec = 0
                        hallSta = (
                            int(value[11:12].encode('utf-8'), 16) >> 1) & 0x03
                        lightSta = int(value[11:12].encode('utf-8'), 16) & 0x01
                        param_list.extend([hallSta, pirSta, lightSta, diffSec])
                        # print(pirSta, diffSec, hallSta, lightSta)
                    elif dev_type == b's':
                        # Motion Sensor
                        # print(adtype, desc, value)
                        pirSta = (
                            int(value[6:7].encode('utf-8'), 16) >> 2) & 0x01
                        lightSta = (int(value[15:16].encode('utf-8'), 16) & 0x03) - 1
                        # TODO:
                        diffSec = 0
                        param_list.extend([pirSta, lightSta, diffSec])
                    elif dev_type == b'g': # j?
                        # Plug Mini	
                        # https://github.com/OpenWonderLabs/SwitchBotAPI-BLE/blob/latest/devicetypes/plugmini.md
                        print('found switchbot_plugmini')
                        print(adtype, desc, value)
                        mode = 0
                        power = (int(value[24:28].encode('utf-8'), 16) & 0x7f) / 10.0;
                        sw = int(value[18].encode('utf-8'), 16 ) >> 3;
                        param_list.extend([sw, power])
                    elif dev_type == b'g': # j?
                        # Meter Plus
                        # https://github.com/OpenWonderLabs/SwitchBotAPI-BLE/blob/latest/devicetypes/plugmini.md
                        print('found switchbot Meter Plus')
                    else:
                        param_list[:] = []
                elif desc == 'Local name':
                    if value == 'WoHand':
                        mac = dev.addr
                        dev_type = b'H'
                    elif value == 'WoMeter':
                        mac = dev.addr
                        dev_type = b'T'
                    elif value == 'WoCurtain':
                        mac = dev.addr
                        dev_type = b'c'
                    elif value == 'WoContact':
                        mac = dev.addr
                        dev_type = b'd'
                    elif value == 'WoMotion':
                        mac = dev.addr
                        dev_type = b's'
                elif desc == 'Complete 128b Services' and value == service_uuid:
                    mac = dev.addr
                elif desc == 'Manufacturer' and value[0:4] == company_id:
                    mac = dev.addr
                #以下追記 
                #`xx:xx:xx:xx:xx:xx`はPlugMiniのBluetoothのMacアドレスを小文字表記で`:`で区切った値
                # if( mac  == "xx:xx:xx:xx:xx:xx"):
                #     mode = 0
                #     power = (int(value[24:28].encode('utf-8'), 16) & 0x7f) / 10.0;
                #     sw = int(value[18].encode('utf-8'), 16 ) >> 3;
                #     param_list.extend([sw, power])

            if mac != 0:
                dev_list.append([mac, dev_type, copy.deepcopy(param_list)])

        # print(dev_list)
        for (mac, dev_type, params) in dev_list:
            if dev_type == b'H':
                if int(binascii.b2a_hex(params[0]), 16) > 127:
                    bot_list.append([mac, 'Bot', 'Turn On'])
                    bot_list.append([mac, 'Bot', 'Turn Off'])
                    bot_list.append([mac, 'Bot', 'Up'])
                    bot_list.append([mac, 'Bot', 'Down'])
                else:
                    bot_list.append([mac, 'Bot', 'Press'])
            elif dev_type == b'T':
                meter_list.append([mac, 'Meter', "%.1f'C %d%%" %
                                  (params[0], params[1])])
            elif dev_type == b'c':
                curtain_list.append([mac, 'Curtain', 'Open'])
                curtain_list.append([mac, 'Curtain', 'Close'])
                curtain_list.append([mac, 'Curtain', 'Pause'])
            elif dev_type == b'd':
                # TODO:
                # timeTirgger = datetime.datetime.now() + datetime.timedelta(0, params[3])
                # contact_list.append([mac, 'Contact', "%s, %s, %s, Last trigger: %s" %
                #                      (hall_tip[params[0]], pir_tip[params[1]], light_tip[params[2]], timeTirgger.strftime("%Y-%m-%d %H:%M"))])
                contact_list.append([mac, 'Contact', "%s, %s, %s" %
                                     (hall_tip[params[0]], pir_tip[params[1]], light_tip[params[2]])])
            elif dev_type == b's':
                motion_list.append([mac, 'Motion', "%s, %s" %
                                    (pir_tip[params[0]], light_tip[params[1]])])
            elif dev_type == b'j':
                plug_list.append([mac, 'Plug', "%s, %.1fW" % (plug_sw[params[0]], params[1])])
        print('Scan timeout.')
        return bot_list + meter_list + curtain_list + contact_list + motion_list + plug_list
        pass

    def register_cb(self, fn):
        self.cb = fn
        return

    def close(self):
        # self.con.sendcontrol('c')
        self.con.close(force=True)


def trigger_device(device):
    [mac, dev_type, act] = device
    # print 'Start to control'
    con = pexpect.spawn('gatttool -b ' + mac + ' -t random -I')
    con.expect('\[LE\]>')
    print('Preparing to connect.')
    retry = 3
    index = 0
    while retry > 0 and 0 == index:
        con.sendline('connect')
        # To compatible with different Bluez versions
        index = con.expect(
            ['Error', '\[CON\]', 'Connection successful.*\[LE\]>'])
        retry -= 1
    if 0 == index:
        print('Connection error.')
        return
    print('Connection successful.')
    con.sendline('char-desc')
    con.expect(['\[CON\]', 'cba20002-224d-11e6-9fb8-0002a5d5c51b'])
    cmd_handle = con.before.decode('utf-8').split('\n')[-1].split()[2].strip(',')
    if dev_type == 'Bot':
        if act == 'Turn On':
            con.sendline('char-write-cmd ' + cmd_handle + ' 570101')
        elif act == 'Turn Off':
            con.sendline('char-write-cmd ' + cmd_handle + ' 570102')
        elif act == 'Press':
            con.sendline('char-write-cmd ' + cmd_handle + ' 570100')
        elif act == 'Down':
            con.sendline('char-write-cmd ' + cmd_handle + ' 570103')
        elif act == 'Up':
            con.sendline('char-write-cmd ' + cmd_handle + ' 570104')
    elif dev_type == 'Meter':
        con.sendline('char-write-cmd ' + cmd_handle + ' 570F31')
        con.expect('\[LE\]>')
        con.sendline('char-read-uuid cba20003-224d-11e6-9fb8-0002a5d5c51b')
        index = con.expect(['value:[0-9a-fA-F ]+', 'Error'])
        if index == 0:
            data = con.after.decode('utf-8').split(':')[1].replace(' ', '')
            tempFra = int(data[3], 16) / 10.0
            tempInt = int(data[4:6], 16)
            if tempInt < 128:
                tempInt *= -1
                tempFra *= -1
            else:
                tempInt -= 128
            meterTemp = tempInt + tempFra
            meterHumi = int(data[6:8], 16) % 128
            print("Meter[%s] %.1f'C %d%%" % (mac, meterTemp, meterHumi))
        else:
            print('Error!')
    elif dev_type == 'Curtain':
        if act == 'Open':
            con.sendline('char-write-cmd ' + cmd_handle + ' 570F450105FF00')
        elif act == 'Close':
            con.sendline('char-write-cmd ' + cmd_handle + ' 570F450105FF64')
        elif act == 'Pause':
            con.sendline('char-write-cmd ' + cmd_handle + ' 570F450100FF')
    else:
        print('Unsupported operations')
    con.expect('\[LE\]>')
    con.sendline('quit')
    print('Complete')


def main():
    # Check bluetooth dongle
    # print(
    #     'Usage: "sudo python3 switchbot_py2topy3.py [mac dev_type cmd]" or "sudo python3 switchbot_py2topy3.py"')

    connect = pexpect.spawn('hciconfig')
    pnum = connect.expect(["hci0", pexpect.EOF, pexpect.TIMEOUT])
    if pnum != 0:
        print('No bluetooth hardware, exit now')
        sys.exit()
    connect = pexpect.spawn('hciconfig hci0 up')

    while 1:
        scan = DevScanner()
        dev_list = scan.scan_loop()
        time.sleep ( 0.1 )

    # if len(sys.argv) == 4 or len(sys.argv) == 5:
    #     dev = sys.argv[1]
    #     dev_type = sys.argv[2]
    #     act = sys.argv[3] if len(sys.argv) < 5 else ('Turn ' + sys.argv[4])
    #     trigger_device([dev, dev_type, act])

    # elif len(sys.argv) == 1:
    #     # Start scanning...
    #     scan = DevScanner()
    #     dev_list = scan.scan_loop()
    #     # dev_number = None

    #     if not dev_list:
    #         print("No SwitchBot nearby, exit")
    #         sys.exit()
    #     for idx, val in enumerate(dev_list):
    #         print('%2d' % idx, val)

    #     dev_number = int(input("Input the device number to control:"))
    #     if dev_number >= len(dev_list):
    #         print("Input error, exit")
    #     else:
    #         ble_dev = dev_list[dev_number]
    #         print(ble_dev)

    #         # Trigger the device to work
    #         # If the SwitchBot address is known you can run this command directly without scanning

    #         trigger_device(ble_dev)
    # else:
    #     print('Wrong cmd!')
    #     print(
    #         'Usage: "sudo python3 switchbot_py2topy3.py [mac dev_type cmd]" or "sudo python3 switchbot_py2topy3.py"')

    # connect = pexpect.spawn('hciconfig')

    sys.exit()


if __name__ == "__main__":
    main()
