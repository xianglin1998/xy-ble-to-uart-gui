import os
import platform
import sys
import tkinter as tk
import typing
from ctypes.wintypes import HWND, UINT, RECT
from ctypes import c_int, Structure, POINTER
from tkinter import ttk

import win32con
import win32gui
from win32api import SetWindowLong as Win32ApiSetWindowLong
from win32api import RGB as WIN32API_RGB
from PIL import ImageColor, Image, ImageTk

EVENT_NAME_CLICK = "<Button-1>"

yesno_bool = {
    True: 'yes',
    False: 'no',
}


def get_img_for_tk(img_file: str, size: typing.Tuple[int, int]):
    image = Image.open(img_file)
    image = image.resize(size, Image.LANCZOS)
    return ImageTk.PhotoImage(image)


def make_img_alpha(size: typing.Tuple[int, int], rgba):
    """
        使用指定的RGBA生成一个图片
    @param size: 大小
    @param rgba: RGBA，可以是字符串或者是元组
    @return:
    """
    image = Image.new('RGBA', size, rgba)
    return ImageTk.PhotoImage(image)


def set_win_center_by_screen(root, width=200, height=200):
    """
    设置窗口大小，并居中显示
    :param root:主窗体实例
    :param width:窗口宽度，非必填，默认200
    :param height:窗口高度，非必填，默认200
    :return:
    """
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    x = (ws / 2) - (width / 2)
    y = (hs / 2) - (height / 2)
    # 设置窗口初始大小和位置
    root.geometry('%dx%d+%d+%d' % (width, height, x, y))


def set_win_center_by_parent(win_child, win_parent):
    """
        设置子窗口以父窗口居中
    @param win_child: 子窗口
    @param win_parent: 父窗口
    @return:
    """
    x = win_parent.winfo_rootx() + win_parent.winfo_width() / 2
    x = x - win_child.winfo_width() / 2
    y = win_parent.winfo_rooty() + win_parent.winfo_height() / 2
    y = y - win_child.winfo_height() / 2
    win_child.geometry("+%d+%d" % (x, y))


def disable_combobox_mouse_wheel(combobox: ttk.Combobox):
    """
        禁止combobox的鼠标滑动切换值的操作
    @param combobox: 控件实例
    @return:
    """
    # Windows & OSX
    combobox.unbind_class("TCombobox", "<MouseWheel>")
    # Linux and other *nix systems:
    combobox.unbind_class("TCombobox", "<ButtonPress-4>")
    combobox.unbind_class("TCombobox", "<ButtonPress-5>")


