import os, re, json, time, socket, asyncio, logging, threading

cfg_filename = './idrac_client.json'
f = open(cfg_filename, 'r')
cfg = json.load(f)
f.close()

logging.basicConfig(filename=cfg['logfile'], level=logging.DEBUG)

def get_gpu_temp():
    try:
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
    except:
        max_temp = 0
    return max_temp


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


class FanSpeedAlg:
    def __init__(self, init_speed=0.3, thres_temp_min=85, thres_temp_max=95, min_speed=0.05, max_speed=1, speed_step=0.05, speed_momentum=0.2):
        self.speed = init_speed
        self.thres_temp_min = thres_temp_min
        self.thres_temp_max = thres_temp_max
        self.min_speed = min_speed
        self.max_speed = max_speed
        self.speed_step = speed_step
        self.speed_momentum = speed_momentum
        
    def step(self, temp):
        speed_range = self.max_speed - self.min_speed
        temp_range = self.thres_temp_max - self.thres_temp_min
        speed = self.min_speed + speed_range / temp_range * (temp - self.thres_temp_min)
        speed = min(speed, self.max_speed)
        speed = max(speed, self.min_speed)
        last_speed = self.speed
        speed = last_speed * (1-self.speed_momentum) + speed * self.speed_momentum
        speed = min(speed, self.max_speed)
        speed = max(speed, self.min_speed)
        self.speed = speed
        return self.speed


def _get_ipmi_head(ipmi_ip=None, ipmi_username="root", ipmi_password="calvin"):
    if ipmi_ip is not None:
        head = f"ipmitool -I lanplus -H {ipmi_ip} -U {ipmi_username} -P {ipmi_password}"
    else:
        head = f"ipmitool"
    return head


def set_fan_idrac(percentage, ipmi_ip=None, ipmi_username="root", ipmi_password="calvin"):
    hex_value = hex(int(percentage*100))
    ipmi_head = _get_ipmi_head(ipmi_ip, ipmi_username, ipmi_password)
    
    # os.system(f"{ipmi_head} raw 0x30 0x30 0x01 0x00")
    # os.system(f"{ipmi_head} raw 0x30 0x30 0x02 0xff {hex_value}")
    
    logging.debug(f"{ipmi_head} raw 0x30 0x30 0x01 0x00")
    logging.debug(f"{ipmi_head} raw 0x30 0x30 0x02 0xff {hex_value}")


def set_fan_c6220(percentage, ipmi_ip=None, ipmi_username="root", ipmi_password="calvin"):
    hex_value = hex(int(percentage*100))
    ipmi_head = _get_ipmi_head(ipmi_ip, ipmi_username, ipmi_password)
    
    # os.system(f"{ipmi_head} raw 0x30 0x19 0x20 {hex_value}")
    
    logging.debug(f"{ipmi_head} raw 0x30 0x19 0x20 {hex_value}")
    
    
class TaskStandalone:
    def __init__(self, cfg):
        devices = cfg["devices"]
        ipmi_setup = cfg["ipmi_setup"]
        self.run_interval = cfg["run_interval"]
        
        self.devices = list()
        for device_cfg in devices:
            device = device_cfg["device"]
            if device == 'cpu':
                temp_fn = get_cpu_temp
            elif device == 'cuda' or device == 'gpu':
                temp_fn = get_gpu_temp
            del device_cfg['device']
            fan_speed_alg = FanSpeedAlg(**device_cfg)
            self.devices.append((temp_fn, fan_speed_alg))
        if ipmi_setup["ipmi_ip"] == '0.0.0.0':
            ipmi_setup["ipmi_ip"] = None
        
        if ipmi_setup["machine_type"] == "idrac":
            self.set_fan_fn = set_fan_idrac
        elif ipmi_setup["mahine_type"] == "c6220":
            self.set_fan_fn = set_fan_c6220
        else:
            assert False
        del ipmi_setup["machine_type"]
        self.ipmi_setup = ipmi_setup
            
    def run_iter(self):
        speeds = list()
        for temp_fn, fan_speed_alg in self.devices:
            temp = temp_fn()
            speed = fan_speed_alg.step(temp) 
            speeds.append(speed)
            logging.info(f"temp={temp}, speed={speed}")
        speed = max(speeds)
        self.set_fan_fn(speed, **self.ipmi_setup)
        
    def run(self):
        while True:
            self.run_iter()
            time.sleep(self.run_interval)
        

