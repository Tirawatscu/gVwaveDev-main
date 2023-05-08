#Client
# This client python can geneate the simulated signal

import socket
import random
import time
import select
import sys
import json
import platform
import uuid

ads1263_available = False

try:
    if platform.system() == "Linux":
        import ADS1263
        import RPi.GPIO as GPIO

        REF = 5.08
        ADC = ADS1263.ADS1263()
        if (ADC.ADS1263_init_ADC1('ADS1263_7200SPS') == -1):
            ADC.ADS1263_Exit()
            print("Failed to initialize ADC1")
            exit()
        ADC.ADS1263_SetMode(1)
        ads1263_available = True
except ImportError:
    print("ADS1263 library not available, using simulated data")

sampling_rate = 128  # Hz
interval = 1 / sampling_rate


def collect_adc_data(duration):
    global ADC
    channelList = [0, 1, 2]
    start_time = time.perf_counter()
    ADC_Value_List = []

    next_sample_time = start_time + interval
    no_sample = duration * sampling_rate

    current_time = start_time

    while len(ADC_Value_List) < no_sample:
        current_time = time.perf_counter()
        if current_time >= next_sample_time:
            ADC_Value = ADC.ADS1263_GetAll(channelList)
            ADC_Value_List.append(ADC_Value)
            next_sample_time += interval

    actual_sampling_rate = len(ADC_Value_List) / (current_time - start_time)

    converted_data = {channel: [] for channel in channelList}
    for data in ADC_Value_List:
        for channel, value in enumerate(data):
            if value >> 31 == 1:
                converted_data[channel].append(-(REF * 2 - value * REF / 0x80000000))
            else:
                converted_data[channel].append(value * REF / 0x7fffffff)
    print(f"actual_sampling_rate = {actual_sampling_rate}")
    return converted_data, actual_sampling_rate


def simulate_adc_data(duration):
    channelList = [0, 1, 2]
    sample_count = int(duration * sampling_rate)
    simulated_data = {channel: [] for channel in channelList}
    time_per_sample = duration / sample_count

    for _ in range(sample_count):
        for channel in channelList:
            simulated_data[channel].append(round(random.uniform(-0.2, 0.2), 2))
        time.sleep(time_per_sample)

    actual_sampling_rate = sampling_rate
    return simulated_data, actual_sampling_rate


def get_mac_address():
    mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
    return ":".join([mac[i:i + 2] for i in range(0, 11, 2)])


def main(ipaddr, port, use_simulated_data=False):
    mac_address = get_mac_address()
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        try:
            s.connect((ipaddr, port))
            s.sendall(mac_address.encode())
            print("Connected to the server")
            while True:
                ready_to_read, ready_to_write, _ = select.select([s], [s], [], 1)

                if ready_to_read:
                    data = s.recv(1024)
                    if data:
                        sample_count = int(data.decode())
                        print(f"Received sample_count: {sample_count}")
                        duration = sample_count / sampling_rate

                        if use_simulated_data or not ads1263_available:
                            random_data, actual_sampling_rate = simulate_adc_data(duration)
                        else:
                            random_data, actual_sampling_rate = collect_adc_data(duration)

                        if ready_to_write:
                            data_to_send = json.dumps(random_data).encode()  # Serialize data to JSON
                            s.sendall(str(len(data_to_send)).encode().zfill(8))  # Send data length
                            s.sendall(data_to_send)  # Send the actual data
                            # print(f"Sent random data: {random_data}")
                    else:
                        break

                time.sleep(1)

        except socket.error as e:
            print(f"Connection failed. Retrying... Error: {e}")
            time.sleep(5)
        finally:
            s.close()



if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python client.py ipaddr port [simulate]")
    else:
        ipaddr = sys.argv[1]
        port = int(sys.argv[2])
        use_simulated_data = False

        if len(sys.argv) >= 4 and sys.argv[3] == "simulate":
            use_simulated_data = True

        main(ipaddr, port, use_simulated_data)