def get_resource_path(relative_path: str):
    """
        获取资源的路径，此函数可以解决pyinstaller打包后程序的相对路径和解压路径不一致导致的资源无法找到的问题
    @param relative_path: 资源在工程中的相对路径
    @return:
    """
    attr_name = '_MEIPASS'  # pyintsaller运行时加入的一个环境变量 https://blog.csdn.net/Yibans/article/details/111305438
    if hasattr(sys, attr_name):
        pyinstaller_unpack_dir = getattr(sys, attr_name)
        return os.path.join(pyinstaller_unpack_dir, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


IMG_PATH_NAV_ICON_DESTROY = get_resource_path("widget_img/nav-icon-destroy.png")
IMG_PATH_NAV_ICON_MAXIMIZE = get_resource_path("widget_img/nav-icon-maximize.png")
IMG_PATH_NAV_ICON_MINIMIZE = get_resource_path("widget_img/nav-icon-minimize.png")
IMG_PATH_NAV_ICON_RESTORE_WIN = get_resource_path("widget_img/nav-icon-restore-win.png")
IMG_PATH_NAV_ICON_TOPPING_WHITE = get_resource_path("widget_img/nav-icon-topping_white.png")
IMG_PATH_NAV_ICON_TOPPING_BLUE = get_resource_path("widget_img/nav-icon-topping_blue.png")


def is_event_in_widget(event: tk.Event, widget: tk.Misc):
    """
        判断事件是否是发生在指定的控件内
    @param event: 事件对象
    @param widget: 控件对象
    @return:
    """
    if (event.x < 0 or event.x > widget.winfo_width() or
            event.y < 0 or event.y > widget.winfo_height()):
        return False
    return True


class PWINDOWPOS(Structure):
    _fields_ = [
        ('hWnd', HWND),
        ('hwndInsertAfter', HWND),
        ('x', c_int),
        ('y', c_int),
        ('cx', c_int),
        ('cy', c_int),
        ('flags', UINT)
    ]


class NCCALCSIZE_PARAMS(Structure):
    _fields_ = [
        ('rgrc', RECT * 3),
        ('lppos', POINTER(PWINDOWPOS))
    ]


class BorderlessWindow:
    # 任务栏右键时的事件ID，属于隐藏事件，不在WINDOWS的公开API中存在
    WM_TASKBARRCLICK = 0x0313
    # 一个虚拟的边框，这是在边缘检测时可以用到的
    BORDER_WIDTH = 5

    def __init__(self, window: tk.Tk | tk.Toplevel):
        self.window = window

        # 存放最后点击的位置
        self.x_for_last_click = 0
        self.y_for_last_click = 0

        # 绑定移动事件 TODO 移动事件应该由状态栏组件自己绑定？
        # self.window.bind("<B1-Motion>", self.on_pywin32_window_drag_motion)
        self.window.bind('<Button-1>', self.on_click_window_save_lastpos)

        # 默认使用的边框颜色 TODO 以后有时间再研究一下怎么做到边框透明
        self._border_bg = "white"

        # 等待窗口创建完成
        if not win32gui.IsWindowVisible(self.window.winfo_id()):
            self.window.wait_visibility(self.window)

        # print(f"创建窗口后的ID：{win32gui.GetParent(self.winfo_id())}")
        self.hwnd = win32gui.GetParent(self.window.winfo_id())
        # Set the WndProc to our function
        self.old_wnd_proc = win32gui.SetWindowLong(self.hwnd, win32con.GWL_WNDPROC, self.base_window_proc)
        # Make a dictionary of message names to be used for printing below
        self.hwnd_proc_msg_dict = {}
        for name in dir(win32con):
            if name.startswith("WM_"):
                value = getattr(win32con, name)
                self.hwnd_proc_msg_dict[value] = name

        self.hide_title_bar_for_win32()

    @property
    def border_bg(self):
        return self._border_bg

    @border_bg.setter
    def border_bg(self, val):
        self._border_bg = val
        win32gui.UpdateWindow(self.hwnd)

    def hide_title_bar_for_win32(self):
        #  get current window style
        style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_STYLE)
        #  remove titlebar elements
        style &= ~win32con.WS_TILEDWINDOW
        #  apply new style
        win32gui.SetWindowLong(self.hwnd, win32con.GWL_STYLE, style)

        # 重新布局窗口
        win32gui.SetWindowPos(
            self.hwnd,
            win32con.NULL, 0, 0, 0, 0,
            win32con.SWP_NOSIZE | win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_DRAWFRAME
        )
        win32gui.UpdateWindow(self.hwnd)

    def on_click_window_save_lastpos(self, event):
        self.x_for_last_click = event.x_root
        self.y_for_last_click = event.y_root

    def on_pywin32_window_drag_motion(self, event):
        # win32gui.ReleaseCapture()
        # win32gui.SendMessage(self.hwnd, win32con.WM_SYSCOMMAND, win32con.SC_MOVE + win32con.HTCAPTION, 0)
        dx = event.x_root - self.x_for_last_click
        dy = event.y_root - self.y_for_last_click
        win32gui.SetWindowPos(self.hwnd, win32con.HWND_TOP, win32gui.GetWindowRect(self.hwnd)[0] + dx,
                              win32gui.GetWindowRect(self.hwnd)[1] + dy, 0, 0,
                              win32con.SWP_NOSIZE | win32con.SWP_NOZORDER)
        self.x_for_last_click = event.x_root
        self.y_for_last_click = event.y_root

    def nchitest_detect(self, x, y):
        """
            识别非客户区的手势
        @param x: 相对于整个窗体的X，也就是包括非客户区的区域
        @param y: 相对于整个窗体的Y，也就是包括非客户区的区域
        @return: 识别到的手势
        """
        # 获取当前屏幕的宽和高（整个窗体，包含客户区和非客户区）
        rect = win32gui.GetWindowRect(self.hwnd)
        w = rect[2] - rect[0]
        h = rect[3] - rect[1]
        # 判断位置
        lx = x < self.BORDER_WIDTH
        rx = x > w - self.BORDER_WIDTH
        ty = y < self.BORDER_WIDTH
        by = y > h - self.BORDER_WIDTH
        if lx and ty:
            return win32con.HTTOPLEFT
        elif rx and by:
            return win32con.HTBOTTOMRIGHT
        elif rx and ty:
            return win32con.HTTOPRIGHT
        elif lx and by:
            return win32con.HTBOTTOMLEFT
        elif ty:
            return win32con.HTTOP
        elif by:
            return win32con.HTBOTTOM
        elif lx:
            return win32con.HTLEFT
        elif rx:
            return win32con.HTRIGHT
        return 0

    @staticmethod
    def create_win32_rgb_by_string(string_color):
        rgb_arr = ImageColor.getrgb(string_color)
        rgb_win = WIN32API_RGB(rgb_arr[0], rgb_arr[1], rgb_arr[2])
        return rgb_win

    def base_window_proc(self, h_wnd, msg, w_param, l_param):
        # Display what we've got.
        # print(self.hwnd_proc_msg_dict.get(msg), msg, w_param, l_param)

        if msg == win32con.WM_CONTEXTMENU:
            print('标题栏右键')
            return 0

        if msg == BorderlessWindow.WM_TASKBARRCLICK:
            print('任务栏小窗右键事件')
            return 0

        if msg == win32con.WM_NCACTIVATE:
            # Paint the non-client area now, otherwise Windows will paint its own
            win32gui.RedrawWindow(self.hwnd, None, None, win32con.RDW_UPDATENOW)
            return 1  # 这个事件里面一定要返回1，不然的话子窗口（tk.messagebox之类的）将会无法缩放和隐藏

        if msg == win32con.WM_ERASEBKGND:
            # 如果应用程序处理消息并擦除背景，则应用程序应返回非零值以响应 WM_ERASEBKGND ;
            # 这表示不需要进一步擦除。 如果应用程序返回零，窗口将保持标记为要擦除。
            return 1

        if msg == win32con.WM_NCPAINT:
            rect = win32gui.GetWindowRect(self.hwnd)
            width_window = rect[2] - rect[0]
            height_window = rect[3] - rect[1]

            hdc = win32gui.GetWindowDC(self.hwnd)

            csb = win32gui.CreateSolidBrush(self.create_win32_rgb_by_string(self._border_bg))

            # 左边的边框
            win32gui.FillRect(hdc, (
                0, 0, self.BORDER_WIDTH, height_window
            ), csb)
            # 上边的边框
            win32gui.FillRect(hdc, (
                self.BORDER_WIDTH, 0, width_window - self.BORDER_WIDTH, self.BORDER_WIDTH
            ), csb)
            # 右边的边框
            win32gui.FillRect(hdc, (
                width_window - self.BORDER_WIDTH, 0, width_window, height_window
            ), csb)
            # 下边的边框
            win32gui.FillRect(hdc, (
                self.BORDER_WIDTH, height_window - self.BORDER_WIDTH, width_window - self.BORDER_WIDTH, height_window
            ), csb)

            win32gui.ReleaseDC(self.hwnd, hdc)
            win32gui.DeleteObject(csb)

            # print("非客户区绘制完成")
            return 0

        if msg == win32con.WM_NCCALCSIZE:
            if w_param:
                # print("拦截非客户区大小计算事件")
                # 修改非客户区大小，添加一些距离的边框，以达到稳定的resize鼠标区域识别
                np = NCCALCSIZE_PARAMS.from_address(l_param)
                np.rgrc[0].left += self.BORDER_WIDTH
                np.rgrc[0].top += self.BORDER_WIDTH
                np.rgrc[0].right -= self.BORDER_WIDTH
                np.rgrc[0].bottom -= self.BORDER_WIDTH

            return win32con.WVR_VALIDRECTS

        if msg == win32con.WM_NCHITTEST:
            # 如果当前窗口是最大化的状态，则不要进行任何的拖动调整大小的事件的处理
            if self.detect_window_size() == win32con.SW_SHOWMAXIMIZED:
                return 0

            # 替代掉 GET_X_LPARAM 和 GET_Y_LPARAM
            rect = win32gui.GetWindowRect(self.hwnd)
            lp_bytes = int.to_bytes(l_param, 4, signed=True)
            # 转换当前的XY坐标为相对于整个窗体的坐标（包含非客户区）
            x = int.from_bytes(lp_bytes[2:4], signed=True) - rect[0]
            y = int.from_bytes(lp_bytes[0:2], signed=True) - rect[1]
            return self.nchitest_detect(x, y)

        # Restore the old WndProc. Notice the use of wxin32api instead of win32gui here.
        # This is to avoid an error due to not passing a callable object.
        if msg == win32con.WM_DESTROY:
            Win32ApiSetWindowLong(self.hwnd, win32con.GWL_WNDPROC, self.old_wnd_proc)

        # Pass all messages (in this case, yours may be different) on to the original WndProc
        return win32gui.CallWindowProc(self.old_wnd_proc, h_wnd, msg, w_param, l_param)

    def detect_window_size(self):
        tup = win32gui.GetWindowPlacement(self.hwnd)
        if tup[1] == win32con.SW_SHOWMAXIMIZED:
            # print("maximized")
            return win32con.SW_SHOWMAXIMIZED
        elif tup[1] == win32con.SW_SHOWMINIMIZED:
            # print("minimized")
            return win32con.SW_SHOWMINIMIZED
        elif tup[1] == win32con.SW_SHOWNORMAL:
            # print("normal")
            return win32con.SW_SHOWNORMAL