class TaskMaster:
    def __init__(self, cfg):
        ipmi_setup = cfg["ipmi_setup"]
        
        if ipmi_setup["ipmi_ip"] == '0.0.0.0':
            ipmi_setup["ipmi_ip"] = None
        
        if ipmi_setup["machine_type"] == "idrac":
            self.set_fan_fn = set_fan_idrac
        elif ipmi_setup["mahine_type"] == "c6220":
            self.set_fan_fn = set_fan_c6220
        else:
            assert False
        del ipmi_setup["machine_type"]
        self.ipmi_setup = ipmi_setup
        
        self.master_ips = cfg["tasks"]["master"]["children"]
        self.master_port = cfg["tasks"]["master"]["port"]
        
        self.children = cfg["tasks"]["master"]["children"]
        self.port = cfg["tasks"]["master"]["port"]
        self.run_interval = cfg["run_interval"]
        # for child in cfg["tasks"]["master"]["children"]:
            # socket_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # socket_server.connect((child, cfg["tasks"]["master"]["port"]))
            # self.children.append(socket_server)
        
    def run_iter(self):
        speeds = list()
        request = "get"
        for i, child in enumerate(self.children):
            try:
                child_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                child_socket.connect((child, self.port))
                child_socket.send(request.encode('utf-8'))
                response = child_socket.recv(255).decode('utf-8')
                speed = float(response)
                speeds.append(speed)
                logging.info(f"response={response}, speed={speed}")
                child_socket.close
            except ConnectionRefusedError as e:
                pass
        if len(speeds) != len(self.children):
            speeds.append(1)
        speed = max(speeds)
        self.set_fan_fn(speed, **self.ipmi_setup)

    def run(self):
        while True:
            self.run_iter()
            time.sleep(self.run_interval)


class TaskClient:
    def __init__(self, cfg):
        devices = cfg["devices"]
        self.run_interval = cfg["run_interval"]
        
        self.devices = list()
        for device_cfg in devices:
            device = device_cfg["device"]
            if device == 'cpu':
                temp_fn = get_cpu_temp
            elif device == 'cuda' or device == 'gpu':
                temp_fn = get_gpu_temp
            del device_cfg['device']
            fan_speed_alg = FanSpeedAlg(**device_cfg)
            self.devices.append((temp_fn, fan_speed_alg))
        self.port = cfg["tasks"]["child"]["port"]
        self.socket_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_server.bind(('0.0.0.0', cfg["tasks"]["child"]["port"]))
        self.socket_server.listen(16)
    
    def run(self):
        logging.debug("client started 1")
        while True:
            client, _ = self.socket_server.accept()
            self.handle_client(client)
                    
    def handle_client(self, client):
        request = None
        while request != "quit":
            try:
                request = client.recv(255)
            except ConnectionResetError:
                break
            if len(request) == 0:
                break
            request = request.decode('utf-8')
            speeds = list()
            for temp_fn, fan_speed_alg in self.devices:
                temp = temp_fn()
                speed = fan_speed_alg.step(temp) 
                speeds.append(speed)
                logging.info(f"temp={temp}, speed={speed}")
            speed = max(speeds)
            response = str(speed)
            client.send(response.encode('utf-8'))
        client.close()


if __name__ == '__main__':
    threads = list()
    asyncio_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(asyncio_loop)
    if "standalone" in cfg["tasks"]:
        task = TaskStandalone(cfg)
        thread = threading.Thread(target=task.run)
        threads.append(thread)
    if "master" in cfg["tasks"]:
        task = TaskMaster(cfg)
        thread = threading.Thread(target=task.run)
        threads.append(thread)
    if "child" in cfg["tasks"]:
        task = TaskClient(cfg)
        # asyncio_loop.create_task(task.run())
        thread = threading.Thread(target=task.run)
        threads.append(thread)
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    asyncio_loop.close()
    