# modem/manager.py
"""多模块管理器 - 管理所有4G模块的生命周期"""
import os
import re
import glob
import uuid
import time
import serial
import threading
import logging
from datetime import datetime, timezone

from .base import BaseModemDriver
from .quectel import QuectelDriver
from .simcom import SimcomDriver
from .huawei import HuaweiDriver

logger = logging.getLogger(__name__)

# 品牌识别优先级
DRIVER_CLASSES = [QuectelDriver, SimcomDriver, HuaweiDriver]


class ModemInstance:
    """单个模块实例"""

    def __init__(self, port, baudrate=115200, timeout=3, write_timeout=3,
                 module_id=None, name=None):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.module_id = module_id or str(uuid.uuid4())
        self.name = name or f"Module-{port.split('/')[-1]}"

        self.driver = None  # type: BaseModemDriver | None
        self.is_online = False
        self.is_initialized = False
        self.info = {}
        self.last_error = None
        self.last_communication = None

        # 监听线程
        self._listen_thread = None
        self._stop_event = threading.Event()
        self._sms_callbacks = []

    def add_sms_callback(self, callback):
        """添加短信接收回调"""
        if callback not in self._sms_callbacks:
            self._sms_callbacks.append(callback)

    def remove_sms_callback(self, callback):
        """移除短信接收回调"""
        if callback in self._sms_callbacks:
            self._sms_callbacks.remove(callback)

    def _on_sms_received(self, sms_data):
        """短信到达时通知所有回调"""
        for cb in self._sms_callbacks:
            try:
                cb(self.module_id, sms_data)
            except Exception as e:
                logger.error(f"[{self.name}] 短信回调异常: {e}")

    def connect(self):
        """连接并识别模块（增强异常处理，任何步骤失败均不导致程序退出）"""
        logger.info(f"[{self.name}] 正在连接 {self.port}...")

        # Step 1: 用 BaseDriver 打开串口
        base_driver = BaseModemDriver(self.port, self.baudrate, self.timeout, self.write_timeout)
        try:
            if not base_driver.open():
                self.last_error = f"无法打开串口 {self.port}"
                logger.info(f"[{self.name}] {self.last_error}")
                return False
        except Exception as e:
            self.last_error = f"打开串口异常: {type(e).__name__}: {e}"
            logger.error(f"[{self.name}] {self.last_error}")
            return False

        # Step 2: 测试 AT 通信
        try:
            if not base_driver.test_communication():
                base_driver.close()
                self.last_error = f"串口 {self.port} 无 AT 响应"
                logger.info(f"[{self.name}] {self.last_error}")
                return False
        except Exception as e:
            base_driver.close()
            self.last_error = f"AT 测试异常: {type(e).__name__}: {e}"
            logger.error(f"[{self.name}] {self.last_error}")
            return False

        # Step 3: 识别品牌和型号
        try:
            model = self._identify_model(base_driver)
            brand = self._identify_brand(model, base_driver)
            logger.info(f"[{self.name}] 识别: {brand} {model}")
        except Exception as e:
            logger.warning(f"[{self.name}] 识别品牌型号异常: {type(e).__name__}: {e}，使用默认")
            model = 'Unknown'
            brand = 'Generic'

        # Step 4: 关闭临时驱动，用正确的驱动重新打开
        driver_class = self._select_driver(brand, model)
        base_driver.close()
        time.sleep(0.3)

        self.driver = driver_class(self.port, self.baudrate, self.timeout, self.write_timeout)
        try:
            if not self.driver.open():
                self.last_error = f"无法用驱动 {driver_class.BRAND} 打开 {self.port}"
                logger.warning(f"[{self.name}] {self.last_error}")
                return False
        except Exception as e:
            self.last_error = f"驱动打开异常: {type(e).__name__}: {e}"
            logger.error(f"[{self.name}] {self.last_error}")
            return False

        # Step 5: 初始化模块
        try:
            if not self.driver.initialize():
                self.last_error = f"模块 {self.port} 初始化失败"
                logger.warning(f"[{self.name}] {self.last_error}")
                self.driver.close()
                return False
        except Exception as e:
            self.last_error = f"初始化异常: {type(e).__name__}: {e}"
            logger.error(f"[{self.name}] {self.last_error}")
            self.driver.close()
            return False

        # Step 6: 读取模块信息
        try:
            self._read_modem_info()
        except Exception as e:
            logger.error(f"[{self.name}] 读取模块信息异常: {type(e).__name__}: {e}")

        self.is_online = True
        self.is_initialized = True
        self.last_communication = datetime.now(timezone.utc)

        logger.info(
            f"[{self.name}] ✅ 模块连接成功: "
            f"{brand} {model} (IMEI: {self.info.get('imei', 'N/A')})"
        )
        return True

    def disconnect(self):
        """断开连接"""
        self._stop_event.set()
        if self._listen_thread:
            self._listen_thread.join(timeout=5)
        if self.driver:
            self.driver.close()
        self.is_online = False
        self.is_initialized = False

    def _identify_model(self, driver):
        """识别模块型号（增强版，支持更多品牌型号）"""
        # 优先用 +CGMM
        model = driver.get_model()
        if model:
            return model

        # 尝试从 ATI 中提取
        ati = driver.send_at_raw('ATI', timeout=3)
        response = ati.get('response', '') if isinstance(ati, dict) else ''
        if isinstance(ati, dict) and ati.get('success'):
            response = ati['response']
        else:
            response = str(ati)

        known_models = [
            # Quectel
            'EC20', 'EC25', 'EG25', 'EC200', 'EG91', 'EC21', 'BG95', 'BG96',
            'RG500', 'RG502', 'RM500', 'RM502', 'RG255', 'EG12',
            # SIMCom
            'SIM7600', 'SIM7600E', 'A7600', 'SIM7000', 'SIM800', 'SIM900',
            'A7670', 'A7680',
            # Huawei
            'ME909', 'ME906', 'MU609', 'MH5000',
        ]

        for line in response.split('\n'):
            line_upper = line.strip().upper()
            for kw in known_models:
                if kw.upper() in line_upper:
                    logger.info(f"[{self.port if hasattr(self,'port') else '?'}] ATI 识别到型号: {kw}")
                    return kw
        return 'Unknown'

    def _identify_brand(self, model, driver):
        """识别品牌（增强版，支持 5G 模块）"""
        model_upper = model.upper() if model else ''

        # Quectel 系列
        quectel_prefixes = ['EC', 'EG', 'RG', 'RM', 'BG', 'AG', 'UC', 'QUECTEL']
        if any(model_upper.startswith(p) for p in quectel_prefixes) or 'QUECTEL' in model_upper:
            return 'Quectel'

        # SIMCom 系列
        simcom_prefixes = ['SIM', 'A76', 'A767', 'A768']
        if any(model_upper.startswith(p) for p in simcom_prefixes):
            return 'SIMCom'

        # 华为
        huawei_prefixes = ['ME', 'MU', 'MH', 'HUAWEI']
        if any(model_upper.startswith(p) for p in huawei_prefixes):
            return 'Huawei'

        # ZTE
        if any(p in model_upper for p in ['ZM', 'ZTE']):
            return 'Quectel'  # ZTE 很多用移远芯片

        # 默认 Quectel（市场上最常见的 4G 模块品牌）
        logger.info(f"未识别品牌 '{model}'，默认使用 Quectel 驱动")
        return 'Quectel'

    def _select_driver(self, brand, model):
        """根据品牌选择驱动"""
        for cls in DRIVER_CLASSES:
            if cls.BRAND == brand:
                return cls
        return BaseModemDriver

    def _read_modem_info(self):
        """读取模块详细信息"""
        if not self.driver:
            return

        try:
            self.info['model'] = self.driver.get_model()
            self.info['firmware'] = self.driver.get_firmware_version()
            self.info['imei'] = self.driver.get_imei()
            self.info['iccid'] = self.driver.get_iccid()
            self.info['imsi'] = self.driver.get_imsi()
            self.info['sim_status'] = self.driver.get_sim_status()
            self.info['operator'] = self.driver.get_operator()
            self.info['network_type'] = self.driver.get_network_type()
            self.info['brand'] = self.driver.BRAND

            csq, rssi, percent = self.driver.get_signal()
            self.info['signal_csq'] = csq
            self.info['signal_rssi'] = rssi
            self.info['signal_percent'] = percent
            self.info['is_roaming'] = self.driver.get_roaming_status()

            stat, status_text = self.driver.get_network_registration()
            self.info['registration_status'] = status_text
        except Exception as e:
            logger.error(f"[{self.name}] 读取模块信息异常: {e}")

    def refresh_info(self):
        """刷新模块信息"""
        if self.is_online and self.driver:
            self._read_modem_info()
            self.last_communication = datetime.now(timezone.utc)

    def send_sms(self, phone, content):
        """发送短信"""
        if not self.is_online or not self.driver:
            return {'success': False, 'error': '模块不在线'}
        return self.driver.send_sms_text(phone, content)

    def exec_at(self, command, timeout=None):
        """执行AT指令"""
        if not self.is_online or not self.driver:
            return {'success': False, 'response': '', 'error': '模块不在线'}
        return self.driver.send_at_raw(command, timeout=timeout)

    def start_listening(self):
        """启动短信监听线程"""
        if self._listen_thread and self._listen_thread.is_alive():
            return
        self._stop_event.clear()
        self._listen_thread = threading.Thread(
            target=self._listen_loop,
            name=f"sms-listener-{self.port.split('/')[-1]}",
            daemon=True,
        )
        self._listen_thread.start()
        logger.info(f"[{self.name}] 短信监听线程已启动")

    def stop_listening(self):
        """停止短信监听"""
        self._stop_event.set()

    def _listen_loop(self):
        """短信监听循环"""
        logger.info(f"[{self.name}] 开始监听短信...")
        while not self._stop_event.is_set():
            try:
                if not self.is_online or not self.driver or not self.driver.is_open():
                    time.sleep(0.5)
                    continue

                line = self.driver._serial.readline()
                if not line:
                    continue

                decoded = line.decode('utf-8', errors='ignore').strip()
                if not decoded:
                    continue

                # 检查 +CMT:
                if '+CMT:' in decoded:
                    logger.info(f"[{self.name}] 收到新短信通知: {decoded}")
                    self._handle_cmt(decoded)
                elif decoded in ('OK', 'ERROR'):
                    continue
                elif decoded.startswith('+CME ERROR') or decoded.startswith('+CMS ERROR'):
                    logger.warning(f"[{self.name}] 模块错误: {decoded}")

            except (serial.SerialException, BrokenPipeError, PermissionError,
                    OSError, IOError) as e:
                logger.error(
                    f"[{self.name}] 串口异常 ({type(e).__name__}): {e}，标记离线"
                )
                self.is_online = False
                time.sleep(5)
            except Exception as e:
                logger.error(
                    f"[{self.name}] 监听异常 ({type(e).__name__}): {e}，继续监听"
                )
                time.sleep(1)

        logger.info(f"[{self.name}] 短信监听已停止")

    def _handle_cmt(self, cmt_line):
        """处理+CMT通知"""
        from utils.helpers import parse_cmt, parse_sms_time

        phone, date_str = parse_cmt(cmt_line)

        # 读取短信内容（下一行）
        content = ''
        try:
            for _ in range(5):
                line = self.driver._serial.readline().decode('utf-8', errors='ignore').strip()
                if not line:
                    continue
                if line in ('OK', 'ERROR'):
                    break
                if not line.startswith('+'):
                    content = line
                    break
        except Exception as e:
            logger.error(f"[{self.name}] 读取短信内容失败: {e}")

        receive_time = parse_sms_time(date_str)

        sms_data = {
            'phone': phone,
            'receive_time': receive_time,
            'content': content,
            'encoding': 'GSM7',
            'raw_cmt': cmt_line,
        }

        self._on_sms_received(sms_data)

    def sync_sms(self):
        """同步模块中的所有短信"""
        if not self.is_online or not self.driver:
            return []

        messages = []
        try:
            # 列出所有短信
            raw_messages = self.driver.list_sms('ALL')
            for msg in raw_messages:
                # 读取完整短信内容
                detail = self.driver.read_sms(msg['index'])
                if detail:
                    detail['index'] = msg['index']
                    detail['status'] = msg.get('status', 0)
                    messages.append(detail)
        except Exception as e:
            logger.error(f"[{self.name}] 同步短信失败: {e}")

        return messages

    def mark_read(self, index):
        """标记短信为已读"""
        if self.driver:
            self.driver.mark_sms_read(index)

    def delete_sms(self, index):
        """删除模块中的短信"""
        if self.driver:
            return self.driver.delete_sms(index)
        return False

    def to_dict(self):
        return {
            'module_id': self.module_id,
            'name': self.name,
            'port': self.port,
            'baudrate': self.baudrate,
            'is_online': self.is_online,
            'is_initialized': self.is_initialized,
            'brand': self.info.get('brand', 'Unknown'),
            'model': self.info.get('model', 'Unknown'),
            'firmware_version': self.info.get('firmware', 'Unknown'),
            'imei': self.info.get('imei', ''),
            'iccid': self.info.get('iccid', ''),
            'imsi': self.info.get('imsi', ''),
            'sim_status': self.info.get('sim_status', 'Unknown'),
            'operator': self.info.get('operator', 'Unknown'),
            'network_type': self.info.get('network_type', 'Unknown'),
            'signal_csq': self.info.get('signal_csq'),
            'signal_rssi': self.info.get('signal_rssi'),
            'signal_percent': self.info.get('signal_percent'),
            'is_roaming': self.info.get('is_roaming', False),
            'registration_status': self.info.get('registration_status', 'Unknown'),
            'last_error': self.last_error,
            'last_communication': self.last_communication.isoformat() if self.last_communication else None,
        }


