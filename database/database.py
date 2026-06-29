# database/database.py
"""数据库管理模块 - 提供初始化、连接管理和迁移支持"""
import os
import logging
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

logger = logging.getLogger(__name__)

db = SQLAlchemy()


class DatabaseManager:
    """数据库管理器 - 封装所有数据库操作"""

    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)

    def init_app(self, app):
        """初始化Flask应用数据库"""
        db_path = app.config.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///data/sms.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = db_path
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 3600,
        }
        db.init_app(app)
        self.app = app

    def create_all(self):
        """创建所有数据表"""
        with self.app.app_context():
            db.create_all()
            logger.info("数据库表创建完成")

    def get_db_size(self):
        """获取数据库文件大小"""
        db_uri = self.app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if db_uri.startswith('sqlite:///'):
            db_file = db_uri.replace('sqlite:///', '')
            if os.path.exists(db_file):
                return os.path.getsize(db_file)
        return 0

    def vacuum(self):
        """优化数据库"""
        with self.app.app_context():
            db.session.execute(text('VACUUM'))
            db.session.commit()
            logger.info("数据库VACUUM完成")

    def check_integrity(self):
        """检查数据库完整性"""
        with self.app.app_context():
            result = db.session.execute(text('PRAGMA integrity_check'))
            row = result.fetchone()
            return row[0] == 'ok' if row else False

    def get_table_counts(self):
        """获取各表记录数"""
        with self.app.app_context():
            return {
                'sms': SMS.query.count(),
                'modem': ModemInfo.query.count(),
                'mail_log': MailLog.query.count(),
                'at_history': ATCommandHistory.query.count(),
                'system_log': SystemLog.query.count(),
            }

    def get_mail_stats(self):
        """获取邮件发送统计"""
        with self.app.app_context():
            total = MailLog.query.count()
            success = MailLog.query.filter_by(success=True).count()
            failed = total - success
            return {'total': total, 'success': success, 'failed': failed}

    def cleanup_old_sms(self, days):
        """删除超过指定天数的短信"""
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self.app.app_context():
            deleted = SMS.query.filter(SMS.receive_time < cutoff).delete()
            db.session.commit()
            logger.info(f"清理了 {deleted} 条旧短信")
            return deleted

    def cleanup_by_count(self, max_count):
        """按数量清理最早的短信"""
        with self.app.app_context():
            total = SMS.query.count()
            if total > max_count:
                to_delete = total - max_count
                subquery = SMS.query.order_by(SMS.receive_time.asc()).limit(to_delete).subquery()
                deleted = SMS.query.filter(SMS.id == subquery.c.id).delete(synchronize_session='fetch')
                db.session.commit()
                logger.info(f"按数量清理了 {deleted} 条旧短信")
                return deleted
        return 0

    def backup_database(self, backup_path=None):
        """备份数据库"""
        import shutil
        db_uri = self.app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if not db_uri.startswith('sqlite:///'):
            raise ValueError("仅支持SQLite备份")
        db_file = db_uri.replace('sqlite:///', '')
        if not backup_path:
            backup_path = db_file + '.backup'
        shutil.copy2(db_file, backup_path)
        logger.info(f"数据库已备份至: {backup_path}")
        return backup_path

    def restore_database(self, backup_path):
        """从备份恢复数据库"""
        import shutil
        db_uri = self.app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if not db_uri.startswith('sqlite:///'):
            raise ValueError("仅支持SQLite恢复")
        db_file = db_uri.replace('sqlite:///', '')
        shutil.copy2(backup_path, db_file)
        logger.info(f"数据库已从 {backup_path} 恢复")


def init_db(app):
    """便捷初始化函数"""
    manager = DatabaseManager(app)
    manager.create_all()
    return manager


# 为避免循环导入, models 中的类在此处延迟引用
from .models import SMS, ModemInfo, MailLog, ATCommandHistory, SystemLog  # noqa: E402, F401