def create_unique_tag_name(name: str, misc: tk.Misc):
    uid = f"{misc.winfo_id()}_{name}"
    return uid


class ImageButton(tk.Canvas):
    """
        与窗口有关的工具按钮，比如最大化，最小化，置顶，关闭
    """

    def __init__(self, master, image_path: str):
        super().__init__(master)

        # 生成一个每个实例唯一的TAG
        self.TAG_NAME_MASK = create_unique_tag_name("_img_btn_bg_mask_", self)
        self.TAG_NAME_BTN = create_unique_tag_name("_img_btn_pic", self)

        self.hide_border()
        self.bind("<Configure>", self.on_configure)
        self.bind("<Enter>", self.on_mouse_enter)
        self.bind("<Leave>", self.on_mouse_leave)
        self.img_topmost = get_img_for_tk(image_path, (16, 16))
        self.img_canvas_mask = None
        self.img_btn = self.create_image(0, 0, image=self.img_topmost, tags=self.TAG_NAME_BTN)

        self.color_mouse_enter_mask = (255, 255, 255, 20)

    def on_mouse_enter(self, _):
        # print("鼠标悬停")
        if self.img_canvas_mask is not None:
            self.delete(self.TAG_NAME_MASK)
            self.create_image(0, 0, image=self.img_canvas_mask, anchor=tk.NW, tags=self.TAG_NAME_MASK)
            # 把图片元素移动到顶层，让按钮蒙版处于最底下，既能做出鼠标悬停时的按钮变色效果，又能不影响之前显示的图片
            self.tag_raise(self.TAG_NAME_BTN)

    def on_mouse_leave(self, _):
        # print("鼠标移走")
        self.delete(self.TAG_NAME_MASK)

    def on_configure(self, _):
        windows_w, windows_h = self.winfo_width(), self.winfo_height()
        # 居中摆放这个图片
        img_w, img_h = self.img_topmost.width(), self.img_topmost.height()
        self.moveto(self.img_btn, windows_w / 2 - img_w / 2, windows_h / 2 - img_h / 2)
        # 绘制一个新的遮罩图
        self.img_canvas_mask = make_img_alpha((windows_w, windows_h), self.color_mouse_enter_mask)

    def hide_border(self):
        """
            隐藏空间自带的边框
        @return:
        """
        self['bd'] = 0
        self['highlightthickness'] = 0
        self['relief'] = tk.RIDGE


