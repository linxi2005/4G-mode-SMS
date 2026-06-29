# web/notifier.py
"""WebSocket通知模块"""
import logging

logger = logging.getLogger(__name__)

# Flask-SocketIO 可选导入
try:
    from flask_socketio import SocketIO
    socketio = SocketIO(cors_allowed_origins='*', async_mode='threading')
    HAS_SOCKETIO = True
except ImportError:
    socketio = None  # type: ignore
    HAS_SOCKETIO = False
    logger.info("flask-socketio 未安装，WebSocket 功能不可用（短信/邮件核心功能正常）")


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
        if HAS_SOCKETIO and socketio:
            try:
                socketio.emit('new_sms', sms_data)
            except Exception:
                pass

    def notify_modem_status(self, modem_data):
        """通知模块状态变化"""
        if HAS_SOCKETIO and socketio:
            try:
                socketio.emit('modem_status', modem_data)
            except Exception:
                pass

    def notify_system_stats(self, stats):
        """通知系统状态"""
        if HAS_SOCKETIO and socketio:
            try:
                socketio.emit('system_stats', stats)
            except Exception:
                pass

    def notify_log(self, level, message):
        """通知日志"""
        if HAS_SOCKETIO and socketio:
            try:
                socketio.emit('log_entry', {'level': level, 'message': message})
            except Exception:
                pass


notifier = Notifier()
