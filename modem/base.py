# modem/base.py
"""AT指令基础驱动 - 提供通用AT指令实现，作为所有驱动的基类"""
import serial
import time
import re
import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ATError(Exception):
    """AT指令错误"""
    pass


class ATTimeoutError(ATError):
    """AT指令超时"""
    pass


class ModemNotRespondingError(ATError):
    """模块无响应"""
    pass


class BaseModemDriver:
    """AT指令基础驱动

    提供通用的AT指令封装，所有品牌驱动继承此类。
    特定品牌可覆盖特定方法实现差异化功能。
    """

    BRAND = 'Generic'
    SUPPORTED_MODELS = []

    def __init__(self, port, baudrate=115200, timeout=3, write_timeout=3):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self._serial = None
        self._lock = threading.Lock()
        self._response_buffer = []
        self._is_open = False

    # ---- 串口操作 ----

    def open(self):
        """打开串口连接（增强异常处理，兼容 ARM/Linux 全部异常类型）"""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=self.write_timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                rtscts=False,
                xonxoff=False,
            )
            self._is_open = True
            logger.info(f"[{self.port}] 串口已打开 (baudrate={self.baudrate})")
            return True
        except (serial.SerialException, BrokenPipeError, PermissionError,
                OSError, IOError, TimeoutError, Exception) as e:
            logger.warning(
                f"[{self.port}] 打开串口失败 "
                f"(类型={type(e).__name__}, 原因={e})"
            )
            self._is_open = False
            return False

    def close(self):
        """关闭串口"""
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception as e:
                logger.warning(f"[{self.port}] 关闭串口异常: {e}")
            finally:
                self._is_open = False
                logger.info(f"[{self.port}] 串口已关闭")

    def is_open(self):
        """检查串口是否打开"""
        return self._is_open and self._serial is not None and self._serial.is_open

    def flush(self):
        """清空串口缓冲区"""
        if self.is_open():
            try:
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
            except Exception:
                pass

    # ---- AT指令核心 ----

    def send_at(self, command, wait_response=True, timeout=None):
        """发送AT指令并获取响应

        Args:
            command: AT指令 (不含末尾\r\n)
            wait_response: 是否等待响应
            timeout: 超时时间(秒)

        Returns:
            str: 原始响应内容
        """
        if not self.is_open():
            raise ModemNotRespondingError(f"[{self.port}] 串口未打开")

        effective_timeout = timeout or self.timeout

        with self._lock:
            try:
                # 发送指令
                full_command = command + '\r\n'
                self._serial.write(full_command.encode('utf-8', errors='ignore'))
                self._serial.flush()

                if not wait_response:
                    return ''

                # 读取响应
                self._serial.timeout = effective_timeout
                response_lines = []
                start_time = time.time()

                while True:
                    if time.time() - start_time > effective_timeout:
                        break
                    try:
                        line = self._serial.readline()
                        if not line:
                            break
                        decoded = line.decode('utf-8', errors='ignore').strip()
                        if decoded:
                            response_lines.append(decoded)
                        # 检测是否收到OK/ERROR/CME ERROR
                        if decoded in ('OK', 'ERROR') or decoded.startswith('+CME ERROR'):
                            break
                        if decoded.startswith('>'):
                            break  # 等待更多输入（如发送短信）
                    except serial.SerialTimeoutException:
                        break
                    except Exception as e:
                        logger.error(f"[{self.port}] 读取响应异常: {e}")
                        break

                response = '\n'.join(response_lines)
                logger.debug(f"[{self.port}] AT> {command}\nAT< {response[:200]}")
                return response

            except serial.SerialException as e:
                logger.error(f"[{self.port}] 串口通信错误: {e}")
                self._is_open = False
                raise ModemNotRespondingError(f"[{self.port}] 串口通信错误: {e}")

    def send_at_raw(self, command, timeout=None, retries=2):
        """发送原始AT指令并返回结构化结果，支持超时重试

        Returns:
            dict: {'success': bool, 'response': str, 'error': str or None}
        """
        last_error = None
        for attempt in range(retries):
            try:
                response = self.send_at(command, timeout=timeout)
                # 检查是否成功
                if 'OK' in response.split('\n')[-2:]:
                    return {'success': True, 'response': response, 'error': None}
                elif 'ERROR' in response:
                    last_error = 'AT ERROR'
                    if '+CME ERROR' in response:
                        err_match = re.search(r'\+CME ERROR:\s*(.+)', response)
                        last_error = err_match.group(1) if err_match else 'CME ERROR'
                elif '+CME ERROR' in response:
                    err_match = re.search(r'\+CME ERROR:\s*(.+)', response)
                    last_error = err_match.group(1) if err_match else 'CME ERROR'
                else:
                    return {'success': True, 'response': response, 'error': None}
            except ModemNotRespondingError as e:
                last_error = str(e)
            except Exception as e:
                logger.error(f"[{self.port}] send_at_raw异常 (attempt {attempt+1}/{retries}): {e}")
                last_error = str(e)

            if attempt < retries - 1:
                logger.debug(f"[{self.port}] AT重试 ({attempt+1}/{retries}): {command} - {last_error}")
                time.sleep(0.5)

        return {'success': False, 'response': '', 'error': last_error or 'Unknown error'}

    def send_sms_text(self, phone, content):
        """发送文本模式短信"""
        try:
            # 设置文本模式
            self.send_at('AT+CMGF=1', timeout=1)
            time.sleep(0.2)

            # 设置接收号码
            result = self.send_at(f'AT+CMGS="{phone}"', timeout=1)
            if '>' not in result:
                return {'success': False, 'error': '模块未进入短信输入模式'}

            # 发送短信内容 + Ctrl+Z
            content_bytes = (content + '\x1A').encode('utf-8', errors='ignore')
            self._serial.write(content_bytes)
            self._serial.flush()

            # 等待发送结果
            time.sleep(2)
            response_lines = []
            start = time.time()
            while time.time() - start < 10:
                line = self._serial.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    response_lines.append(line)
                if 'OK' in line or 'ERROR' in line or '+CMS ERROR' in line:
                    break

            response = '\n'.join(response_lines)
            if 'OK' in response:
                return {'success': True, 'response': response}
            elif '+CMS ERROR' in response:
                err = re.search(r'\+CMS ERROR:\s*(.+)', response)
                return {'success': False, 'error': err.group(1) if err else 'CMS ERROR'}
            else:
                return {'success': False, 'error': '发送超时或失败'}
        except Exception as e:
            logger.error(f"[{self.port}] 发送短信失败: {e}")
            return {'success': False, 'error': str(e)}

    # ---- 信息获取 ----

    def get_manufacturer(self):
        """获取制造商信息"""
        result = self.send_at_raw('ATI')
        return result['response'] if result['success'] else ''

    def get_model(self):
        """获取型号"""
        result = self.send_at_raw('AT+CGMM')
        return self._extract_value(result['response'], '+CGMM:')

    def get_firmware_version(self):
        """获取固件版本"""
        result = self.send_at_raw('AT+CGMR')
        return self._extract_value(result['response'], '+CGMR:')

    def get_imei(self):
        """获取IMEI"""
        result = self.send_at_raw('AT+CGSN')
        response = result['response']
        # 提取IMEI（通常为15位纯数字）
        match = re.search(r'(\d{15})', response)
        return match.group(1) if match else ''

    def get_iccid(self):
        """获取ICCID"""
        result = self.send_at_raw('AT+CCID')
        match = re.search(r'\+CCID:\s*"?(\d+)"?', result['response'])
        return match.group(1) if match else ''

    def get_imsi(self):
        """获取IMSI"""
        result = self.send_at_raw('AT+CIMI')
        response = result['response'].strip()
        # IMSI通常为15位数字
        match = re.search(r'(\d{15})', response)
        return match.group(1) if match else ''

    def get_signal(self):
        """获取信号强度 返回 (csq, rssi, percent)"""
        result = self.send_at_raw('AT+CSQ')
        response = result['response']
        match = re.search(r'\+CSQ:\s*(\d+),(\d*)', response)
        if match:
            csq = int(match.group(1))
            rssi = -113 + 2 * csq if csq != 99 else None
            percent = min(100, int(csq / 31 * 100)) if csq != 99 else 0
            return csq, rssi, percent
        return None, None, 0

    def get_operator(self):
        """获取运营商信息"""
        result = self.send_at_raw('AT+COPS?')
        response = result['response']
        match = re.search(r'\+COPS:\s*\d+,\d+,"([^"]*)"', response)
        if match:
            operator = match.group(1)
            if operator:
                # 尝试解码十六进制运营商名称
                try:
                    bytes.fromhex(operator)
                    return bytes.fromhex(operator).decode('utf-16-be', errors='ignore')
                except ValueError:
                    return operator
        # 长格式
        match = re.search(r'\+COPS:\s*\d+,\d+,"[^"]*",\d+', response)
        if match:
            # 尝试 COPS=? 获取
            cops_test = self.send_at_raw('AT+COPS=?', timeout=5)
            logger.debug(f"COPS=? response: {cops_test['response']}")
        return 'Unknown'

    def get_network_registration(self):
        """获取网络注册状态"""
        result = self.send_at_raw('AT+CREG?')
        response = result['response']
        match = re.search(r'\+CREG:\s*(\d+),(\d+)', response)
        if match:
            stat = int(match.group(2))
            status_map = {
                0: '未注册',
                1: '已注册(本地)',
                2: '搜索中',
                3: '注册被拒绝',
                4: '未知',
                5: '已注册(漫游)',
            }
            return stat, status_map.get(stat, f'未知({stat})')
        return None, 'Unknown'

    def get_network_type(self):
        """获取当前网络制式"""
        result = self.send_at_raw('AT+COPS?')
        response = result['response']
        match = re.search(r'\+COPS:\s*(\d+),(\d+),"([^"]*)",(\d+)', response)
        if match:
            act = int(match.group(4))
            act_map = {0: 'GSM', 2: 'UTRAN', 3: 'EGPRS', 4: 'HSDPA', 5: 'HSUPA',
                       6: 'HSPA', 7: 'LTE', 8: 'eMTC', 9: 'NB-IoT', 10: '5G NR'}
            return act_map.get(act, f'RAT:{act}')
        return 'Unknown'

    def get_sim_status(self):
        """获取SIM卡状态"""
        result = self.send_at_raw('AT+CPIN?')
        response = result['response']
        if 'READY' in response:
            return '已就绪'
        elif 'SIM PIN' in response:
            return '需要PIN码'
        elif 'SIM PUK' in response:
            return '需要PUK码'
        elif 'PH-SIM PIN' in response:
            return '需要Phone-SIM PIN'
        elif 'SIM PIN2' in response:
            return '需要PIN2'
        elif 'NOT INSERTED' in response or 'NOT READY' in response:
            return '未插卡'
        else:
            return '未知状态'

    def get_roaming_status(self):
        """检查是否漫游"""
        stat, _ = self.get_network_registration()
        return stat == 5 if stat is not None else False

    # ---- 短信操作 ----

    def set_text_mode(self):
        """设置文本模式"""
        result = self.send_at_raw('AT+CMGF=1')
        return result['success']

    def set_cpms(self, read_storage='MT', send_storage='MT', new_storage='MT'):
        """设置短信首选存储
        
        AT+CPMS="MT","MT","MT" — 读写新短信统一使用 MT (模块+SIM卡)
        """
        result = self.send_at_raw(f'AT+CPMS="{read_storage}","{send_storage}","{new_storage}"')
        return result['success']

    def set_sms_notification(self):
        """开启短信通知（新短信保存到模块 + 输出 CMTI 索引通知）
        
        AT+CNMI=2,1,0,0,0:
        - mode=2: 直接缓存到模块，输出 +CMTI: <mem>,<index>
        - mt=1: 收到短信后保存到模块并输出通知
        - bm=0, ds=0, bfr=0: 不发送广播/状态报告通知
        
        使用 +CMTI 而非 +CMT，确保短信持久保存到模块存储，重启不丢失。
        """
        result = self.send_at_raw('AT+CNMI=2,1,0,0,0')
        return result['success']

    def list_sms(self, status='ALL'):
        """列出模块中的短信

        Args:
            status: ALL, REC UNREAD, REC READ, STO UNSENT, STO SENT
        """
        result = self.send_at_raw(f'AT+CMGL="{status}"', timeout=10)
        return self._parse_cmgl_response(result['response'])

    def read_sms(self, index):
        """读取指定索引的短信"""
        result = self.send_at_raw(f'AT+CMGR={index}')
        return self._parse_cmgr_response(result['response'], index)

    def delete_sms(self, index):
        """删除指定索引的短信"""
        result = self.send_at_raw(f'AT+CMGD={index}')
        return result['success']

    def mark_sms_read(self, index):
        """标记短信为已读 (通过读取实现)"""
        return self.read_sms(index)

    # ---- 解析方法 ----

    def _parse_cmgl_response(self, response):
        """解析 CMGL 响应，返回短信列表"""
        messages = []
        if not response:
            return messages

        lines = response.split('\n')
        current_msg = None

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line in ('OK', 'ERROR'):
                continue

            cmgl_match = re.match(r'\+CMGL:\s*(\d+),(\d+),?.*,"([^"]*)"', line)
            if cmgl_match:
                if current_msg:
                    messages.append(current_msg)
                current_msg = {
                    'index': int(cmgl_match.group(1)),
                    'status': int(cmgl_match.group(2)),
                    'date': cmgl_match.group(3) if cmgl_match.lastindex and cmgl_match.lastindex >= 3 else '',
                }
            elif current_msg is not None:
                current_msg['content'] = line

        if current_msg:
            messages.append(current_msg)

        return messages

    def _parse_cmgr_response(self, response, index):
        """解析 CMGR 响应"""
        if not response:
            return None

        msg = {'index': index}
        lines = response.split('\n')

        for i, line in enumerate(lines):
            line = line.strip()
            if line in ('OK', 'ERROR'):
                continue

            cmgr_match = re.match(
                r'\+CMGR:\s*"?(\d+)"?,\s*"?([^"]*)"?,\s*"?([^"]*)"?,\s*"?([^"]*)"?',
                line
            )
            if cmgr_match:
                # 尝试解析多种格式
                parts = re.split(r',\s*', re.sub(r'^\+CMGR:\s*', '', line))
                msg['status'] = parts[0].strip('"') if len(parts) > 0 else ''
                msg['sender'] = parts[1].strip('"') if len(parts) > 1 else ''
                # date might be empty
                if len(parts) > 4:
                    msg['date'] = parts[3].strip('"')
                elif len(parts) > 2:
                    msg['date'] = parts[2].strip('"') if len(parts) > 2 and parts[2] else ''
                continue

            if i > 0 and line and not line.startswith('+CMGR:') and not line.startswith('AT+'):
                msg['content'] = line

        return msg

    def _extract_value(self, response, prefix):
        """从响应中提取某前缀后的值"""
        for line in response.split('\n'):
            line = line.strip()
            if line.startswith(prefix):
                return line.replace(prefix, '').strip()
            if line and not line.startswith('AT') and line not in ('OK', 'ERROR'):
                return line
        return ''

    # ---- 初始化 ----

    def initialize(self):
        """初始化模块：标准 EC20 短信就绪流程
        
        序列: ATE0 → CMGF=1 → CPMS="MT","MT","MT" → CNMI=2,1,0,0,0
        
        CNMI=2,1 确保短信先保存到模块存储再发 CMTI 通知，
        防止 +CMT 直接推送模式导致短信不落存储、重启丢失。
        """
        try:
            # 基础 AT 测试
            result = self.send_at_raw('AT', timeout=2)
            if not result['success']:
                logger.warning(f"[{self.port}] AT测试失败，模块可能不在线")
                return False

            # 关闭回显
            self.send_at_raw('ATE0', timeout=1)
            logger.debug(f"[{self.port}] ATE0 已设置")

            # 设置文本模式
            if not self.set_text_mode():
                logger.warning(f"[{self.port}] 设置文本模式 (CMGF=1) 失败")
            else:
                logger.debug(f"[{self.port}] CMGF=1 已设置")

            # 设置短信存储位置
            if not self.set_cpms('MT', 'MT', 'MT'):
                logger.warning(f"[{self.port}] 设置短信存储 (CPMS) 失败")
            else:
                logger.debug(f"[{self.port}] CPMS=\"MT\",\"MT\",\"MT\" 已设置")

            # 开启短信通知（CMTI 模式）
            if not self.set_sms_notification():
                logger.warning(f"[{self.port}] 设置短信通知 (CNMI=2,1) 失败")
            else:
                logger.debug(f"[{self.port}] CNMI=2,1,0,0,0 已设置")

            logger.info(
                f"[{self.port}] 模块初始化完成 "
                f"(CMGF=1, CPMS=MT, CNMI=2,1 → CMTI 通知模式)"
            )
            return True
        except Exception as e:
            logger.error(f"[{self.port}] 初始化失败: {e}")
            return False

    def test_communication(self):
        """测试模块通信是否正常"""
        result = self.send_at_raw('AT', timeout=2)
        return result['success']

    def __repr__(self):
        return f"<{self.BRAND} Driver port={self.port}>"