class CloseWindowButton(ImageButton):
    """
        关闭窗口专用的封装按钮
    """

    def __init__(self, master, window):
        super().__init__(master, IMG_PATH_NAV_ICON_DESTROY)
        self.window = window
        self.color_mouse_enter_mask = "red"
        self.on_confirm_close: typing.Callable[[], bool] | None = None
        self.bind(EVENT_NAME_CLICK, self._on_close_window)  # 窗口关闭事件

    def _on_close_window(self, _):
        """
            在关闭窗口前执行
        @return:
        """
        if self.on_confirm_close is not None:
            if not self.on_confirm_close():  # 如果不确定需要关闭的话，那就跳过此次事件
                return
        self.window.destroy()


class MaximizeWindowButton(ImageButton):
    """
        窗口最大化专用的封装按钮
    """

    def __init__(self, master, window):
        super().__init__(master, IMG_PATH_NAV_ICON_MAXIMIZE)
        self.window = window
        self.img_restore = get_img_for_tk(IMG_PATH_NAV_ICON_RESTORE_WIN, (16, 16))
        self.bind(EVENT_NAME_CLICK, self.on_maximize)  # 窗口最大化事件

    def on_maximize(self, _):
        zoomed = 'zoomed'
        if self.window.state() == zoomed:
            self.window.state(tk.NORMAL)
            self.itemconfig(self.img_btn, image=self.img_topmost)
        else:
            self.window.state(zoomed)
            self.itemconfig(self.img_btn, image=self.img_restore)


