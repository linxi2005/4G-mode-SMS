# modem/huawei.py
"""华为模块驱动 - 支持ME909等"""
import re
import logging
from .base import BaseModemDriver

logger = logging.getLogger(__name__)


class HuaweiDriver(BaseModemDriver):
    """华为模块驱动

    支持: ME909, ME906, MU609, MH5000 等
    """

    BRAND = 'Huawei'
    SUPPORTED_MODELS = ['ME909', 'ME906', 'MU609', 'MH5000', 'ME909s']

    def get_model(self):
        """获取型号"""
        result = self.send_at_raw('AT+CGMM')
        response = result['response']
        model = self._extract_value(response, '+CGMM:')
        if not model:
            ati = self.send_at_raw('ATI')
            for line in ati['response'].split('\n'):
                line = line.strip()
                if 'ME' in line or 'MU' in line or 'MH' in line:
                    return line
        return model

    def get_network_type(self):
        """获取网络制式 - 华为"""
        result = self.send_at_raw('AT^SYSINFO')
        response = result['response']
        # ^SYSINFO: <srv_status>,<srv_domain>,<roam>,<mode>,<sim>,<sysmode>,...
        match = re.search(r'\^SYSINFO:\s*\d+,\d+,\d+,\d+,\d+,(\d+)', response)
        if match:
            mode = int(match.group(1))
            mode_map = {0: '无服务', 1: 'GSM', 2: 'GPRS', 3: 'EDGE', 4: 'WCDMA',
                        5: 'HSDPA', 6: 'HSUPA', 7: 'HSPA+', 8: 'TD-SCDMA',
                        9: 'HSPA+', 10: 'LTE', 11: 'eMTC', 12: 'NB-IoT', 13: '5G NR'}
            return mode_map.get(mode, f'Unknown({mode})')

        return super().get_network_type()

    def get_operator(self):
        """获取运营商"""
        return super().get_operator()

    def get_signal(self):
        """获取信号强度 - 华为可能有自己的格式"""
        # 标准 CSQ
        csq, rssi, percent = super().get_signal()

        # 尝试扩展信号查询
        result = self.send_at_raw('AT^HCSQ?')
        response = result['response']
        match = re.search(r'\^HCSQ:\s*"([^"]*)",(\d+),(\d+),(\d+),(\d+)', response)
        if match:
            percent = int(match.group(3))

        return csq, rssi, percent

    def get_sim_status(self):
        """获取SIM状态"""
        result = self.send_at_raw('AT^SIMST?')
        response = result['response']
        match = re.search(r'\^SIMST:\s*(\d+)', response)
        if match:
            status = int(match.group(1))
            status_map = {0: 'SIM卡不存在', 1: 'SIM卡存在', 255: '物理错误'}
            return status_map.get(status, f'Unknown({status})')
        return super().get_sim_status()

    def initialize(self):
        """华为模块初始化"""
        if not super().initialize():
            return False

        try:
            self.send_at('AT+CFUN=1', timeout=3)
            self.send_at('AT+CREG=2', timeout=1)
        except Exception as e:
            logger.warning(f"[{self.port}] 华为额外初始化异常: {e}")

        return True
