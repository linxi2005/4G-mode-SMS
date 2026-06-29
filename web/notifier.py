# web/notifier.py
"""WebSocket通知模块"""
import logging
from flask_socketio import SocketIO

logger = logging.getLogger(__name__)

socketio = SocketIO(cors_allowed_origins='*', async_mode='threading')


class Notifier:
    """实时通知管理器"""

    def __init__(self):
        self._clients = set()

    def register_client(self, sid):
        self._clients.add(sid)

    def unregister_client(self, sid):
        self._clients.discard(sid)

    def notify_new_sms(self, sms_data):
        """通知新短信"""
        socketio.emit('new_sms', sms_data)

    def notify_modem_status(self, modem_data):
        """通知模块状态变化"""
        socketio.emit('modem_status', modem_data)

    def notify_system_stats(self, stats):
        """通知系统状态"""
        socketio.emit('system_stats', stats)

    def notify_log(self, level, message):
        """通知日志"""
        socketio.emit('log_entry', {'level': level, 'message': message})


notifier = Notifier()