class TopmostWindowButton(ImageButton):
    """
        置顶窗口专用按钮
    """

    def __init__(self, master, window):
        super().__init__(master, IMG_PATH_NAV_ICON_TOPPING_WHITE)
        self.window = window
        self.img_no_topmost = get_img_for_tk(IMG_PATH_NAV_ICON_TOPPING_BLUE, (16, 16))
        self.bind(EVENT_NAME_CLICK, self.on_topping)

    def on_topping(self, _):
        attr_key = "-topmost"
        is_topmost = self.window.attributes(attr_key)
        if is_topmost:
            self.window.attributes(attr_key, False)
            self.itemconfig(self.img_btn, image=self.img_topmost)
        else:
            self.window.attributes(attr_key, True)
            self.itemconfig(self.img_btn, image=self.img_no_topmost)


class TitleBarSimple(tk.Frame):
    """
        简单的标题栏
    """

    def __init__(self, master: tk.Tk | tk.Toplevel):
        super().__init__(master)

        self['width'] = master.winfo_width()
        self['height'] = 30

        # 工具按钮集合
        self.tbs = []
        # 关闭窗口的按钮
        self.btn_destroy = CloseWindowButton(self, self.master)
        self.draw_tool_btn(self.btn_destroy)
        # 窗口最大化按钮
        self.btn_maximize = MaximizeWindowButton(self, self.master)
        self.draw_tool_btn(self.btn_maximize)
        # 窗口最小化
        self.btn_minimize = ImageButton(self, IMG_PATH_NAV_ICON_MINIMIZE)
        self.draw_tool_btn(self.btn_minimize)
        # 窗口置顶
        self.btn_topping = TopmostWindowButton(self, self.master)
        self.draw_tool_btn(self.btn_topping)

        # 注册相应的事件
        self.btn_minimize.bind(EVENT_NAME_CLICK, lambda e: master.iconify())

    def draw_tool_btn(self, btn: ImageButton):
        """
            绘制窗口工具
        @param btn: 按钮的实现
        @return:
        """
        btn['width'] = 30
        btn['height'] = 16
        btn.pack(side=tk.RIGHT, expand=False, fill=tk.NONE, ipadx=4, ipady=4)
        self.tbs.append(btn)

    def __setitem__(self, key, value):
        if key == 'bg' or key == 'background':
            # 在遇到给当前标题栏设置背景的时候，顺便也给窗口工具也设置一下
            for wtb in self.tbs:
                if wtb is not None:
                    wtb['bg'] = value
        self.configure({key: value})


class WorkingDialog(tk.Toplevel):
    def __init__(self, master):
        tk.Toplevel.__init__(self, master)
        self.geometry("400x150")
        self.overrideredirect(True)

        frame_root = tk.Frame(self)
        frame_root.pack(padx=5, pady=5)

        self.progress = None
        self.progress = ttk.Progressbar(frame_root, mode='indeterminate')
        self.progress.pack(pady=20)
        self.progress.start()

        message_label = tk.Label(frame_root, text="初始消息")
        message_label.pack(pady=10)
        self.message_label = message_label  # 用于后续更新文本消息

        self.bind('<Button-1>', self._click_win)
        self.bind('<B1-Motion>', self._drag_win)

        self.withdraw()  # 默认隐藏对话框

    def _drag_win(self, event):
        if is_event_in_widget(event, self):
            x = self.winfo_pointerx() - self._offset_x
            y = self.winfo_pointery() - self._offset_y
            self.geometry('+{x}+{y}'.format(x=x, y=y))

    def _click_win(self, event):
        if is_event_in_widget(event, self):
            self._offset_x = event.x
            self._offset_y = event.y
        else:
            self.bell()

    def show(self):
        self.deiconify()  # 显示对话框
        self.grab_set()  # 抢占所有的事件，使得对话框在最前面
        self.master.update_idletasks()  # 更新UI对象
        set_win_center_by_parent(self, self.master)  # 使其在父窗口之内居中显示

    def cancel(self):
        self.withdraw()
        self.grab_release()

    def update_message(self, new_message):
        self.message_label.config(text=new_message)  # 更新文本消息控件的文本内容