class ModemManager:
    """多模块管理器 - 全局单例"""

    def __init__(self, config_manager, db_session_factory=None):
        self.config_manager = config_manager
        self.db_session_factory = db_session_factory
        self._modems = {}  # module_id -> ModemInstance
        self._lock = threading.Lock()
        self._sms_callbacks = []
        self._monitor_thread = None
        self._stop_event = threading.Event()

    def add_sms_callback(self, callback):
        """添加全局短信接收回调"""
        self._sms_callbacks.append(callback)

    def _on_global_sms(self, module_id, sms_data):
        """全局短信回调"""
        for cb in self._sms_callbacks:
            try:
                cb(module_id, sms_data)
            except Exception as e:
                logger.error(f"全局短信回调异常: {e}")

    def scan_ports(self):
        """扫描所有可用串口（按优先级排序 + 忽略配置）"""
        serial_config = self.config_manager.serial_config
        scan_patterns = serial_config.get('scan_ports', ['/dev/ttyUSB*', '/dev/ttyACM*'])
        preferred = serial_config.get('preferred_ports', [
            '/dev/ttyUSB2', '/dev/ttyUSB3', '/dev/ttyUSB1', '/dev/ttyUSB4'
        ])
        ignore = set(serial_config.get('ignore_ports', ['/dev/ttyUSB0']))
        default_port = serial_config.get('default_port', '/dev/ttyUSB2')

        logger.info(f"开始扫描串口... (忽略端口: {sorted(ignore)})")

        # 收集所有匹配的端口
        found_set = set()
        for pattern in scan_patterns:
            try:
                matches = glob.glob(pattern)
                found_set.update(matches)
            except Exception as e:
                logger.warning(f"扫描模式 {pattern} 异常: {type(e).__name__}: {e}")

        # 确保默认端口在列表中
        if default_port not in found_set and os.path.exists(default_port):
            found_set.add(default_port)

        # 过滤掉忽略的端口
        found_set -= ignore

        # 按优先级排序：preferred 中的排前面，其余按字母序
        def sort_key(p):
            try:
                return (0, preferred.index(p)) if p in preferred else (1, p)
            except ValueError:
                return (1, p)

        sorted_ports = sorted(found_set, key=sort_key)
        logger.info(f"扫描到 {len(sorted_ports)} 个可用串口: {sorted_ports}")
        return sorted_ports

    def try_connect_port(self, port, baudrate=115200):
        """尝试连接一个串口并识别是否为4G模块的AT口

        流程：
        1. 打开串口
        2. 发送 AT 测试是否响应 OK
        3. 发送 ATI/AT+CGMM 获取品牌型号
        4. 确认是真正的 AT 口后加入模块管理
        5. 任何步骤失败则跳过该端口，继续下一个
        """
        logger.info(f"── 正在探测端口: {port} ──")

        # 检查是否已被管理
        with self._lock:
            for modem in self._modems.values():
                if modem.port == port:
                    logger.info(f"[{port}] 端口已在管理中 (模块: {modem.name})，跳过")
                    return modem

        # Step 1: 打开串口
        base_driver = BaseModemDriver(port, baudrate, self.config_manager.get('serial.timeout', 3))
        if not base_driver.open():
            logger.info(f"[{port}] 打开失败，继续扫描其它端口...")
            return None

        logger.info(f"[{port}] 打开成功")

        # Step 2: AT 测试
        try:
            result = base_driver.send_at_raw('AT', timeout=2)
            if not result['success']:
                logger.info(f"[{port}] AT 测试失败（响应: {result.get('response','')[:100]}），不是有效的 AT 口，跳过")
                base_driver.close()
                return None
            logger.info(f"[{port}] AT 测试成功")
        except Exception as e:
            logger.info(f"[{port}] AT 测试异常: {type(e).__name__}: {e}，跳过")
            base_driver.close()
            return None

        # Step 3: 获取品牌型号
        try:
            model = self._identify_model(base_driver)
            brand = self._identify_brand(model, base_driver)
            logger.info(f"[{port}] 识别品牌: {brand}, 型号: {model}")
        except Exception as e:
            logger.warning(f"[{port}] 识别品牌型号异常: {type(e).__name__}: {e}，使用默认品牌")
            model = 'Unknown'
            brand = 'Generic'

        # Step 4: 获取 IMEI（进一步验证是真正的 AT 口）
        try:
            imei = base_driver.get_imei()
            logger.info(f"[{port}] IMEI: {imei or 'N/A'}")
        except Exception as e:
            logger.warning(f"[{port}] 获取 IMEI 异常: {type(e).__name__}: {e}")
            imei = ''

        # 关闭临时驱动
        base_driver.close()
        time.sleep(0.3)

        # Step 5: 用正确驱动重新连接
        driver_class = self._select_driver(brand, model)
        instance = ModemInstance(port, baudrate=baudrate,
                                 timeout=self.config_manager.get('serial.timeout', 3))
        instance.driver = driver_class(port, baudrate,
                                       self.config_manager.get('serial.timeout', 3))

        if not instance.driver.open():
            logger.warning(f"[{port}] 驱动 {driver_class.BRAND} 打开失败，跳过")
            return None

        # 初始化
        if not instance.driver.initialize():
            logger.warning(f"[{port}] 模块初始化失败，跳过")
            instance.driver.close()
            return None

        # 读取完整模块信息
        instance._read_modem_info()
        instance.is_online = True
        instance.is_initialized = True
        instance.last_communication = datetime.now(timezone.utc)

        logger.info(
            f"[{port}] ✅ 模块加入管理: "
            f"{instance.info.get('brand','')} {instance.info.get('model','')} "
            f"IMEI={instance.info.get('imei','N/A')}"
        )

        # 注册到管理器
        with self._lock:
            self._modems[instance.module_id] = instance
        instance.add_sms_callback(self._on_global_sms)
        instance.start_listening()
        self._save_modem_to_db(instance)

        return instance

    def auto_discover(self):
        """自动发现并连接所有4G模块（容错增强版）

        每个端口独立处理，任何一个端口异常不会影响其它端口。
        """
        serial_config = self.config_manager.serial_config
        baudrate = serial_config.get('baudrate', 115200)
        auto_scan = serial_config.get('auto_scan', True)

        if not auto_scan:
            logger.info("auto_scan 已禁用，跳过自动发现")
            return []

        ports = self.scan_ports()
        if not ports:
            logger.info("未扫描到任何串口")
            self._restore_from_db()
            return []

        connected = []
        failed = []

        for port in ports:
            try:
                instance = self.try_connect_port(port, baudrate)
                if instance:
                    connected.append(instance)
                else:
                    failed.append(port)
            except Exception as e:
                logger.error(
                    f"[{port}] 探测异常（不影响其它端口）: "
                    f"{type(e).__name__}: {e}"
                )
                failed.append(port)
                continue  # ← 关键：继续扫描下一个端口

        logger.info(
            f"自动发现完成: 成功={len(connected)} 个, "
            f"失败={len(failed)} 个 ({failed if failed else '无'})"
        )

        # 恢复数据库中的模块
        self._restore_from_db()

        return connected

    def get_modem(self, module_id):
        """获取指定模块"""
        with self._lock:
            return self._modems.get(module_id)

    def get_all_modems(self):
        """获取所有模块"""
        with self._lock:
            return dict(self._modems)

    def get_online_modems(self):
        """获取所有在线模块"""
        with self._lock:
            return {k: v for k, v in self._modems.items() if v.is_online}

    def update_modem_name(self, module_id, name):
        """更新模块备注"""
        with self._lock:
            modem = self._modems.get(module_id)
            if modem:
                modem.name = name
                try:
                    self._update_modem_in_db(modem)
                except Exception as e:
                    logger.warning(f"更新模块备注到数据库失败: {e}")

    def reconnect_modem(self, module_id):
        """重连指定模块（增强异常处理）"""
        with self._lock:
            modem = self._modems.get(module_id)
            if not modem:
                logger.warning(f"重连失败: 模块 {module_id} 不存在")
                return False

        logger.info(f"[{modem.name}] 正在重连...")
        try:
            modem.disconnect()
        except Exception as e:
            logger.warning(f"[{modem.name}] 断开旧连接异常: {type(e).__name__}: {e}")

        time.sleep(2)
        try:
            success = modem.connect()
        except Exception as e:
            logger.error(f"[{modem.name}] 重连异常: {type(e).__name__}: {e}")
            success = False

        if success:
            modem.start_listening()
            logger.info(f"[{modem.name}] ✅ 重连成功")
        else:
            logger.warning(f"[{modem.name}] ❌ 重连失败")

        return success

    def disable_modem(self, module_id):
        """禁用模块"""
        with self._lock:
            modem = self._modems.get(module_id)
            if modem:
                modem.stop_listening()
                modem.disconnect()
                del self._modems[module_id]
                self._delete_modem_from_db(module_id)

    def send_sms(self, module_id, phone, content):
        """通过指定模块发送短信"""
        modem = self.get_modem(module_id)
        if not modem:
            return {'success': False, 'error': '模块不存在'}
        return modem.send_sms(phone, content)

    def exec_at(self, module_id, command, timeout=None):
        """在指定模块执行AT指令"""
        modem = self.get_modem(module_id)
        if not modem:
            return {'success': False, 'response': '', 'error': '模块不存在'}
        return modem.exec_at(command, timeout=timeout)

    def sync_all_modems(self):
        """同步所有在线模块的短信"""
        results = {}
        with self._lock:
            for mid, modem in list(self._modems.items()):
                if modem.is_online:
                    try:
                        messages = modem.sync_sms()
                        results[mid] = messages
                        logger.info(f"[{modem.name}] 同步完成: {len(messages)} 条短信")
                    except Exception as e:
                        logger.error(f"[{modem.name}] 同步失败: {e}")
                        results[mid] = []
        return results

    def refresh_all_info(self):
        """刷新所有模块信息"""
        with self._lock:
            for modem in self._modems.values():
                if modem.is_online:
                    modem.refresh_info()
                    self._update_modem_in_db(modem)

    def start_auto_reconnect(self):
        """启动自动重连监控"""
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._auto_reconnect_loop,
            name="modem-reconnect-monitor",
            daemon=True,
        )
        self._monitor_thread.start()

    def stop_all(self):
        """停止所有模块"""
        self._stop_event.set()
        with self._lock:
            for modem in list(self._modems.values()):
                modem.stop_listening()
                modem.disconnect()
            self._modems.clear()

    def _auto_reconnect_loop(self):
        """自动重连监控循环（增强异常处理）"""
        serial_config = self.config_manager.serial_config
        interval = serial_config.get('reconnect_interval', 10)

        logger.info(f"自动重连监控已启动 (间隔={interval}s)")
        while not self._stop_event.is_set():
            time.sleep(interval)
            with self._lock:
                for mid, modem in list(self._modems.items()):
                    if not modem.is_online:
                        logger.info(f"[{modem.name}] 检测到离线，尝试自动重连...")
                        try:
                            if modem.connect():
                                modem.start_listening()
                                logger.info(f"[{modem.name}] ✅ 自动重连成功")
                            else:
                                logger.info(
                                    f"[{modem.name}] 自动重连失败 "
                                    f"({modem.last_error})，将在 {interval}s 后重试"
                                )
                        except Exception as e:
                            logger.error(
                                f"[{modem.name}] 自动重连异常 "
                                f"({type(e).__name__}): {e}"
                            )

    def _save_modem_to_db(self, instance):
        """保存模块信息到数据库"""
        if not self.db_session_factory:
            return
        try:
            from database.models import ModemInfo
            session = self.db_session_factory()
            existing = session.query(ModemInfo).filter_by(port=instance.port).first()
            if existing:
                existing.module_id = instance.module_id
                existing.name = instance.name
                existing.brand = instance.info.get('brand')
                existing.model = instance.info.get('model')
                existing.firmware_version = instance.info.get('firmware')
                existing.imei = instance.info.get('imei')
                existing.iccid = instance.info.get('iccid')
                existing.imsi = instance.info.get('imsi')
                existing.is_online = True
            else:
                modem_info = ModemInfo(
                    module_id=instance.module_id,
                    name=instance.name,
                    port=instance.port,
                    baudrate=instance.baudrate,
                    brand=instance.info.get('brand'),
                    model=instance.info.get('model'),
                    firmware_version=instance.info.get('firmware'),
                    imei=instance.info.get('imei'),
                    iccid=instance.info.get('iccid'),
                    imsi=instance.info.get('imsi'),
                    is_online=True,
                )
                session.add(modem_info)
            session.commit()
            session.close()
        except Exception as e:
            logger.error(f"保存模块到数据库失败: {e}")

    def _update_modem_in_db(self, instance):
        """更新数据库中的模块信息"""
        if not self.db_session_factory:
            return
        try:
            from database.models import ModemInfo
            session = self.db_session_factory()
            record = session.query(ModemInfo).filter_by(module_id=instance.module_id).first()
            if record:
                record.is_online = instance.is_online
                record.operator = instance.info.get('operator')
                record.network_type = instance.info.get('network_type')
                record.signal_csq = instance.info.get('signal_csq')
                record.signal_rssi = instance.info.get('signal_rssi')
                record.signal_percent = instance.info.get('signal_percent')
                record.is_roaming = instance.info.get('is_roaming')
                record.sim_status = instance.info.get('sim_status')
                record.registration_status = instance.info.get('registration_status')
                record.last_communication = instance.last_communication
                session.commit()
            session.close()
        except Exception as e:
            logger.error(f"更新模块数据库失败: {e}")

    def _delete_modem_from_db(self, module_id):
        """从数据库删除模块"""
        if not self.db_session_factory:
            return
        try:
            from database.models import ModemInfo
            session = self.db_session_factory()
            session.query(ModemInfo).filter_by(module_id=module_id).delete()
            session.commit()
            session.close()
        except Exception as e:
            logger.error(f"从数据库删除模块失败: {e}")

    def _restore_from_db(self):
        """从数据库恢复模块信息"""
        if not self.db_session_factory:
            return
        try:
            from database.models import ModemInfo
            session = self.db_session_factory()
            records = session.query(ModemInfo).filter_by(enabled=True).all()
            for rec in records:
                if rec.port not in [m.port for m in self._modems.values()]:
                    # 端口尚未连接，标记为离线
                    rec.is_online = False
            session.commit()
            session.close()
        except Exception as e:
            logger.error(f"从数据库恢复模块失败: {e}")

    def get_statistics(self):
        """获取模块统计信息"""
        with self._lock:
            total = len(self._modems)
            online = sum(1 for m in self._modems.values() if m.is_online)
            offline = total - online
            return {
                'total': total,
                'online': online,
                'offline': offline,
            }
