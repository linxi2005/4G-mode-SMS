# utils/config_manager.py
"""配置管理模块 - 负责系统配置和邮件配置的读写"""
import os
import json
import logging
import threading
from copy import deepcopy

logger = logging.getLogger(__name__)


class ConfigManager:
    """线程安全的配置管理器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_dir='config'):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self.config_dir = config_dir
        self._config_lock = threading.Lock()
        self._config = {}
        self._mail_config = {}
        self._load_all()

    def _get_path(self, filename):
        return os.path.join(self.config_dir, filename)

    def _load_json(self, filename):
        """安全加载JSON文件"""
        path = self._get_path(filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"配置文件不存在: {path}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"配置文件JSON解析错误 {path}: {e}")
            return {}

    def _save_json(self, filename, data):
        """安全保存JSON文件"""
        path = self._get_path(filename)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp_path = path + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
            try:
                os.chmod(path, 0o600)
            except (OSError, PermissionError):
                pass
            logger.debug(f"配置文件已保存: {path}")
        except Exception as e:
            logger.error(f"保存配置文件失败 {path}: {e}")

    def _load_all(self):
        """加载所有配置"""
        self._config = self._load_json('config.json')
        self._mail_config = self._load_json('mail.json')

    def reload(self):
        """重新加载所有配置"""
        self._load_all()
        logger.info("配置已重新加载")

    # ---- 系统配置 ----
    @property
    def config(self):
        return deepcopy(self._config)

    def get(self, key, default=None):
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key, value):
        """设置配置项并保存"""
        with self._config_lock:
            keys = key.split('.')
            target = self._config
            for k in keys[:-1]:
                if k not in target:
                    target[k] = {}
                target = target[k]
            target[keys[-1]] = value
            self._save_json('config.json', self._config)

    def update_section(self, section, data):
        """更新某个配置节"""
        with self._config_lock:
            if section not in self._config:
                self._config[section] = {}
            self._config[section].update(data)
            self._save_json('config.json', self._config)

    # ---- 邮件配置 ----
    @property
    def mail_config(self):
        return deepcopy(self._mail_config)

    def get_mail(self, key, default=None):
        return self._mail_config.get(key, default)

    def set_mail(self, key, value):
        """设置邮件配置项并保存"""
        with self._config_lock:
            self._mail_config[key] = value
            self._save_json('mail.json', self._mail_config)

    def update_mail_config(self, data):
        """更新整个邮件配置"""
        with self._config_lock:
            self._mail_config.update(data)
            self._save_json('mail.json', self._mail_config)

    # ---- 便捷属性 ----
    @property
    def app_name(self):
        return self._config.get('app', {}).get('name', '4G SMS System')

    @property
    def app_version(self):
        return self._config.get('app', {}).get('version', '1.0.0')

    @property
    def debug(self):
        return self._config.get('app', {}).get('debug', False)

    @property
    def log_level(self):
        return self._config.get('logging', {}).get('level', 'INFO')

    @property
    def sms_sync_interval(self):
        return self._config.get('sms', {}).get('sync_interval', 30)

    @property
    def page_size(self):
        return self._config.get('sms', {}).get('page_size', 20)

    @property
    def serial_config(self):
        return deepcopy(self._config.get('serial', {}))

    def export_config(self):
        """导出所有配置"""
        return {
            'config': deepcopy(self._config),
            'mail': deepcopy(self._mail_config),
        }

    def import_config(self, data):
        """导入配置"""
        with self._config_lock:
            if 'config' in data:
                self._config.update(data['config'])
                self._save_json('config.json', self._config)
            if 'mail' in data:
                self._mail_config.update(data['mail'])
                self._save_json('mail.json', self._mail_config)
        self._load_all()
        logger.info("配置导入完成")