def round_polygon_in_canvas(canvas, x, y, sharpness, **kwargs):
    # The sharpness here is just how close the sub-points
    # are going to be to the vertex. The more the sharpness,
    # the more the sub-points will be closer to the vertex.
    # (This is not normalized)
    if sharpness < 2:
        sharpness = 2
    ratio_multiplier = sharpness - 1
    ratio_dividend = sharpness
    # Array to store the points
    points = []
    # Iterate over the x points
    for i in range(len(x)):
        # Set vertex
        points.append(x[i])
        points.append(y[i])
        # If it's not the last point
        if i != (len(x) - 1):
            # Insert submultiples points. The more the sharpness, the more these points will be
            # closer to the vertex.
            points.append((ratio_multiplier * x[i] + x[i + 1]) / ratio_dividend)
            points.append((ratio_multiplier * y[i] + y[i + 1]) / ratio_dividend)
            points.append((ratio_multiplier * x[i + 1] + x[i]) / ratio_dividend)
            points.append((ratio_multiplier * y[i + 1] + y[i]) / ratio_dividend)
        else:
            # Insert submultiples points.
            points.append((ratio_multiplier * x[i] + x[0]) / ratio_dividend)
            points.append((ratio_multiplier * y[i] + y[0]) / ratio_dividend)
            points.append((ratio_multiplier * x[0] + x[i]) / ratio_dividend)
            points.append((ratio_multiplier * y[0] + y[i]) / ratio_dividend)
            # Close the polygon
            points.append(x[0])
            points.append(y[0])
    return canvas.create_polygon(points, **kwargs, smooth=tk.TRUE)


