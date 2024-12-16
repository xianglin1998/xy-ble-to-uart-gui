import re
import threading
import time
import traceback
import typing
import serial

import log

logger = log.getLogger("BLE转串口适配器通信日志")


class BLEDevice:

    def __init__(self):
        self.mac: str = ""  # 蓝牙设备地址
        self.mac_type: int = 0  # 地址类型，0-静态地址 1-随机地址
        self.rssi: int = 0
        self.name: str = ""  # 蓝牙设备名

    def __str__(self):
        return ("{"
                f"mac: '{self.mac}', "
                f"mac_type: {self.mac_type}, "
                f"rssi: {self.rssi}, "
                f"name: '{self.name}'"
                "}")


class AdapterException(Exception):
    """
        适配器异常
    """


class BLEToUartAdapter:
    """
        蓝牙转串口的适配器的封装类
    """

    RESP_OK = "OK"
    RESP_ERROR = "ERROR"
    RESP_READY = "+READY"

    class ScanState:
        STOPPED = 0
        RUNNING = 1
        STOPPING = 2

    # 新一手册中的参数到波特率的映射表
    BAUDRATE_MAP = {
        0: 9600,
        1: 14400,
        2: 19200,
        3: 38400,
        4: 57600,
        5: 115200,
        6: 230400,
    }

    def __init__(self, port):
        self._ser: serial.Serial = serial.Serial()
        self._ser.timeout = 0
        self._ser.port = port
        self._ser.baudrate = 115200

        self.baudrate_current_index = -1

        self.scan_state: int = self.ScanState.STOPPED  # 标志当前是否有在Scan，如果有的话，其他一切操作都不能进行
        self.has_stop_scan_by_cmd = False  # 标志当前是否有尝试过使用指令去结束扫描
        self.scan_device_map = {
            # 设备信息的映射表，布局为：
            # mac地址: 设备实例
        }

        # 设备发现时的回调
        self.callback_on_device_found: typing.Callable[[BLEDevice], None] | None = None

    @staticmethod
    def from_baudrate_get_index(baudrate: int):
        """
            从映射表中的值获取对应在新一的手册中描写的索引
        @param baudrate: 波特率
        @return:
        """
        for index in BLEToUartAdapter.BAUDRATE_MAP.keys():
            if BLEToUartAdapter.BAUDRATE_MAP[index] == baudrate:
                return index

    def open(self):
        """
            打开适配器
        @return:
        """
        try:
            if not self._ser.is_open:
                self._ser.open()  # 首先需要打开串口设备，为后续的通信做准备
                threading.Thread(target=self.thread_scan, ).start()  # 在开启设备成功后，再启用扫描用的子线程
            return True
        except Exception as e:
            logger.error(f"打开串口失败： {e}")
            return False

    def close(self):
        try:
            self._ser.close()
        except Exception as e:
            logger.error(f"关闭串口失败：{e}")

    def check_is_ble_to_uart_device(self):
        """
            检查是否是BLE转串口的模块
        @return:
        """
        self.baudrate_current_index = self.detect_baudrate()
        if self.baudrate_current_index == -1:
            raise AdapterException("无法自动侦测到波特率，可能该设备并不是蓝牙转串口模块")
        baudrate_current_value = self.BAUDRATE_MAP[self.baudrate_current_index]
        logger.info(f"侦测到的波特率是：{baudrate_current_value}")

    def __enter__(self):
        """
            兼容with语法
        """
        if not self.open():
            raise serial.SerialException("打开串口失败，请审查日志排查问题")
        self.check_is_ble_to_uart_device()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
            兼容with语法
        """
        self.stop_scan()  # 如果存在扫描，则停止扫描后再认为关闭完成
        self.close()

    def wait_response(self, end_lines: str | typing.List[str], timeout: float,
                      on_line_callback: typing.Callable[[str], None] = None,
                      on_stop_callback: typing.Callable[[], bool] = None) -> str | typing.List[str] | None:
        """
            等待应答
        @param on_stop_callback: 在需要停止时，此回调函数返回True
        @param on_line_callback: 出现新的一行时，如果是多行应答指令，可以实时处理
        @param timeout: 等待应答最多等多久？
        @param end_lines: 应答以什么为结尾？
        @return:
        """
        lines = []
        is_1_str = True
        if not isinstance(end_lines, str):
            if not isinstance(end_lines, (list, tuple)):
                raise TypeError("等待蓝牙转串口模块的AT指令应答要么是一个字符串，要么是一个字符串数组，不支持其他类型")
            is_1_str = False
        time_start = time.time()
        line_buffer = bytearray()
        while True:
            # 超时内等待结果
            if time.time() - time_start > timeout:
                # 指令发送不正常或者应答结束标志行不对就会导致这个问题，当然，不排查转串口模块有问题
                raise TimeoutError("等待超时，BLE转串口模块没有正确应答AT指令")

            # 在超时内读取一行
            data_read = self._ser.read()
            if len(data_read) > 0:
                line_buffer.extend(data_read)
                # logger.info(line_buffer)
            if not line_buffer.endswith(b"\r\n"):
                time.sleep(0.001)
                continue
            resp_line = line_buffer.decode(encoding="utf-8", errors="ignore")
            line_buffer.clear()  # 记得一行处理完毕后，清除掉BUFFER

            # logger.info(f"应答行：{resp_line}")
            # 检查是否需要实时处理
            if on_line_callback is not None:
                on_line_callback(self.extract_from_at_response(resp_line, end_lines))

            # 检查是否需要停止处理
            if callable(on_stop_callback) and on_stop_callback():
                return None

            # 追加到应答结果中
            lines.append(resp_line)
            # 检查是否结束
            if is_1_str and end_lines in resp_line:
                break

            if not is_1_str:
                finish = False
                for end_line_start_with in end_lines:
                    # logger.info(f"{resp_line} -- {end_line_start_with} --- {end_line_start_withs}")
                    if end_line_start_with in resp_line:
                        finish = True
                        break
                if finish:
                    break

        return lines[0] if len(lines) == 1 else lines  # 这里我做一个封装，如果应答结果是单行的，那就直接返回一行字符串

    def send(self, cmd: str):
        """
            发送指令
        @param cmd: 指令本身，不带AT+开头的字符串，也不需要带回车换行结尾
        @return:
        """
        cmd = f"AT+{cmd}\r\n"
        # logger.info(f"最终执行的指令是：{cmd}")
        self._ser.write(cmd.encode("ASCII"))

    @staticmethod
    def extract_from_at_response(line: str, resp_end_lines: str | typing.List[str]):
        """
            从一行应答中提取AT指令的有效消息
        @param resp_end_lines: 应答结束标志行
        @param line: 应答行
        @return:
        """
        if isinstance(resp_end_lines, str):
            if resp_end_lines in line:
                ser_obj = re.search(r"(" + re.escape(resp_end_lines) + ".*?)\r\n", line)
                # print(ser_obj)
                if ser_obj is not None:
                    line = ser_obj.group(1)
            else:
                line = line.replace("\r\n", "")  # 非结束行，我们依旧需要去除尾部的回车换行
        else:
            for end_line in resp_end_lines:
                if end_line in line:
                    ser_obj = re.search(r"(" + re.escape(end_line) + ".*?)\r\n", line)
                    # print(ser_obj)
                    if ser_obj is not None:
                        line = ser_obj.group(1)
                else:
                    line = line.replace("\r\n", "")
        return line

    def exec(self, cmd: str, resp_end_lines: str | typing.List[str], timeout: float = 3,
             on_line_callback: typing.Callable[[str], None] = None):
        """
            执行指令
        @param on_line_callback: 在有一行应答时，如果需要关心实时的一个应答结果，可以直接实现此回调进行处理
        @param timeout: 等待超时
        @param cmd: 指令
        @param resp_end_lines: 接受的应答结束行
        @return:
        """
        if self.scan_state != self.ScanState.STOPPED:
            raise RuntimeError("在扫描的时候，不允许任何其他指令执行，请开发者做好停止扫描再执行指令的逻辑")
        if cmd.startswith("+"):
            logger.warning("'AT+'已经被自动添加到头部，请开发者检查是否是多余的添加，还是协议更新了，"
                           "如果是协议更新请检查适配。")
        # 执行指令
        time.sleep(0.5)  # 新一的模块有点毛病，回复了指令不等于芯片在正常工作，因此我们需要先等一会儿
        self.send(cmd)
        # 等待应答
        resp = self.wait_response(resp_end_lines, timeout, on_line_callback)
        # 初步处理一下应答，因为应答数据可能包含透传过来的数据
        resp = [resp] if isinstance(resp, str) else resp
        for i in range(len(resp)):
            line: str = resp[i]
            resp[i] = self.extract_from_at_response(line, resp_end_lines)

        return resp[0] if len(resp) == 1 else resp

    def on_scan_found(self, device: BLEDevice):
        # logger.info(f"扫描到的设备信息：{device}")
        if self.callback_on_device_found is not None:  # 回调通知一下设备发现的消息
            self.callback_on_device_found(device)

    def thread_scan(self):
        """
            子线程，在此线程中进行扫描操作
        @return:
        """

        def on_scan_line(line: str):
            # 跳过一些非设备信息的打印
            if line.startswith("+"):
                return

            # 解析设备信息
            info_arr = line.split(' ', 3)
            # 查看是否已经有当前设备了，如果有，取出之前的设备实例直接更新
            mac_from_line = info_arr[0]
            if mac_from_line in self.scan_device_map:
                ble_device = self.scan_device_map[mac_from_line]
            else:
                ble_device = BLEDevice()
                self.scan_device_map[mac_from_line] = ble_device  # 将设备实例放入到映射表中
            # 赋值一定存在的基础信息
            ble_device.mac = mac_from_line
            ble_device.mac_type = int(info_arr[1])
            ble_device.rssi = int(info_arr[2])
            # 名字不一定存在，因为需要确认
            if len(info_arr) == 4:
                ble_device.name = info_arr[3]
            # logger.info(ble_device)
            self.on_scan_found(ble_device)

        while self._ser.is_open:
            if self.scan_state == self.ScanState.RUNNING:
                try:
                    # 执行扫描
                    time.sleep(0.5)
                    self.send("SCAN=1")
                    self.has_stop_scan_by_cmd = False
                    try:
                        time_start = time.time()

                        # 内部函数，用于检查是否需要停止等待应答
                        def on_stop_check():
                            time_end = time.time() - time_start

                            # 快速重启搜索  # TODO 此逻辑可能导致信号差的设备无法搜索到，待验证稳定性
                            if time_end > 0.8:
                                if not self.has_stop_scan_by_cmd:
                                    self.send("SCAN=0")
                                    self.has_stop_scan_by_cmd = True
                                return False

                            # 检测到正在停止扫描，我们需要检查扫描的剩余时间，如果还要超过1S才能结束，
                            # 那我们就提前发送指令结束，否则的话直接等扫描过程自己结束即可
                            if self.scan_state == self.ScanState.STOPPING:
                                if time_end > 1 and not self.has_stop_scan_by_cmd:
                                    self.send("SCAN=0")
                                    self.has_stop_scan_by_cmd = True
                                return False  # 让外部等待应答的处理函数等待结束执行

                        self.wait_response("+SCAN END", 10, on_scan_line, on_stop_check)
                        # logger.info(f"本次蓝牙设备扫描耗时：{time.time() - time_start}")
                    except TimeoutError:
                        pass  # 忽略此处的超时异常
                except serial.SerialException as se:
                    if self.is_not_port_permission_error(str(se)):  # 遇到无权限的问题，就可能是串口重启错误了
                        self.close()
                        self.scan_state = self.ScanState.STOPPED
                except Exception as e:
                    logger.error(f"在扫描线程中出现了可能打断行解析的致命异常：\n{traceback.format_exception(e)}")
            else:
                self.scan_state = self.ScanState.STOPPED
                time.sleep(0.01)

    @staticmethod
    def is_not_port_permission_error(error_msg: str):
        """
            检查是否是串口无权限的错误消息
        @param error_msg: 错误消息
        @return:
        """
        return 'PermissionError' in error_msg

    def start_scan(self):
        """
            启动蓝牙扫描，同时禁止其他的指令执行
        @return:
        """
        self.scan_state = self.ScanState.RUNNING

    def stop_scan(self):
        """
            停止蓝牙扫描，并且等待彻底停止完成
        @return:
        """
        if self.scan_state == self.ScanState.STOPPED:
            return
        self.scan_state = self.ScanState.STOPPING
        while self.scan_state != self.ScanState.STOPPED:  # 一直等，等到扫描彻底结束
            time.sleep(0.01)

    @staticmethod
    def get_data(line: str):
        """
            从应答行中获得有效的数据部分
        @param line: 应答行
        @return:
        """
        data_start_index = line.index(':')
        return line[data_start_index + 1:]

    def detect_baudrate(self) -> int:
        """
            识别一下当前的波特率
        @return: 如果识别成功，那么将会返回 self.baudrate_map中的键，否则返回-1
        """
        # 优先尝试38400，其次才是115200
        try_baudrate_list = [3, 5, 0, 6, 2, 4, 1]
        for baudrate_index in try_baudrate_list:
            # 先把波特率切换过去
            self._ser.baudrate = self.BAUDRATE_MAP[baudrate_index]
            # 然后尝试通信
            try:
                self.get_version(3)
                return baudrate_index
            except TimeoutError:
                pass
        return -1

    def try_change_baudrate(self, baudrate: int):
        """
            自动改波特率为38400，以此做到兼容其他的上位机的效果
        @param baudrate: 波特率参数，并非波特率本身，详情请看新一的手册中设置波特率的章节
        @return:
        """
        if baudrate in self.BAUDRATE_MAP:
            if baudrate == self.baudrate_current_index:
                logger.warning("检测到当前已经是目标波特率，将自动跳过修改。")
                return
            for try_count in range(3):
                try:
                    # 先执行指令修改波特率，并且等待有成功的应答
                    resp = self.exec_set(f"UART={baudrate}", "设置波特率")
                    logger.info(f"切换波特率的指令已经完成执行：{resp}")
                    # 然后再在pyserial端切换到对应的波特率
                    self._ser.baudrate = self.BAUDRATE_MAP[baudrate]
                    # 回读验证是否更改成功
                    resp = self.exec_get_no_error("UART")
                    baudrate_index_from_device = int(resp)
                    logger.info(f"切换波特率成功，当前的波特率是：{self.BAUDRATE_MAP[baudrate_index_from_device]}")
                    self.baudrate_current_index = baudrate_index_from_device
                    return
                except TimeoutError:
                    pass
            raise AdapterException("设置波特率失败")
        else:
            raise ValueError(f"根据新一的手册，波特率只能是 {self.BAUDRATE_MAP}")

    def soft_reset(self):
        """
            软复位BLE转串口的模块
        @return:
        """
        self.exec("REBOOT=1", "+READY")

    # 连接设备的应答
    RESP_CONNECTED = "+CONNECTED"
    RESP_CON_TIMEOUT = "+CONNECT TIMEOUT"

    def connect_slave_device(self, mac: str, typ: int):
        """
            连接到设备
        @param mac: 设备的MAC地址
        @param typ: MAC地址的类型
        @return:
        """
        cmd = f"CONN={mac},{typ}"
        resp = self.exec(cmd, [self.RESP_CONNECTED, self.RESP_CON_TIMEOUT], timeout=10)
        if resp == self.RESP_CON_TIMEOUT:
            raise TimeoutError(f"BLE转串口模块上报连接到MAC为{mac}，MAC Type为{typ}的设备超时")

    def get_slave_device_connected(self) -> str | None:
        """
            获取当前已连接的蓝牙设备
        @return: 蓝牙地址
        """
        resp = self.exec("DEV?", ["+DEV", self.RESP_ERROR])
        if resp == self.RESP_ERROR:
            return None
        info_arr = self.get_data(resp).split(',')
        if info_arr[0] == '0':  # 蓝牙转串口是主设备，连接到的目标控制器或者仪表是从设备，因此在新一的手册中，从设备应当是字符串 '0'
            return info_arr[1]
        return None

    def disconnect_slave_device(self):
        """
            断开所有的从设备连接，也就是断开适配器主动连接的目标蓝牙设备
        @return:
        """
        resp = self.exec(f"DISCONN=0", ["+DISCONN", self.RESP_ERROR])
        if resp == self.RESP_ERROR:
            raise AdapterException("断开设备失败，可能设备并没有连接")

    def get_device_by_name(self, name: str) -> BLEDevice | None:
        """
            根据名字获得设备的实例
        @param name: 名字
        @return:
        """
        for device in self.scan_device_map.values():
            device: BLEDevice = device
            if device.name == name:
                return device
        return None

    def exec_set(self, cmd: str, action_name: str, timeout: float = 3):
        """
            通用设置指令的执行封装函数
        @param timeout: 应答超时，以秒为单位
        @param cmd: 要执行的指令，不带AT+开头，不带\r\n结尾
        @param action_name: 操作的名字，在出现异常时，此名称将携带在异常消息中一起抛出
        @return:
        """
        resp = self.exec(cmd, [self.RESP_ERROR, self.RESP_OK], timeout)
        if resp == self.RESP_ERROR:
            raise AdapterException(f"执行 '{action_name}' BLE转串口模块上报错误")

    def exec_get_no_error(self, cmd: str, timeout: float = 3):
        """
            执行获取指令
        @param timeout: 应答超时，以秒为单位
        @param cmd: 要执行的指令，不到AT+开头，不带 ?\r\n结尾
        @return:
        """
        resp = self.exec(f"{cmd}?", f"+{cmd}", timeout)
        return self.get_data(resp)

    def get_version(self, timeout: float = 1):
        """
            获取当前蓝牙转串口的适配器的固件版本号
        @return:
        """
        return self.exec_get_no_error("VER", timeout)

    def change_adv_interval(self, adv_interval: int):
        """
            修改广播间隔
        @param adv_interval: 广播间隔，以毫秒为单位，支持20-10240毫米
        @return:
        """
        self.exec_set(f"INTVL={adv_interval}", f"设置广播间隔为{adv_interval}")

    def set_auto_reconnect_device(self, device_mac: str, mac_type: int):
        """
            设置自动重连到指定的设备
        @param device_mac: 设备的mac地址
        @param mac_type: 设备的类型
        @return:
        """
        self.exec_set(f"AUTO_MAC={device_mac},{mac_type}", "设置自动重连的设备")

    def set_auto_reconnect_enable(self, enable: bool):
        """
            设置自动重连功能是否使能
        @param enable: 是否使能
        @return:
        """
        self.exec_set(f"AUTO_CFG={1 if enable else 0}", f"设置自动重连功能为 {'使能' if enable else '禁用'}")

    def get_auto_reconnect_enable(self) -> bool:
        """
            判断当前是否启用自动回连
        @return:
        """
        return self.exec_get_no_error("AUTO_CFG") == '1'

    def del_auto_reconnect_list(self):
        """
            删除自动重连列表
        @return:
        """
        self.exec_set(f"AUTO_DEL", "删除自动重连列表")

    def set_transfer_main_service_uuid(self, uuid_s):
        """
            设置透传主服务的UUID
        @param uuid_s: 服务的UUID，16bit 格式或 128bit 格式的 UUID
        @return:
        """
        self.exec_set(f"UUIDS={uuid_s}", "设置蓝牙透传主服务UUID")

    def get_transfer_main_service_uuid(self):
        """
            获取透传主服务的UUID
        @return:
        """
        return self.exec_get_no_error("UUIDS")

    def set_transfer_characteristic_w_uuid(self, uuid_w):
        """
            设置透传服务的写特征的UUID
        @param uuid_w: 特征的UUID，，16bit 格式或 128bit 格式的 UUID
        @return:
        """
        self.exec_set(f"UUIDW={uuid_w}", "设置蓝牙透传写特征UUID")

    def get_transfer_characteristic_w_uuid(self):
        """
            获取透传服务的写特征的UUID
        @return:
        """
        return self.exec_get_no_error("UUIDW")

    def set_transfer_characteristic_n_uuid(self, uuid_n):
        """
            设置透传服务的通知特征的UUID
        @param uuid_n: 特征的UUID，，16bit 格式或 128bit 格式的 UUID
        @return:
        """
        self.exec_set(f"UUIDN={uuid_n}", "设置蓝牙透传通知特征UUID")

    def get_transfer_characteristic_n_uuid(self):
        """
            获取透传服务的通知特征的UUID
        @return:
        """
        return self.exec_get_no_error("UUIDN")

    def is_opened(self) -> bool:
        """
            判断是否是打开状态
        @return:
        """
        if self._ser is None:
            return False
        return self._ser.is_open


def test():
    with BLEToUartAdapter("com23") as adapter:
        # # 切换波特率
        # if adapter.baudrate_current_index == 3:
        #     adapter.try_change_baudrate(5)
        # else:
        #     adapter.try_change_baudrate(3)

        # 执行软复位
        # adapter.exec("REBOOT=1", "+READY")
        # logger.info(f"软复位完成，BLE转串口模块已完成重置")

        # 执行本模块的MAC地址获取
        # resp = adapter.exec("MAC?", "+MAC")
        # logger.info(f"测试读取设备的MAC地址为：{adapter.get_data(resp)}")
        #
        # adapter.start_scan()
        # time.sleep(3)
        # adapter.stop_scan()
        # logger.info("结束扫描，执行余下测试指令")

        # # 根据名字得到设备
        # device = adapter.get_device_by_name("MyDevice")
        # if device is not None:
        #     logger.info(f"开始连接到设备：{device}")
        #     adapter.connect_slave_device(device.mac, device.mac_type)
        #     logger.info(f"连接成功")
        # else:
        #     logger.warning("没有搜索到测试用的控制器，所以没办法去连接。")

        # 获取当前已经连接的设备的mac地址
        # mac_for_connected = adapter.get_slave_device_connected()
        # logger.info(f"当前已连接的设备是：{mac_for_connected}")

        # 如果已经连接，测试断开连接的指令
        # if mac_for_connected is not None:
        #     adapter.disconnect_slave_device(mac_for_connected)
        #     logger.info("断开设备连接成功")

        resp = adapter.exec("TXPOWER?", "+TXPOWER")
        data = adapter.get_data(resp)
        logger.info(f"发射功率为：{data}")

        while True:
            time.sleep(1)


if __name__ == '__main__':
    test()
