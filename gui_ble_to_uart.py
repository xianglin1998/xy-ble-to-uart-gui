import datetime
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import serial.tools.list_ports

import bleuart
import log
import widget

DEFAULT_BACKGROUND = "#3F3F3F"

logger = log.getLogger("BLE转串口桥接GUI日志")


class App:

    def __init__(self, master):
        """
            GUI由此类封装
        @param master: 根窗口句柄
        """
        self.root = master

        # 存放串口对象的数组
        from serial.tools.list_ports_common import ListPortInfo
        self.port_obj_list = [ListPortInfo]
        # 存放当前选择的串口号
        self.port_num_selected = None

        # 存放已经打开的适配器的句柄
        self.ble_adapter: bleuart.BLEToUartAdapter | None = None

        # 串口选择下拉列表
        self.frame_serial = tk.Frame(self.root, bg=DEFAULT_BACKGROUND)
        self.frame_serial.pack(pady=16)

        self.com_label = tk.Label(
            self.frame_serial,
            text="蓝牙适配器: ",
            bg=DEFAULT_BACKGROUND,
            fg="white",
            font=("微软雅黑", 10, "bold")
        )
        self.com_label.pack(side=tk.LEFT)
        self.var_com_port_selected = tk.StringVar()
        self.port_list = ttk.Combobox(self.frame_serial, width=30, textvariable=self.var_com_port_selected,
                                      postcommand=self.show_ports, state="readonly")
        self.port_list.bind("<<ComboboxSelected>>", self.on_port_select)
        self.port_list.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        widget.disable_combobox_mouse_wheel(self.port_list)

        # 在适配器成功的初始化之后，我们可以显示一些设备相关的UI，此时需要一个整体容纳适配器的UI
        self.frame_device_fun = tk.Frame(self.root, bg=DEFAULT_BACKGROUND)
        self.frame_device_fun.pack(expand=True, fill=tk.BOTH, padx=10)

        # UI中下部分是设备相关的UI
        self.frame_center_content = tk.Frame(self.frame_device_fun, bg="green")
        self.frame_center_content.pack(fill=tk.BOTH, expand=True)

        self.frame_ble_device_list = tk.Frame(self.frame_center_content, bg=DEFAULT_BACKGROUND)
        self.frame_ble_device_list.pack(expand=True, fill=tk.BOTH)
        ble_device_list_x_scroll = ttk.Scrollbar(self.frame_ble_device_list, orient=tk.HORIZONTAL)
        ble_device_list_y_scroll = ttk.Scrollbar(self.frame_ble_device_list, orient=tk.VERTICAL)
        ble_device_list_x_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        ble_device_list_y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        ble_device_columns = ["蓝牙名", "MAC地址", "MAC类型", "RSSI", "最后更新"]
        self.tree_view_device_list = ttk.Treeview(
            master=self.frame_ble_device_list,  # 父容器
            columns=ble_device_columns,  # 列标识符列表
            show='headings',  # 隐藏首列
            style='Treeview',  # 样式
            selectmode=tk.BROWSE,
            xscrollcommand=ble_device_list_x_scroll.set,  # x轴滚动条
            yscrollcommand=ble_device_list_y_scroll.set  # y轴滚动条
        )
        ble_device_list_x_scroll.config(command=self.tree_view_device_list.xview)
        ble_device_list_y_scroll.config(command=self.tree_view_device_list.yview)
        self.tree_view_device_list.pack(expand=True, fill=tk.BOTH)
        self.tree_view_device_list.bind("<Double-1>", self.on_ble_device_select)

        # 绘制表头
        for column in ble_device_columns:
            self.tree_view_device_list.heading(column=column, text=column, anchor=tk.CENTER)  # 定义表头
            width = 100
            if column == ble_device_columns[0]:
                width = 180
            if column == ble_device_columns[3]:
                width = 60
            if column == ble_device_columns[4]:
                width = 140
            self.tree_view_device_list.column(column=column, width=width, anchor=tk.CENTER, )  # 定义列

        # 底部区域可以用来显示一些功能按钮，比如切换波特率之类的
        self.frame_bottom_content = tk.Frame(self.frame_device_fun, bg=DEFAULT_BACKGROUND)
        self.frame_bottom_content.pack(anchor=tk.NW, side=tk.TOP, fill=tk.X)

        # 第一行内容
        frame_bottom_content_line_1 = tk.Frame(self.frame_bottom_content, bg=DEFAULT_BACKGROUND)
        frame_bottom_content_line_1.pack(expand=True, fill=tk.BOTH, padx=5, pady=(10, 5), )

        tk.Label(
            frame_bottom_content_line_1,
            text="只显示以指定名称开头的设备: ",
            bg=DEFAULT_BACKGROUND,
            fg="white",
        ).pack(side=tk.LEFT)
        self.var_filter_device_name = tk.StringVar(value="")
        tk.Entry(
            frame_bottom_content_line_1,
            textvariable=self.var_filter_device_name,
            bg="white",
            fg=DEFAULT_BACKGROUND,
        ).pack(side=tk.LEFT)

        # 开始搜索设备的按钮，开启搜索后，其他的按钮功能全部都需要禁用掉
        self.btn_start_ble_scan = tk.Button(
            frame_bottom_content_line_1,
            fg="white",
            command=self.on_start_ble_device_scan_click,
        )
        self.btn_start_ble_scan.pack(side=tk.RIGHT, padx=5)

        # 重置扫描到的设备列表的按钮
        self.btn_clear_device_list = tk.Button(
            frame_bottom_content_line_1,
            text="清空上方扫描列表",
            bg=DEFAULT_BACKGROUND,
            fg="white",
            command=self.on_clear_device_list_click,
        )
        self.btn_clear_device_list.pack(side=tk.RIGHT, padx=5)

        # 软重置蓝牙适配器的按钮
        self.btn_soft_reset_adapter = tk.Button(
            frame_bottom_content_line_1,
            text="适配器Reset",
            bg=DEFAULT_BACKGROUND,
            fg="white",
            command=self.on_soft_reset_adapter_click,
        )
        self.btn_soft_reset_adapter.pack(side=tk.RIGHT, padx=5)

        # 勾选框，控制在连接的时候启用或者禁用自动重连相关的操作
        self.var_config_auto_reconnect_on_connect_enable = tk.BooleanVar(value=True)
        style_cbb = ttk.Style()
        style_cbb.configure('Red.TCheckbutton',
                            indicatorbackground="white", indicatorforeground="black",
                            background=DEFAULT_BACKGROUND, focuscolor='',
                            foreground="white")
        style_cbb.map('TCheckbutton',
                      background=[('active', "grey"), ],
                      indicatorcolor=[('selected', DEFAULT_BACKGROUND), ])
        self.checkbox_auto_reconnect_on_connect = ttk.Checkbutton(
            frame_bottom_content_line_1,
            text='连接时配置自动重连',
            variable=self.var_config_auto_reconnect_on_connect_enable,
            onvalue=True,
            offvalue=False,
            style='Red.TCheckbutton',
        )
        self.checkbox_auto_reconnect_on_connect.pack(side=tk.RIGHT, padx=5)

        # 第二行内容
        frame_bottom_content_line_2 = tk.Frame(self.frame_bottom_content, bg=DEFAULT_BACKGROUND)
        frame_bottom_content_line_2.pack(expand=True, fill=tk.BOTH, padx=5, pady=(10, 5), )

        # 波特率切换的部分
        frame_baudrate = tk.Frame(frame_bottom_content_line_2, bg=DEFAULT_BACKGROUND)
        frame_baudrate.pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(frame_baudrate, bg=DEFAULT_BACKGROUND, text="波特率切换：", fg="white").pack(side=tk.LEFT)
        self.var_baudrate = tk.IntVar()
        self.baudrate_list = ttk.Combobox(
            frame_baudrate, width=30, textvariable=self.var_baudrate,
            values=list(bleuart.BLEToUartAdapter.BAUDRATE_MAP.values()))
        self.baudrate_list.pack(side=tk.LEFT)
        self.baudrate_list.bind("<<ComboboxSelected>>", self.on_baudrate_select)
        widget.disable_combobox_mouse_wheel(self.baudrate_list)

        # 服务特征的UUID的配置部分
        frame_uuid_config = tk.Frame(
            frame_bottom_content_line_2,
            bg=DEFAULT_BACKGROUND,
            highlightbackground="grey",
            borderwidth=2,
            highlightthickness=1,
            # text="透传数据通道（服务与特征）配置",
            # fg="white",
        )
        frame_uuid_config.pack(side=tk.RIGHT, padx=(0, 5))
        frame_uuid_config.grid_columnconfigure((1, 3, 5), weight=1, uniform="column")

        # 主服务的UUID的配置项
        tk.Label(frame_uuid_config, bg=DEFAULT_BACKGROUND, fg="white", text="主服务：").grid(column=0, row=0, )
        self.var_uuid_service_main = tk.StringVar()
        self.entry_input_main_service = tk.Entry(
            frame_uuid_config,
            bg=DEFAULT_BACKGROUND,
            fg="white",
            disabledbackground="#DCDCDC",
            textvariable=self.var_uuid_service_main,
        )
        self.entry_input_main_service.grid(column=1, row=0, )

        # 写特征的UUID的配置项
        tk.Label(frame_uuid_config, bg=DEFAULT_BACKGROUND, fg="white", text="通知特征：").grid(column=2, row=0, )
        self.var_uuid_characteristic_notify = tk.StringVar()
        self.entry_input_notify_characteristic = tk.Entry(
            frame_uuid_config,
            bg=DEFAULT_BACKGROUND,
            fg="white",
            disabledbackground="#DCDCDC",
            textvariable=self.var_uuid_characteristic_notify,
        )
        self.entry_input_notify_characteristic.grid(column=3, row=0, )

        # 通知特征的UUID的配置项
        tk.Label(frame_uuid_config, bg=DEFAULT_BACKGROUND, fg="white", text="写特征：").grid(column=4, row=0, )
        self.var_uuid_characteristic_write = tk.StringVar()
        self.entry_input_write_characteristic = tk.Entry(
            frame_uuid_config,
            bg=DEFAULT_BACKGROUND,
            fg="white",
            disabledbackground="#DCDCDC",
            textvariable=self.var_uuid_characteristic_write,
        )
        self.entry_input_write_characteristic.grid(column=5, row=0, )

        self.btn_update_uuid_to_device = tk.Button(
            frame_uuid_config,
            bg=DEFAULT_BACKGROUND,
            fg="white",
            text="设置UUID",
            command=self.on_update_transfer_service_uuid,
        )
        self.btn_update_uuid_to_device.grid(column=6, row=0, padx=(10, 0))

        self.device_adv_record_map = {
            # 设备的mac地址到设备的相关信息与最后一次更新的时间戳的映射表
            # 结构如下：
            # mac: {
            #     device: bleuart.BLEDevice,
            #     time: 时间戳
            # }
        }
        # 首次启动扫描设备广播更新时间
        self.task_check_device_adv_time()

        # 首次启动，更新view状态为未启动扫描
        self.set_view_for_scan_state(False)
        # 更新view未适配器未打开的状态
        self.set_view_for_adapter_close(True)

    def set_view_for_scan_state(self, scanning: bool):
        """
            设置扫描按钮的UI样式
        @param scanning: 是否是启动扫描的状态
        @return:
        """
        if scanning:
            self.btn_start_ble_scan.config(text="取消扫描", bg="red")
            self.baudrate_list.config(state=tk.DISABLED)
            self.btn_soft_reset_adapter.config(state=tk.DISABLED)
            self.port_list.config(state=tk.DISABLED)
            self.entry_input_main_service.config(state=tk.DISABLED)
            self.entry_input_notify_characteristic.config(state=tk.DISABLED)
            self.entry_input_write_characteristic.config(state=tk.DISABLED)
            self.btn_update_uuid_to_device.config(state=tk.DISABLED)
        else:
            self.btn_start_ble_scan.config(bg="green", text="开启扫描")
            self.baudrate_list.config(state="readonly")
            self.btn_soft_reset_adapter.config(state=tk.NORMAL)
            self.port_list.config(state="readonly")
            self.entry_input_main_service.config(state=tk.NORMAL)
            self.entry_input_notify_characteristic.config(state=tk.NORMAL)
            self.entry_input_write_characteristic.config(state=tk.NORMAL)
            self.btn_update_uuid_to_device.config(state=tk.NORMAL)

    def set_view_for_adapter_close(self, closed: bool):
        """
            设置适配器关闭或者开启的UI样式
        @param closed: 是否已关闭适配器
        @return:
        """
        # 要更新UI状态的视图实例
        view_handle = [
            self.btn_start_ble_scan,
            self.baudrate_list,
            self.btn_soft_reset_adapter,
            self.entry_input_main_service,
            self.entry_input_notify_characteristic,
            self.entry_input_write_characteristic,
            self.btn_update_uuid_to_device,
        ]
        for view in view_handle:
            if closed:
                view.config(state=tk.DISABLED)
            else:
                if isinstance(view, ttk.Combobox):
                    view.config(state="readonly")
                else:
                    view.config(state=tk.NORMAL)
        return

    def update_view_if_adapter_is_closed(self):
        """
            更新视图，如果适配器已关闭
        @return:
        """
        if self.is_adapter_closed():
            self.set_view_for_adapter_close(True)
        else:
            self.set_view_for_adapter_close(False)

    def clear_port_selected(self):
        """
            清除掉已选择的串口，包括UI和业务逻辑相关的缓存
        @return:
        """
        self.port_num_selected = None
        self.var_com_port_selected.set("")

    def clear_device_list(self):
        """
            清空显示的列表
        @return:
        """
        # 清空显示扫描到的设备列表的view
        self.tree_view_device_list.delete(*self.tree_view_device_list.get_children())
        # 清空缓存中记录的最后更新时间
        self.device_adv_record_map.clear()

    def is_adapter_closed(self):
        """
            判断适配器是否已经关闭
        @return:
        """
        if self.ble_adapter is None or not self.ble_adapter.is_opened():
            return True
        return False

    def task_check_device_adv_time(self):
        """
            检查时间
        @return:
        """
        # 仅在扫描进行时，我们才去检查消失的时间
        if self.ble_adapter is not None and self.ble_adapter.scan_state == bleuart.BLEToUartAdapter.ScanState.RUNNING:
            # 遍历表中的每一行，此处我们的child_iid其实就是搜索到的设备的mac地址，
            # 在插入这个表的时候就是传入的设备的mac作为iid的
            for child_iid in self.tree_view_device_list.get_children():
                # 检查一下时间记录映射表中有没有这个设备
                if child_iid in self.device_adv_record_map:
                    last_adv_time = self.device_adv_record_map[child_iid]['time']  # 取出最后一次更新的时间
                    time_distance = time.time() - last_adv_time
                    if time_distance > 5:
                        item_values = self.tree_view_device_list.item(child_iid)["values"]  # 取出旧的值
                        date = datetime.datetime.fromtimestamp(last_adv_time)  # 格式化最后更新的时间
                        # 将格式化的时间拼接上消失的时间
                        item_values[4] = f"{date.strftime('%H:%M:%S')}（消失{int(time_distance)}S）"
                        self.tree_view_device_list.item(child_iid, values=item_values)  # 更新到treeview中的历史行

        # 隔一段时间后再重启这个任务继续检查
        self.root.after(1000, self.task_check_device_adv_time)

    def close_adapter(self):
        """
            关闭适配器且设置引用为空
        @return:
        """
        if self.ble_adapter is not None:
            self.ble_adapter.callback_on_device_found = None  # 解注册回调，不然适配器会一直持有本GUI对象导致无法释放
            self.ble_adapter.close()
            self.ble_adapter = None

    def thread_open_ble_adapter(self, wd: widget.WorkingDialog):
        """
            在子线程中进行BLE转串口设备的打开和检查有效性，避免堵塞UI线程导致卡死
        @return:
        """
        try:
            # 确保旧的设备关掉了，避免没有释放资源导致后续的操作异常
            self.close_adapter()
            self.ble_adapter = bleuart.BLEToUartAdapter(self.port_num_selected)
            if self.ble_adapter.open():
                wd.update_message("正在检测有效性和波特率")
                self.ble_adapter.check_is_ble_to_uart_device()
                # 设置当前的设备选择的波特率到UI上显示，让用户了解当前使用了什么波特率
                self.var_baudrate.set(bleuart.BLEToUartAdapter.BAUDRATE_MAP[self.ble_adapter.baudrate_current_index])

                wd.update_message("正在关闭自动重连")
                self.ble_adapter.set_auto_reconnect_enable(False)
                wd.update_message("正在断开所有蓝牙链接")
                try:
                    self.ble_adapter.disconnect_slave_device()
                except:
                    pass

                # 获取当前的服务特征的UUID，显示在UI上
                wd.update_message("正在获取当前透传服务的UUID信息")
                uuid_s = self.ble_adapter.get_transfer_main_service_uuid()
                self.var_uuid_service_main.set(uuid_s)
                uuid_n = self.ble_adapter.get_transfer_characteristic_n_uuid()
                self.var_uuid_characteristic_notify.set(uuid_n)
                uuid_w = self.ble_adapter.get_transfer_characteristic_w_uuid()
                self.var_uuid_characteristic_write.set(uuid_w)

                # 设备开启成功后，注册扫描回调
                self.ble_adapter.callback_on_device_found = self.on_device_found
                wd.destroy()
                self.set_view_for_adapter_close(False)  # 更新视图为未关闭适配器的状态

                # 来一个弱提醒
                widget.Toast.create(self.root, "适配器已打开")
            else:
                raise Exception("打开串口失败，请检查串口是否被其他串口调试软件占用，或者检查输出日志详细排查！")
        except Exception as e:
            # 如果打开失败的话，那就重置一下选择的串口吧
            self.clear_port_selected()
            self.close_adapter()
            raise e

    def thread_change_baudrate(self, wd: widget.WorkingDialog):
        """
            切换波特率的子线程
        @return:
        """
        baudrate_index = self.ble_adapter.from_baudrate_get_index(self.var_baudrate.get())
        self.ble_adapter.try_change_baudrate(baudrate_index)
        wd.destroy()
        messagebox.showinfo("成功",
                            f"切换到波特率{self.var_baudrate.get()}完成，其他软件使用此串口进行通信请使用此波特率。")

    def thread_reset_adapter(self, wd: widget.WorkingDialog):
        """
            重置适配器的子线程
        @return:
        """
        # 先把自动重连功能禁用掉
        wd.update_message("正在禁用自动重连功能")
        self.ble_adapter.set_auto_reconnect_enable(False)
        wd.update_message("正在清除自动重连列表")
        self.ble_adapter.del_auto_reconnect_list()

        # 然后把可能存在的设备给断掉
        wd.update_message("正在断开可能存在的设备连接")
        try:
            self.ble_adapter.disconnect_slave_device()
        except:
            pass

        # 把服务特征复位
        uuid_s = "FFF0"
        uuid_n = "FFF1"
        uuid_w = "FFF2"
        wd.update_message(f"正在复位服务(s)与特征(c)为："
                          f"\n 主服务 = {uuid_s}, 通知特征 = {uuid_n}, 写特征 = {uuid_w}"
                          f"\n此信息可在新一的手册中获取")
        self.ble_adapter.set_transfer_main_service_uuid(uuid_s)
        self.ble_adapter.set_transfer_characteristic_w_uuid(uuid_w)
        self.ble_adapter.set_transfer_characteristic_n_uuid(uuid_n)
        self.var_uuid_service_main.set(uuid_s)
        self.var_uuid_characteristic_notify.set(uuid_n)
        self.var_uuid_characteristic_write.set(uuid_w)

        # 软重置
        wd.update_message("正在进行软复位适配器")
        self.ble_adapter.soft_reset()
        wd.destroy()
        messagebox.showinfo("重置成功", "适配器已完成默认参数的重置并且软复位成功")

    def thread_wait_scan_stopped(self, wd: widget.WorkingDialog):
        """
            等待结束扫描的子线程
        @return:
        """
        self.ble_adapter.stop_scan()
        wd.destroy()
        widget.Toast.create(self.root, "扫描已停止")
        self.set_view_for_scan_state(False)

    def thread_connect_to_ble_device(self, wd: widget.WorkingDialog, mac: str):
        """
            连接到BLE设备的子线程
        @return:
        """
        try:
            wd.update_message("正在停止扫描")
            self.ble_adapter.stop_scan()
            self.set_view_for_scan_state(False)

            wd.update_message("正在重置适配器以此避免某些未知问题")
            self.ble_adapter.soft_reset()

            device: bleuart.BLEDevice = self.device_adv_record_map[mac]['device']
            device_str = f"{device.name}, {device.mac}"

            wd.update_message("正在删除旧的重连列表")
            self.ble_adapter.del_auto_reconnect_list()

            auto_reconnect_enable = self.var_config_auto_reconnect_on_connect_enable.get()
            if auto_reconnect_enable:
                wd.update_message(f"正在为 {device_str} 设置自动重连")
                self.ble_adapter.set_auto_reconnect_device(device.mac, device.mac_type)

            wd.update_message(f"开始连接到设备 {device_str}")
            self.ble_adapter.connect_slave_device(device.mac, device.mac_type)

            if auto_reconnect_enable:
                wd.update_message("正在开启自动重连功能")
                self.ble_adapter.set_auto_reconnect_enable(True)

            # 连接成功后，关闭适配器，释放串口
            wd.update_message("正在释放串口")
            self.close_adapter()

            # 在UI上标注提示
            values = list(self.tree_view_device_list.item(mac)['values'])
            values[0] = values[0] + "（已连接\n本消息仅供参考，非实时状态）"
            self.tree_view_device_list.item(mac, values=values)

            # 置灰一些操作按钮，恢复到初始状态
            self.set_view_for_adapter_close(True)

            # 把选择的串口号给清除掉
            port_num = self.port_num_selected  # 在清除之前我们先缓存一份，后面在UI中显示可以用的上
            self.clear_port_selected()

            # 弹窗提示，告知一些使用的注意事项，因此必须是强提醒
            wd.destroy()
            messagebox.showinfo("恭喜",
                                f"已完成设备 '{device.name}, {device.mac}' 的连接"
                                f"\n其他上位机请使用波特率 {self.var_baudrate.get()} 连接串口 {port_num}"
                                f"\n为了不抢占串口，本程序已自动关闭蓝牙适配器")
        except Exception as e:
            wd.destroy()
            # 连接失败后，尝试重新开启搜索
            if self.ble_adapter is not None:
                self.ble_adapter.start_scan()
                self.set_view_for_scan_state(True)
            # 最终重新抛出异常，在UI中告知用户问题出现的关键点
            raise e

    def thread_start_scan(self, wd: widget.WorkingDialog):
        """
            启动扫描的子线程
        @return:
        """
        wd.destroy()
        self.ble_adapter.start_scan()
        self.set_view_for_scan_state(True)
        widget.Toast.create(self.root, "扫描已启动")

    def thread_update_service_and_characteristic(self, wd: widget.WorkingDialog):
        """
            执行更新服务特征的UUID
        @return:
        """
        wd.update_message("正在设置主服务的UUID")
        self.ble_adapter.set_transfer_main_service_uuid(self.var_uuid_service_main.get())
        wd.update_message("正在设置通知特征的UUID")
        self.ble_adapter.set_transfer_characteristic_n_uuid(self.var_uuid_characteristic_notify.get())
        wd.update_message("正在设置写特征的UUID")
        self.ble_adapter.set_transfer_characteristic_w_uuid(self.var_uuid_characteristic_write.get())
        wd.destroy()
        messagebox.showinfo("恭喜", "设置透传服务的UUID成功")

    def create_task_sub_thread(self, task_name: str, task_fn, setup_msg: str, args=None):
        """
            创建一个子线程任务
        @param args: 其他的附加参数，需要传入到子线程的进行操作的话
        @param task_name: 任务的名字
        @param task_fn: 任务的实现函数
        @param setup_msg: 初始消息
        @return:
        """
        wd = widget.WorkingDialog(self.root)
        wd.update_message(setup_msg)
        wd.show()

        # 内部闭包封装一个能自动拦截子线程任务发生异常的函数
        def thread_impl():
            try:
                if args is not None:
                    task_fn(wd, args)
                else:
                    task_fn(wd)
            except Exception as e:
                wd.destroy()
                messagebox.showerror(f"任务 '{task_name}' 执行失败", str(e))

        threading.Thread(target=thread_impl).start()

    def on_device_found(self, device: bleuart.BLEDevice):
        """
            设备发现时的回调
        @param device: 设备实例
        @return:
        """
        name_start_filter = self.var_filter_device_name.get()
        if len(name_start_filter) > 0:
            if not device.name.startswith(name_start_filter):
                return  # 发现的设备名称不符合过滤规则，直接忽略

        # 记录设备相关的信息
        self.device_adv_record_map[device.mac] = {
            'time': time.time(),  # 记录当前时间
            'device': device,  # 记录当前设备
        }

        # 格式化当前时间
        current_time = datetime.datetime.now()
        formatted_time = current_time.strftime("%H:%M:%S")

        # 组成信息行
        new_info = [
            device.name,
            device.mac,
            "静态地址" if device.mac_type == 0 else "随机地址",
            f"{device.rssi}dbm",
            formatted_time,  # 最后更新的时间，只需要显示几时几分几秒
        ]

        # 检查是否是存在的行记录，如果是，直接更新，否则插入到结尾
        if self.tree_view_device_list.exists(device.mac):
            self.tree_view_device_list.item(device.mac, values=new_info)
            # logger.info("更新列表中已存在的设备信息完成")
        else:
            self.tree_view_device_list.insert('', tk.END, values=new_info, iid=device.mac)
            logger.info(f"设备 {device} 加入到列表完成")

    def on_baudrate_select(self, _):
        baudrate = self.var_baudrate.get()
        if self.ble_adapter is not None and self.ble_adapter.baudrate_current_index != -1:
            if baudrate != self.ble_adapter.BAUDRATE_MAP[self.ble_adapter.baudrate_current_index]:
                logger.info(f"需要切换到波特率：{baudrate}")
                self.create_task_sub_thread("切换波特率", self.thread_change_baudrate, "正在切换波特率")
        return

    def on_port_select(self, _):
        index_selected = self.port_list.current()
        new_port_selected = self.port_obj_list[index_selected].device

        # 检查如果这个适配器虽然是当前已经打开的适配器，但是实际上已经关闭的话，那就可以再次打开
        if self.is_adapter_closed():
            self.port_num_selected = None

        if self.port_num_selected != new_port_selected:
            self.port_num_selected = new_port_selected
            logger.info(f"选择了一个串口：index = {index_selected}，port = {self.port_num_selected}")
            self.clear_device_list()
            self.create_task_sub_thread("蓝牙适配器初始化", self.thread_open_ble_adapter, "正在打开串口")
        return

    def on_soft_reset_adapter_click(self):
        self.create_task_sub_thread("软重启适配器", self.thread_reset_adapter, "正在软重启")

    def on_start_ble_device_scan_click(self):
        if self.is_adapter_closed():
            self.set_view_for_scan_state(False)
            return
        if self.ble_adapter.scan_state != bleuart.BLEToUartAdapter.ScanState.RUNNING:
            self.create_task_sub_thread("启动BLE扫描", self.thread_start_scan, "正在启动扫描")
        else:
            self.create_task_sub_thread("停止BLE扫描", self.thread_wait_scan_stopped, "正在停止扫描")

    def on_update_transfer_service_uuid(self):
        self.create_task_sub_thread("更新服务特征", self.thread_update_service_and_characteristic, "正在更新")

    def on_ble_device_select(self, _):
        # 跳过头部的选择
        selections = self.tree_view_device_list.selection()
        if len(selections) == 0:
            return

        # 如果适配器已经关闭则弹窗提示
        if self.is_adapter_closed():
            messagebox.showerror("适配器已关闭", "请重新选择串口号连接到BLE转串口适配器")
            return

        device_mac = selections[0]
        connect = messagebox.askyesno(
            "确认连接？", f"请确认是否连接到MAC地址为 {device_mac} 的蓝牙设备？")
        if connect:  # 确认需要连接到此设备
            logger.info(f"选择连接到设备：{device_mac}")
            self.create_task_sub_thread(f"连接到BLE设备", self.thread_connect_to_ble_device, "正在连接", device_mac)
        return

    def on_clear_device_list_click(self):
        self.clear_device_list()

    def show_ports(self):
        """
            更新需要显示的串口下拉选择的列表
        @return:
        """
        self.port_obj_list = serial.tools.list_ports.comports()
        logger.info(f"搜索到的串口总数：{len(self.port_obj_list)}")
        for port, desc, hwid in self.port_obj_list:
            logger.info("串口信息：{}: {} [{}]".format(port, desc, hwid))
        self.port_list['values'] = [device.description for device in self.port_obj_list]

    def on_window_close_confirm(self) -> bool:
        """
            在确认关闭窗口的时候回调此函数
        @return: 返回False表示不关闭，返回True表示关闭
        """
        self.close_adapter()
        return True


if __name__ == '__main__':
    root = tk.Tk()

    # 无边框窗体
    bW = widget.BorderlessWindow(root)
    bW.border_bg = DEFAULT_BACKGROUND

    # 绘制顶上标题栏
    wTBS = widget.TitleBarSimple(root)
    wTBS['bg'] = DEFAULT_BACKGROUND
    wTBS.bind("<B1-Motion>", bW.on_pywin32_window_drag_motion)
    wTBS.pack(fill=tk.X, side=tk.TOP)

    style = ttk.Style()
    style.theme_use('alt')

    root['background'] = DEFAULT_BACKGROUND

    widget.set_win_center_by_screen(root, 1080, 480)

    appGui = App(root)
    # 注册一个关闭窗口的处理回调
    wTBS.btn_destroy.on_confirm_close = appGui.on_window_close_confirm

    tk.mainloop()
