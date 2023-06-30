import os, json, time, re

min_speed = 0.05
max_speed = 1
speed_step = 0.05
thres_temp_min = 85
thres_temp_max = 90
ipmi_ip = "10.0.0.221"
ipmi_username = "root"
ipmi_password = "calvin"

def get_cpu_temp():
    temp = list()
    stdout = os.popen('sensors -j')
    lines = stdout.readlines()
    stdout.close()
    line = ""
    for ll in lines:
        line += ll
    jd = json.loads(line)
    for key1 in jd.keys():
        for key2 in jd[key1].keys():
            if key2 == 'Adapter':
                continue
            for key3 in jd[key1][key2].keys():
                if not 'input' in key3:
                    continue
                temp.append(jd[key1][key2][key3])
    max_temp = -1
    for _ in temp:
        max_temp = max(max_temp, _)
    return max_temp


def get_cuda_temp():
    temp = list()
    stdout = os.popen('nvidia-smi dmon -s p -c 1')
    lines = stdout.readlines()
    stdout.close()
    for line in lines:
        if line.startswith("#"):
            continue
        line_split = re.split(r'[ ]+', line)
        temp.append(int(line_split[3].strip()))
    max_temp = -1
    for _ in temp:
        max_temp = max(max_temp, _)
    return max_temp


def set_fan(percentage):
    hex_value = hex(int(percentage*100))

    os.system(f"ipmitool -I lanplus -H {ipmi_ip} -U {ipmi_username} -P {ipmi_password} raw 0x30 0x30 0x01 0x00")
    os.system(f"ipmitool -I lanplus -H {ipmi_ip} -U {ipmi_username} -P {ipmi_password} raw 0x30 0x30 0x02 0xff "+hex_value)
    

if __name__ == '__main__':
    current_speed = 0.3
    while True:
        cpu_temp = get_cpu_temp()
        cuda_temp = get_cuda_temp()
        temp = max(cpu_temp, cuda_temp)
        if temp > thres_temp_max:
            current_speed += speed_step
        elif temp < thres_temp_min:
            current_speed -= speed_step
        else:
            pass
            # current_speed -= 0.1 * speed_step
        current_speed = min(current_speed, max_speed)
        current_speed = max(current_speed, min_speed)
        set_fan(current_speed)
        print(f"{temp}_{current_speed}")
        time.sleep(5)
        