class Toast(tk.Toplevel):
    def __init__(self, master, message, duration_ms=800, padding=(10, 10, 10, 10),
                 bg_outline="#DCDCDC", bg_fill="white", msg_font=("微软雅黑", 10), msg_fill="#696969"):
        super().__init__(master)

        self.overrideredirect(True)  # 把窗口设置为无标题栏无边框，方便接下来进行自定义
        self.wm_attributes("-toolwindow", True)  # 设置为工具窗口，可以将非必要的窗口按钮隐藏，以及从任务栏移除ICON
        self.attributes('-topmost', tk.FALSE)  # 没必要置顶，这是个弱提示工具，置顶遮住了其他的内容，会导致客户没办法忽略此内容
        self.attributes('-transparentcolor', 'grey15')  # 配置透明色
        self.config(bg='grey15')  # 把当前窗口的颜色设置为透明色，这样子窗口就变成了局部透明的了

        self.canvas = tk.Canvas(self, bg='grey15', highlightthickness=0)
        self.canvas.pack(expand=True, fill=tk.BOTH)
        self.canvas.update()

        self.duration = duration_ms
        self._fade_step = 1
        self.padding = padding
        self.msg = message
        self.bg_outline = bg_outline
        self.bg_fill = bg_fill
        self.msg_fill = msg_fill
        self.msg_font = msg_font

        self.show()

    def draw_msg(self):
        """
            绘制消息框体
        @return:
        """
        # 绘制文字，在画布的中间
        txt_msg = self.canvas.create_text(
            self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2,
            text=self.msg, font=self.msg_font, fill=self.msg_fill)
        txt_bounds = self.canvas.bbox(txt_msg)  # 获取绘制的文字的矩形边界 (x1, y1, x2, y2)
        width_msg = txt_bounds[2] - txt_bounds[0]
        height_msg = txt_bounds[3] - txt_bounds[1]

        # 绘制一个带弧边的背景
        pad_l, pad_t, pad_r, pad_b = self.padding
        polygon_bg = round_polygon_in_canvas(
            self.canvas,
            # 左上 右上  右下  左下
            # [100, 300, 300, 100],  # X
            # [100, 100, 150, 150],  # Y
            #         左上                      右上                    右下                    左下
            [txt_bounds[0] - pad_l, txt_bounds[2] + pad_r, txt_bounds[2] + pad_r, txt_bounds[0] - pad_l],  # X
            [txt_bounds[1] - pad_t, txt_bounds[1] - pad_t, txt_bounds[3] + pad_b, txt_bounds[3] + pad_b],  # y
            16, width=2,
            outline=self.bg_outline, fill=self.bg_fill
        )
        self.canvas.tag_lower(polygon_bg)  # 背景就是背景，显示的那么顶层干嘛？当显眼包啊，把其他的内容都盖住了，给我下去吧你
        bg_bounds = self.canvas.bbox(polygon_bg)
        width_bg = bg_bounds[2] - bg_bounds[0]
        height_bg = bg_bounds[3] - bg_bounds[1]

        # 把画布设置为刚好适合承载的Toast内容的大小
        self.canvas.config(width=width_bg, height=height_bg)
        self.canvas.update()
        # 让背景居中
        self.canvas.moveto(polygon_bg, 0, 0)
        # 让文本居中
        self.canvas.moveto(
            txt_msg,
            width_bg / 2 - width_msg / 2,
            height_bg / 2 - height_msg / 2
        )
        # 把窗体设置为刚好适合承载的Toast内容的大小
        self.geometry(f"{width_bg}x{height_bg}")

    def show(self):
        # 绘制消息
        self.draw_msg()
        # 使其在父窗口之内居中显示
        set_win_center_by_parent(self, self.master)
        # 在持续N秒后，启动渐出动画，慢慢的消失
        self.after(self.duration, self.fade)

    def fade(self):
        """
            在给定的时间内渐出
        @return:
        """
        if self._fade_step <= 0:
            # 已经彻底透明隐藏，我们可以销毁此Toast窗体了
            self.destroy()
            return
        self._fade_step = round(self._fade_step - 0.1, 1)
        self.attributes("-alpha", self._fade_step)  # 透明度，值在0-1之间
        self.after(20, self.fade)  # 一段时间后继续减少透明度

    @staticmethod
    def create(master: tk.Misc, message, **kwargs):
        """
            创建一个Toast的封装函数，线程安全的创建函数
        @param message: 显示的消息
        @param master: 上一级窗口
        @param kwargs: 其他的参数，详情请看 Toast 的构造函数
        @return:
        """
        master.after_idle(lambda: Toast(master, message, **kwargs))


class TkDnD:
    def __init__(self, tkroot):
        self._tkroot = tkroot
        tkroot.tk.eval('package require tkdnd')
        tkroot.dnd = self

    def bind_source(self, widget, target_type=None, command=None, arguments=None, priority=None):
        command = self._generate_callback(command, arguments)
        tk_cmd = self._generate_tk_command('bindsource', widget, target_type, command, priority)
        res = self._tkroot.tk.eval(tk_cmd)
        if target_type is None:
            res = res.split()
        return res

    def bind_target(self, widget, target_type=None, sequence=None, command=None, arguments=None, priority=None):
        command = self._generate_callback(command, arguments)
        tk_cmd = self._generate_tk_command('bindtarget', widget, target_type, sequence, command, priority)
        res = self._tkroot.tk.eval(tk_cmd)
        if target_type is None:
            res = res.split()
        return res

    def clear_source(self, widget):
        self._tkroot.tk.call('dnd', 'clearsource', widget)

    def clear_target(self, widget):
        self._tkroot.tk.call('dnd', 'cleartarget', widget)

    def drag(self, widget, actions=None, descriptions=None, cursor_window=None, command=None, arguments=None):
        command = self._generate_callback(command, arguments)
        if actions:
            if actions[1:]:
                actions = '-actions {%s}' % ' '.join(actions)
            else:
                actions = '-actions %s' % actions[0]
        if descriptions:
            descriptions = ['{%s}' % i for i in descriptions]
            descriptions = '{%s}' % ' '.join(descriptions)
        if cursor_window:
            cursor_window = '-cursorwindow %s' % cursor_window
        tk_cmd = self._generate_tk_command('drag', widget, actions, descriptions, cursor_window, command)
        self._tkroot.tk.eval(tk_cmd)

    def _generate_callback(self, command, arguments):
        cmd = None
        if command:
            cmd = self._tkroot.register(command)
            if arguments:
                cmd = '{%s %s}' % (cmd, ' '.join(arguments))
        return cmd

    @staticmethod
    def _generate_tk_command(base, widget, *opts):
        tk_cmd = 'dnd %s %s' % (base, widget)
        for i in opts:
            if i is not None:
                tk_cmd += ' %s' % i
        return tk_cmd


