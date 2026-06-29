# modem/simcom.py
"""SIMCom模块驱动 - 支持SIM7600/A7600等"""
import re
import logging
from .base import BaseModemDriver

logger = logging.getLogger(__name__)


class SimcomDriver(BaseModemDriver):
    """SIMCom模块驱动

    支持: SIM7600, A7600, SIM7000, SIM800 等
    """

    BRAND = 'SIMCom'
    SUPPORTED_MODELS = ['SIM7600', 'A7600', 'SIM7000', 'SIM800', 'SIM900', 'SIM7600E']

    def get_model(self):
        """获取型号"""
        result = self.send_at_raw('AT+CGMM')
        response = result['response']
        model = self._extract_value(response, '+CGMM:')
        if not model:
            ati = self.send_at_raw('ATI')
            for line in ati['response'].split('\n'):
                line = line.strip()
                if 'SIM' in line or 'A7600' in line:
                    return line
        return model

    def get_network_type(self):
        """获取网络制式 - SIMCom"""
        # 尝试 CNSMOD
        result = self.send_at_raw('AT+CNSMOD?')
        response = result['response']
        match = re.search(r'\+CNSMOD:\s*(\d+),(\d+)', response)
        if match:
            mode = int(match.group(2))
            mode_map = {0: '无服务', 1: 'GSM', 2: 'WCDMA', 3: 'LTE', 4: 'TD-SCDMA',
                        5: 'CDMA', 6: 'EVDO', 7: 'eMTC', 8: 'NB-IoT'}
            return mode_map.get(mode, f'Unknown({mode})')

        return super().get_network_type()

    def get_operator(self):
        """获取运营商"""
        # SIMCom COPS格式可能不同
        result = self.send_at_raw('AT+COPS?')
        response = result['response']
        match = re.search(r'\+COPS:\s*(\d+),(\d+),"([^"]*)",(\d+)', response)
        if match:
            operator = match.group(3)
            if operator:
                try:
                    bytes.fromhex(operator)
                    return bytes.fromhex(operator).decode('utf-16-be', errors='ignore')
                except ValueError:
                    return operator

        # 尝试短格式
        match = re.search(r'\+COPS:\s*(\d+),(\d+),"([^"]*)"', response)
        if match:
            return match.group(3)

        return 'Unknown'

    def get_signal(self):
        """获取信号强度"""
        return super().get_signal()

    def get_cops_info(self):
        """获取详细网络信息"""
        result = self.send_at_raw('AT+COPS?')
        response = result['response']
        match = re.search(r'\+COPS:\s*(\d+),(\d+),"([^"]*)",(\d+)', response)
        if match:
            act = int(match.group(4))
            act_map = {0: 'GSM', 2: 'UTRAN', 3: 'EGPRS', 4: 'HSDPA',
                       5: 'HSUPA', 6: 'HSPA', 7: 'LTE', 8: 'eMTC', 9: 'NB-IoT'}
            return {
                'mode': int(match.group(1)),
                'format': int(match.group(2)),
                'operator': match.group(3),
                'act': act,
                'act_name': act_map.get(act, f'Unknown({act})'),
            }
        return {}

    def initialize(self):
        """SIMCom模块初始化"""
        if not super().initialize():
            return False

        try:
            # SIMCom额外配置
            self.send_at('AT+CFUN=1', timeout=3)
            self.send_at('AT+CREG=2', timeout=1)
        except Exception as e:
            logger.warning(f"[{self.port}] SIMCom额外初始化异常: {e}")

        return True
