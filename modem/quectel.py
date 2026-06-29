# modem/quectel.py
"""移远(Quectel)模块驱动 - 重点支持EC20/EC25/EG25等"""
import re
import logging
from .base import BaseModemDriver

logger = logging.getLogger(__name__)


class QuectelDriver(BaseModemDriver):
    """移远模块驱动

    支持: EC20, EC25, EG25, EC200, EG91 等
    """

    BRAND = 'Quectel'
    SUPPORTED_MODELS = ['EC20', 'EC25', 'EG25', 'EC200', 'EG91', 'EC21', 'EC200T', 'EG21']

    def get_manufacturer(self):
        """获取制造商信息"""
        result = self.send_at_raw('ATI')
        return result['response'] if result['success'] else ''

    def get_model(self):
        """获取型号 - Quectel特有解析"""
        result = self.send_at_raw('AT+CGMM')
        response = result['response']
        # Quectel通常返回类似 "EC20" 或 "Quectel EC20"
        model = self._extract_value(response, '+CGMM:')
        if not model:
            # 尝试从ATI中提取
            ati = self.send_at_raw('ATI')
            for line in ati['response'].split('\n'):
                line = line.strip()
                if any(m in line for m in self.SUPPORTED_MODELS):
                    return line
        return model

    def get_firmware_version(self):
        """获取固件版本"""
        result = self.send_at_raw('AT+CGMR')
        return self._extract_value(result['response'], '+CGMR:')

    def get_imei(self):
        """获取IMEI - 兼容Quectel"""
        result = self.send_at_raw('AT+CGSN')
        response = result['response']
        match = re.search(r'(\d{15})', response)
        return match.group(1) if match else ''

    def get_network_type(self):
        """获取网络制式 - Quectel专用"""
        # 首先尝试 QNWINFO
        result = self.send_at_raw('AT+QNWINFO')
        response = result['response']
        qnw_match = re.search(r'\+QNWINFO:\s*"([^"]*)","([^"]*)","([^"]*)",(\d+)', response)
        if qnw_match:
            act_str = qnw_match.group(1)
            # QNWINFO返回的ACT字段
            if 'LTE' in act_str:
                return 'LTE'
            elif 'WCDMA' in act_str or 'HSPA' in act_str:
                return 'WCDMA'
            elif 'GSM' in act_str:
                return 'GSM'
            elif 'NR' in act_str or '5G' in act_str:
                return '5G NR'

        # 回退到标准方式
        return super().get_network_type()

    def get_operator(self):
        """获取运营商 - Quectel增强"""
        # 使用 QNWINFO 获取更准确的信息
        result = self.send_at_raw('AT+QNWINFO')
        response = result['response']
        qnw_match = re.search(r'\+QNWINFO:\s*"[^"]*","([^"]*)","[^"]*",\d+', response)
        if qnw_match and qnw_match.group(1):
            operator = qnw_match.group(1)
            if operator:
                return operator

        # 回退到标准COPS
        return super().get_operator()

    def get_cops_info(self):
        """获取详细运营商信息"""
        result = self.send_at_raw('AT+COPS?')
        response = result['response']
        # 格式: +COPS: <mode>[,<format>[,<oper>[,<Act>]]]
        match = re.search(r'\+COPS:\s*(\d+),(\d+),"([^"]*)",(\d+)', response)
        if match:
            act = int(match.group(4))
            act_map = {0: 'GSM', 2: 'UTRAN', 3: 'EGPRS', 4: 'HSDPA', 5: 'HSUPA',
                       6: 'HSPA', 7: 'LTE', 8: 'eMTC', 9: 'NB-IoT', 10: '5G NR'}
            return {
                'mode': int(match.group(1)),
                'format': int(match.group(2)),
                'operator': match.group(3),
                'act': act,
                'act_name': act_map.get(act, f'Unknown({act})'),
            }
        return super().get_operator()

    def get_signal(self):
        """获取信号强度"""
        csq, rssi, percent = super().get_signal()
        return csq, rssi, percent

    def get_extended_signal(self):
        """扩展信号信息查询 - Quectel专用"""
        result = self.send_at_raw('AT+QCSQ')
        response = result['response']
        info = {}
        # 格式: +QCSQ: "<sysmode>",<value1>,<value2>,...
        match = re.search(r'\+QCSQ:\s*"([^"]*)"(.*)', response)
        if match:
            info['sysmode'] = match.group(1)
            parts = match.group(2).split(',')
            # 解析额外值
            for i, part in enumerate(parts):
                part = part.strip().strip('"')
                info[f'value_{i}'] = part
        return info

    def list_sms(self, status='ALL'):
        """列出短信 - Quectel优化"""
        # Quectel支持更多状态参数
        return super().list_sms(status)

    def delete_all_sms(self):
        """删除所有短信 - Quectel特有"""
        try:
            result = self.send_at_raw('AT+CMGDA="DEL ALL"', timeout=10)
            return result['success']
        except Exception as e:
            logger.error(f"[{self.port}] 删除所有短信失败: {e}")
            return False

    # Quectel扩展AT指令

    def get_ccid(self):
        """获取SIM卡CCID"""
        return self.get_iccid()

    def get_apn(self):
        """获取当前APN"""
        result = self.send_at_raw('AT+CGDCONT?')
        response = result['response']
        match = re.search(r'\+CGDCONT:\s*\d+,"([^"]*)","([^"]*)', response)
        return match.group(2) if match else ''

    def set_apn(self, apn, cid=1):
        """设置APN"""
        result = self.send_at_raw(f'AT+CGDCONT={cid},"IP","{apn}"')
        return result['success']

    def get_location(self):
        """获取基站定位 (如果支持)"""
        result = self.send_at_raw('AT+QCELLLOC?', timeout=10)
        return result['response']

    def reset_module(self):
        """重置模块"""
        logger.info(f"[{self.port}] 正在重置Quectel模块...")
        result = self.send_at_raw('AT+CFUN=1,1', timeout=10)
        return result['success']

    def initialize(self):
        """Quectel模块初始化"""
        if not super().initialize():
            return False

        # Quectel额外初始化
        try:
            # 确保网络功能开启
            self.send_at('AT+CFUN=1', timeout=3)
            # 设置URC上报模式
            self.send_at('AT+QURCCFG="urcport","usbmodem"', timeout=1)
            # 检查网络注册
            self.send_at('AT+CREG=2', timeout=1)  # 启用网络注册URC
            self.send_at('AT+CGREG=2', timeout=1)  # GPRS注册URC
        except Exception as e:
            logger.warning(f"[{self.port}] Quectel额外初始化异常: {e}")

        return True