class ScrollFrame(tk.Frame):
    def __init__(self, master=None, cnf=None, **kw):
        if cnf is None:
            cnf = {}
        super().__init__(master, cnf, **kw)  # create a frame (self)

        self.canvas = tk.Canvas(self, bd=0, highlightthickness=0, relief='ridge', **kw)  # place canvas on self
        self.viewPort = tk.Frame(self.canvas, **kw)  # place a frame on the canvas, this frame will hold the child widgets
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)  # place a scrollbar on self
        self.canvas.configure(yscrollcommand=self.vsb.set)  # attach scrollbar action to scroll of canvas

        self.vsb.pack(side="right", fill="y")  # pack scrollbar to right of self
        self.canvas.pack(side="left", fill="both", expand=True)  # pack canvas to left of self and expand to fil
        self.canvas_window = self.canvas.create_window((4, 4), window=self.viewPort, anchor="nw",
                                                       # add view port frame to canvas
                                                       tags="self.viewPort")

        self.viewPort.bind("<Configure>",
                           self.onFrameConfigure)  # bind an event whenever the size of the viewPort frame changes.
        self.canvas.bind("<Configure>",
                         self.onCanvasConfigure)  # bind an event whenever the size of the canvas frame changes.

        self.viewPort.bind('<Enter>', self.onEnter)  # bind wheel events when the cursor enters the control
        self.viewPort.bind('<Leave>', self.onLeave)  # unbind wheel events when the cursorl leaves the control

        # perform an initial stretch on render, otherwise the scroll region has a tiny border until the first resize
        self.onFrameConfigure(None)

    def onFrameConfigure(self, event):
        '''Reset the scroll region to encompass the inner frame'''
        # whenever the size of the frame changes, alter the scroll region respectively.
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def onCanvasConfigure(self, event):
        '''Reset the canvas window to encompass inner frame when required'''
        self.canvas.itemconfig(self.canvas_window,
                               # height=self.canvas.winfo_height(),
                               width=event.width)  # whenever the size of the canvas changes alter the window region respectively.

    def onMouseWheel(self, event):  # cross platform scroll wheel event
        canvas_height = self.canvas.winfo_height()
        rows_height = self.canvas.bbox("all")[3]

        if rows_height > canvas_height:  # only scroll if the rows overflow the frame
            if platform.system() == 'Windows':
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif platform.system() == 'Darwin':
                self.canvas.yview_scroll(int(-1 * event.delta), "units")
            else:
                if event.num == 4:
                    self.canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self.canvas.yview_scroll(1, "units")

    def onEnter(self, event):  # bind wheel events when the cursor enters the control
        if platform.system() == 'Linux':
            self.canvas.bind_all("<Button-4>", self.onMouseWheel)
            self.canvas.bind_all("<Button-5>", self.onMouseWheel)
        else:
            self.canvas.bind_all("<MouseWheel>", self.onMouseWheel)

    def onLeave(self, event):  # unbind wheel events when the cursorl leaves the control
        if platform.system() == 'Linux':
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")
        else:
            self.canvas.unbind_all("<MouseWheel>")


def test():
    """
        测试函数
    @return:
    """
    root = tk.Tk()
    root.config(bg="grey")
    set_win_center_by_screen(root, width=500, height=400)

    def show_toast():
        # Toast(root, "这是一串Toast")
        WorkingDialog(root).show()
        Toast.create(root, "这是一串Toast")

    btn = tk.Button(root, text="显示一串Toast", command=show_toast, bg="#3c3c3c", fg="white")
    btn.pack(side=tk.BOTTOM, padx=10, pady=10, ipadx=10, ipady=5)

    root.mainloop()


if __name__ == '__main__':
    test()
