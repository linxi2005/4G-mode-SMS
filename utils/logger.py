# utils/logger.py
"""日志系统配置"""
import os
import logging
import logging.handlers


class DBLogHandler(logging.Handler):
    """将日志同时写入数据库"""

    def __init__(self, app=None):
        super().__init__()
        self.app = app

    def emit(self, record):
        if self.app is None:
            return
        try:
            from database.models import SystemLog
            from database.database import db
            with self.app.app_context():
                log_entry = SystemLog(
                    level=record.levelname,
                    module=record.name,
                    message=self.format(record),
                )
                db.session.add(log_entry)
                db.session.commit()
        except Exception:
            pass


def setup_logger(app=None, config_manager=None):
    """配置日志系统"""
    log_level = logging.INFO
    log_dir = 'data/log'
    if config_manager:
        level_str = config_manager.log_level
        log_level = getattr(logging, level_str.upper(), logging.INFO)

    os.makedirs(log_dir, exist_ok=True)

    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除已有handlers
    root_logger.handlers.clear()

    # 控制台
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(fmt)
    root_logger.addHandler(console_handler)

    # 文件日志 (轮转)
    max_bytes = config_manager.get('logging.max_size_mb', 10) * 1024 * 1024 if config_manager else 10 * 1024 * 1024
    backup_count = config_manager.get('logging.backup_count', 5) if config_manager else 5

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'system.log'),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    # 数据库日志处理器
    if app:
        db_handler = DBLogHandler(app)
        db_handler.setLevel(logging.WARNING)
        db_handler.setFormatter(fmt)
        root_logger.addHandler(db_handler)

    return root_logger
