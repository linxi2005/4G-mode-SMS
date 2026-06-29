# database/models.py
"""SQLAlchemy ORM 数据模型定义"""
from datetime import datetime, timezone
from .database import db


class SMS(db.Model):
    """短信记录表"""
    __tablename__ = 'sms'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    module_id = db.Column(db.String(36), nullable=True, index=True)
    modem_name = db.Column(db.String(128), nullable=True)
    modem_model = db.Column(db.String(64), nullable=True)
    imei = db.Column(db.String(32), nullable=True, index=True)
    sms_index = db.Column(db.Integer, nullable=True)
    phone = db.Column(db.String(32), nullable=False, index=True)
    receive_time = db.Column(db.DateTime, nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    encoding = db.Column(db.String(16), default='GSM7')
    is_read = db.Column(db.Boolean, default=False)
    forwarded = db.Column(db.Boolean, default=False, index=True)
    forward_count = db.Column(db.Integer, default=0)
    last_forward_time = db.Column(db.DateTime, nullable=True)
    sync_time = db.Column(db.DateTime, nullable=True)
    hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'module_id': self.module_id,
            'modem_name': self.modem_name,
            'modem_model': self.modem_model,
            'imei': self.imei,
            'sms_index': self.sms_index,
            'phone': self.phone,
            'receive_time': self.receive_time.isoformat() if self.receive_time else None,
            'content': self.content,
            'encoding': self.encoding,
            'is_read': self.is_read,
            'forwarded': self.forwarded,
            'forward_count': self.forward_count,
            'last_forward_time': self.last_forward_time.isoformat() if self.last_forward_time else None,
            'sync_time': self.sync_time.isoformat() if self.sync_time else None,
            'hash': self.hash,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ModemInfo(db.Model):
    """4G模块信息表"""
    __tablename__ = 'modem_info'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    module_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=True)
    port = db.Column(db.String(64), unique=True, nullable=False)
    baudrate = db.Column(db.Integer, default=115200)
    brand = db.Column(db.String(32), nullable=True)
    model = db.Column(db.String(64), nullable=True)
    firmware_version = db.Column(db.String(64), nullable=True)
    imei = db.Column(db.String(32), nullable=True, index=True)
    iccid = db.Column(db.String(32), nullable=True)
    imsi = db.Column(db.String(32), nullable=True)
    network_type = db.Column(db.String(16), nullable=True)
    operator = db.Column(db.String(64), nullable=True)
    is_online = db.Column(db.Boolean, default=False)
    is_roaming = db.Column(db.Boolean, default=False)
    signal_csq = db.Column(db.Integer, nullable=True)
    signal_rssi = db.Column(db.Integer, nullable=True)
    signal_percent = db.Column(db.Integer, nullable=True)
    sim_status = db.Column(db.String(32), nullable=True)
    registration_status = db.Column(db.String(32), nullable=True)
    enabled = db.Column(db.Boolean, default=True)
    last_communication = db.Column(db.DateTime, nullable=True)
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'module_id': self.module_id,
            'name': self.name,
            'port': self.port,
            'baudrate': self.baudrate,
            'brand': self.brand,
            'model': self.model,
            'firmware_version': self.firmware_version,
            'imei': self.imei,
            'iccid': self.iccid,
            'imsi': self.imsi,
            'network_type': self.network_type,
            'operator': self.operator,
            'is_online': self.is_online,
            'is_roaming': self.is_roaming,
            'signal_csq': self.signal_csq,
            'signal_rssi': self.signal_rssi,
            'signal_percent': self.signal_percent,
            'sim_status': self.sim_status,
            'registration_status': self.registration_status,
            'enabled': self.enabled,
            'last_communication': self.last_communication.isoformat() if self.last_communication else None,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
        }


class MailLog(db.Model):
    """邮件发送日志表"""
    __tablename__ = 'mail_log'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sms_id = db.Column(db.Integer, db.ForeignKey('sms.id', ondelete='SET NULL'), nullable=True, index=True)
    recipient = db.Column(db.String(256), nullable=False)
    success = db.Column(db.Boolean, default=False)
    error_message = db.Column(db.Text, nullable=True)
    sent_time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    sms = db.relationship('SMS', backref=db.backref('mail_logs', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'sms_id': self.sms_id,
            'recipient': self.recipient,
            'success': self.success,
            'error_message': self.error_message,
            'sent_time': self.sent_time.isoformat() if self.sent_time else None,
        }


class ATCommandHistory(db.Model):
    """AT指令历史表"""
    __tablename__ = 'at_history'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    module_id = db.Column(db.String(36), nullable=False, index=True)
    command = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=True)
    success = db.Column(db.Boolean, default=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    executed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'module_id': self.module_id,
            'command': self.command,
            'response': self.response,
            'success': self.success,
            'duration_ms': self.duration_ms,
            'executed_at': self.executed_at.isoformat() if self.executed_at else None,
        }


class SystemLog(db.Model):
    """系统日志表"""
    __tablename__ = 'system_log'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    level = db.Column(db.String(16), nullable=False, index=True)
    module = db.Column(db.String(64), nullable=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'level': self.level,
            'module': self.module,
            'message': self.message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
