# utils/helpers.py
"""通用辅助函数"""
import hashlib
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def generate_sms_hash(phone, receive_time, content, imei=''):
    """生成短信唯一哈希用于去重"""
    raw = f"{phone}|{receive_time}|{content}|{imei}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def decode_ucs2(hex_string):
    """将UCS2编码的十六进制字符串解码为UTF-8"""
    try:
        if not hex_string:
            return ''
        hex_string = hex_string.strip().replace(' ', '')
        bytes_data = bytes.fromhex(hex_string)
        return bytes_data.decode('utf-16-be', errors='replace')
    except (ValueError, UnicodeDecodeError) as e:
        logger.warning(f"UCS2解码失败: {e}")
        return hex_string


def decode_gsm7(hex_string):
    """GSM7解码"""
    gsm7_table = (
        "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./"
        "0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
    )
    try:
        hex_string = hex_string.strip().replace(' ', '')
        bytes_data = bytes.fromhex(hex_string)
        # 7-bit unpacking
        result = []
        bit_buffer = 0
        bit_count = 0
        for byte in bytes_data:
            bit_buffer |= byte << bit_count
            bit_count += 8
            while bit_count >= 7:
                char_code = bit_buffer & 0x7F
                bit_buffer >>= 7
                bit_count -= 7
                if char_code == 0x1B:
                    # ESC sequence - skip for simplicity
                    continue
                if char_code < len(gsm7_table):
                    result.append(gsm7_table[char_code])
                else:
                    result.append('?')
        return ''.join(result)
    except Exception as e:
        logger.warning(f"GSM7解码失败: {e}")
        return hex_string


def decode_pdu_content(pdu_text, encoding='GSM7'):
    """根据编码类型解码PDU短信内容"""
    if not pdu_text:
        return ''
    if encoding.upper() == 'UCS2':
        return decode_ucs2(pdu_text)
    elif encoding.upper() == 'GSM7':
        return decode_gsm7(pdu_text)
    else:
        return pdu_text


def parse_cmt(line):
    """解析 +CMT: 短信通知行
    格式: +CMT: "phone",,"date" 或 +CMT: "phone","name","date"
    """
    try:
        # Match +CMT: "phone",...  ,"date"
        match = re.match(r'\+CMT:\s*"([^"]*)",?.*,"([^"]*)"\s*$', line)
        if match:
            return match.group(1), match.group(2)
        # Alternative format
        match = re.match(r'\+CMT:\s*(\d+),\d+', line)
        if match:
            return match.group(1), ''
    except Exception as e:
        logger.warning(f"解析CMT行失败 '{line}': {e}")
    return None, None


def sanitize_input(text):
    """清理用户输入"""
    if not text:
        return ''
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(text))


def format_bytes(size_bytes):
    """格式化字节大小"""
    if size_bytes == 0:
        return '0 B'
    units = ['B', 'KB', 'MB', 'GB']
    i = 0
    size = float(size_bytes)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f'{size:.2f} {units[i]}'


def csq_to_rssi(csq):
    """CSQ值转RSSI (dBm)"""
    if csq is None or csq == 99:
        return None
    if csq == 0:
        return -113
    return -113 + 2 * csq


def csq_to_percent(csq):
    """CSQ值转百分比"""
    if csq is None or csq == 99:
        return 0
    return min(100, int(csq / 31 * 100))


def safe_filename(filename):
    """清理文件名，移除不安全字符"""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


def parse_sms_time(time_str):
    """解析短信时间字符串为datetime对象"""
    if not time_str:
        return datetime.now()
    # 格式: "yy/MM/dd,HH:mm:ss±zz" 如 "23/06/27,18:20:35+32"
    try:
        # 去掉引号和空格
        time_str = time_str.strip('"').strip()
        # 提取时区
        tz_match = re.search(r'([+-]\d{2})$', time_str)
        tz_offset = 0
        if tz_match:
            tz_offset_str = tz_match.group(1)
            tz_offset = int(tz_offset_str) // 4  # quarter hours to hours
            time_str = time_str[:-3]
        dt = datetime.strptime(time_str, '%y/%m/%d,%H:%M:%S')
        return dt
    except (ValueError, IndexError) as e:
        logger.warning(f"解析短信时间失败 '{time_str}': {e}")
        return datetime.now()
