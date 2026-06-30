#!/usr/bin/env python3
# app.py - 4G短信转发系统主应用
"""4G短信转发系统 - 主应用入口

支持平台: Linux (amd64/arm64/armv7), Windows (amd64)
Python: 3.7+
"""
import os
import sys
import json
import time
import signal
import hashlib
import logging
import platform
import threading
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify, redirect,
    url_for, session, send_file, Response
)

# psutil 在 Windows/armv7 上可能有问题，做兼容处理
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    psutil = None

# Flask-SocketIO 可选（ARM/Linux 环境可能装不上）
try:
    from flask_socketio import SocketIO  # noqa: F811
    HAS_SOCKETIO = True
except ImportError:
    HAS_SOCKETIO = False
    SocketIO = None  # type: ignore

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.config_manager import ConfigManager
from utils.logger import setup_logger
from utils.helpers import format_bytes
from database.database import DatabaseManager, db, init_db
from database.models import SMS, ModemInfo, MailLog, ATCommandHistory, SystemLog
from modem.manager import ModemManager
from web.sms_engine import SMSEngine
from web.mail_forwarder import MailForwarder
from web.notifier import socketio, notifier

# ---- 初始化 ----

config_manager = ConfigManager(config_dir='config')
logger = None  # 稍后初始化

# 创建 Flask 应用
app = Flask(__name__)
app.config['SECRET_KEY'] = config_manager.get('app.secret_key', 'dev-secret-change-me')
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = config_manager.get('app.session_timeout', 3600)

# 配置数据库URI
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'sms.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 3600,
}

# 初始化数据库（只初始化一次）
# DatabaseManager 构造函数不会再调用 db.init_app，避免重复注册
db_manager = DatabaseManager()
db_manager.init_app(app)

# 初始化日志（在数据库之后）
logger = setup_logger(app, config_manager)

# 初始化 SocketIO（如果可用）
if HAS_SOCKETIO:
    try:
        socketio.init_app(app, async_mode='threading', cors_allowed_origins='*')
        logger.info("WebSocket 支持已启用")
    except Exception as e:
        logger.warning(f"WebSocket 初始化失败（不影响核心功能）: {e}")
        HAS_SOCKETIO = False
else:
    logger.info("flask-socketio 未安装，WebSocket 实时推送不可用（短信/邮件功能正常）")

# 数据库会话工厂
def get_db_session():
    return db.session

# 初始化核心组件
modem_manager = ModemManager(config_manager, get_db_session)
sms_engine = SMSEngine(modem_manager, config_manager, get_db_session)
mail_forwarder = MailForwarder(config_manager, get_db_session)

# 注册转发回调
sms_engine.add_forward_callback(mail_forwarder.forward_sms)

# 全局启动时间
START_TIME = datetime.now(timezone.utc)


# ---- 认证装饰器 ----

def login_required(f):
    """登录认证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not config_manager.get('web_auth.enabled', True):
            return f(*args, **kwargs)
        if 'logged_in' in session and session.get('logged_in'):
            return f(*args, **kwargs)
        if request.path.startswith('/api/'):
            return jsonify({'error': '未授权', 'code': 401}), 401
        return redirect(url_for('login'))
    return decorated


def api_error_handler(f):
    """API异常处理装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"API异常: {e}")
            return jsonify({'error': str(e), 'code': 500}), 500
    return decorated


# ---- 首页/登录 ----

@app.route('/login', methods=['GET', 'POST'])
def login():
    if not config_manager.get('web_auth.enabled', True):
        session['logged_in'] = True
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        config_username = config_manager.get('web_auth.username', 'admin')
        config_password_hash = config_manager.get('web_auth.password_hash', '')

        # 首次使用默认密码 admin/admin
        if config_password_hash == 'pbkdf2:sha256:600000$salt$hash_placeholder':
            if username == 'admin' and password == 'admin':
                session['logged_in'] = True
                return redirect(url_for('index'))
        else:
            # TODO: 实现正确的密码哈希验证
            if username == config_username and password == password:
                session['logged_in'] = True
                return redirect(url_for('index'))

        return render_template('login.html', error='用户名或密码错误')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ---- 首页 ----

@app.route('/')
@login_required
def index():
    """首页 - 仪表盘"""
    # 系统信息
    modem_stats = modem_manager.get_statistics()
    sms_stats = sms_engine.get_statistics()

    # 系统资源（兼容无 psutil 的环境）
    if HAS_PSUTIL:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        stats = {
            'cpu': cpu_percent,
            'memory_percent': memory.percent,
            'memory_used': format_bytes(memory.used),
            'memory_total': format_bytes(memory.total),
            'disk_percent': disk.percent,
            'disk_used': format_bytes(disk.used),
            'disk_total': format_bytes(disk.total),
        }
    else:
        stats = {
            'cpu': 'N/A',
            'memory_percent': 'N/A',
            'memory_used': 'N/A',
            'memory_total': 'N/A',
            'disk_percent': 'N/A',
            'disk_used': 'N/A',
            'disk_total': 'N/A',
        }

    # 运行时间
    uptime = datetime.now(timezone.utc) - START_TIME
    uptime_str = str(uptime).split('.')[0]

    stats['uptime'] = uptime_str
    stats['version'] = config_manager.app_version

    return render_template('index.html',
                           modems=modem_manager.get_all_modems(),
                           modem_stats=modem_stats,
                           sms_stats=sms_stats,
                           stats=stats)


# ---- 短信记录 ----

@app.route('/sms')
@login_required
def sms_page():
    """短信记录页面"""
    return render_template('sms.html')


@app.route('/api/sms')
@login_required
@api_error_handler
def api_sms_list():
    """API: 获取短信列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', config_manager.page_size, type=int)
    phone = request.args.get('phone', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    module_id = request.args.get('module_id', '')
    forwarded = request.args.get('forwarded', '')
    is_read = request.args.get('is_read', '')
    search = request.args.get('search', '')

    # 转换参数
    if forwarded != '':
        forwarded = forwarded.lower() == 'true'
    else:
        forwarded = None

    if is_read != '':
        is_read = is_read.lower() == 'true'
    else:
        is_read = None

    from datetime import datetime as dt
    if date_from:
        date_from = dt.fromisoformat(date_from)
    if date_to:
        date_to = dt.fromisoformat(date_to)

    result = sms_engine.get_sms_list(
        page=page, per_page=per_page,
        phone=phone or None,
        date_from=date_from,
        date_to=date_to,
        module_id=module_id or None,
        forwarded=forwarded,
        is_read=is_read,
        search=search or None,
    )
    return jsonify(result)


@app.route('/api/sms/<int:sms_id>/resend', methods=['POST'])
@login_required
@api_error_handler
def api_sms_resend(sms_id):
    """API: 重新发送邮件"""
    success = sms_engine.resend_mail(sms_id)
    return jsonify({'success': success})


@app.route('/api/sms/batch', methods=['POST'])
@login_required
@api_error_handler
def api_sms_batch():
    """API: 批量操作短信"""
    data = request.get_json()
    ids = data.get('ids', [])
    action = data.get('action', '')
    if not ids or not action:
        return jsonify({'success': False, 'error': '参数错误'})

    count = sms_engine.batch_action(ids, action)
    return jsonify({'success': True, 'count': count})


@app.route('/api/sms/export')
@login_required
@api_error_handler
def api_sms_export():
    """API: 导出短信"""
    fmt = request.args.get('format', 'json')
    phone = request.args.get('phone', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    module_id = request.args.get('module_id', '')

    from datetime import datetime as dt
    if date_from:
        date_from = dt.fromisoformat(date_from)
    if date_to:
        date_to = dt.fromisoformat(date_to)

    content, mime = sms_engine.export_sms(
        format=fmt,
        phone=phone or None,
        date_from=date_from,
        date_to=date_to,
        module_id=module_id or None,
    )

    if fmt == 'csv':
        return Response(
            content,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=sms_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'}
        )
    return Response(
        content,
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=sms_export.json'}
    )


# ---- 发送短信 ----

@app.route('/send')
@login_required
def send_page():
    """发送短信页面"""
    return render_template('send.html', modems=modem_manager.get_all_modems())


@app.route('/api/send', methods=['POST'])
@login_required
@api_error_handler
def api_send_sms():
    """API: 发送短信"""
    data = request.get_json()
    module_id = data.get('module_id', '')
    phone = data.get('phone', '')
    content = data.get('content', '')

    if not module_id or not phone or not content:
        return jsonify({'success': False, 'error': '参数不完整'})

    result = modem_manager.send_sms(module_id, phone, content)
    return jsonify(result)


# ---- 邮件配置 ----

@app.route('/mail')
@login_required
def mail_page():
    """邮件配置页面"""
    return render_template('mail.html', config=config_manager.mail_config)


@app.route('/api/mail', methods=['GET'])
@login_required
@api_error_handler
def api_get_mail():
    """API: 获取邮件配置"""
    return jsonify(config_manager.mail_config)


@app.route('/api/mail', methods=['POST'])
@login_required
@api_error_handler
def api_save_mail():
    """API: 保存邮件配置"""
    data = request.get_json()
    config_manager.update_mail_config(data)
    return jsonify({'success': True, 'message': '配置已保存'})


@app.route('/api/mail/test', methods=['POST'])
@login_required
@api_error_handler
def api_test_mail():
    """API: 测试邮件发送"""
    data = request.get_json() or {}
    recipient = data.get('recipient', '')
    success, error = mail_forwarder.test_send(recipient or None)
    return jsonify({'success': success, 'error': error})


# ---- 系统设置 ----

@app.route('/settings')
@login_required
def settings_page():
    """系统设置页面"""
    cfg = config_manager.config
    # 确保顶层 key 存在，防止模板渲染崩溃
    for key in ['serial', 'sms', 'logging']:
        if key not in cfg:
            cfg[key] = {}
    return render_template('settings.html', config=cfg)


@app.route('/api/settings', methods=['GET'])
@login_required
@api_error_handler
def api_get_settings():
    """API: 获取系统配置"""
    return jsonify(config_manager.config)


@app.route('/api/settings', methods=['POST'])
@login_required
@api_error_handler
def api_save_settings():
    """API: 保存系统配置"""
    data = request.get_json()
    section = data.get('section', '')
    values = data.get('values', {})

    if not section:
        return jsonify({'success': False, 'error': '未指定配置节'})

    config_manager.update_section(section, values)
    # 重新加载配置
    config_manager.reload()
    return jsonify({'success': True, 'message': '配置已保存'})


# ---- 模块管理 ----

@app.route('/modems')
@login_required
def modems_page():
    """模块管理页面"""
    return render_template('modems.html')


@app.route('/api/modems')
@login_required
@api_error_handler
def api_get_modems():
    """API: 获取所有模块"""
    modems = modem_manager.get_all_modems()
    return jsonify([m.to_dict() for m in modems.values()])


@app.route('/api/modems/<module_id>/reconnect', methods=['POST'])
@login_required
@api_error_handler
def api_reconnect_modem(module_id):
    """API: 重连模块"""
    success = modem_manager.reconnect_modem(module_id)
    return jsonify({'success': success})


@app.route('/api/modems/<module_id>/restart', methods=['POST'])
@login_required
@api_error_handler
def api_restart_modem(module_id):
    """API: 软重启模块 (AT+CFUN=1,1)"""
    result = modem_manager.restart_modem(module_id)
    return jsonify(result)


@app.route('/api/modems/<module_id>', methods=['PUT'])
@login_required
@api_error_handler
def api_update_modem(module_id):
    """API: 更新模块信息"""
    data = request.get_json()
    name = data.get('name', '')
    if name:
        modem_manager.update_modem_name(module_id, name)
    return jsonify({'success': True})


@app.route('/api/modems/<module_id>', methods=['DELETE'])
@login_required
@api_error_handler
def api_delete_modem(module_id):
    """API: 移除/禁用模块"""
    modem_manager.disable_modem(module_id)
    return jsonify({'success': True})


@app.route('/api/modems/add', methods=['POST'])
@login_required
@api_error_handler
def api_add_modem():
    """API: 手动添加模块"""
    data = request.get_json()
    port = data.get('port', '')
    baudrate = data.get('baudrate', 115200)
    name = data.get('name', '')

    if not port:
        return jsonify({'success': False, 'error': '串口路径不能为空'})

    # Windows 下路径处理: COM3, COM10 等
    # Linux 下: /dev/ttyUSB2, /dev/ttyACM0 等
    instance = modem_manager.try_connect_port(port, baudrate)
    if instance:
        if name:
            modem_manager.update_modem_name(instance.module_id, name)
        return jsonify({'success': True, 'module': instance.to_dict()})
    else:
        return jsonify({'success': False, 'error': f'无法连接端口 {port}，请检查串口是否存在且为AT口'})


@app.route('/api/modems/discover', methods=['POST'])
@login_required
@api_error_handler
def api_discover_modems():
    """API: 自动发现并连接模块"""
    instances = modem_manager.auto_discover()
    return jsonify([m.to_dict() for m in instances])


# ---- AT调试 ----

@app.route('/at')
@login_required
def at_page():
    """AT调试页面"""
    return render_template('at.html', modems=modem_manager.get_all_modems())


@app.route('/api/at', methods=['POST'])
@login_required
@api_error_handler
def api_exec_at():
    """API: 执行AT指令"""
    data = request.get_json()
    module_id = data.get('module_id', '')
    command = data.get('command', '')

    if not module_id or not command:
        return jsonify({'success': False, 'error': '参数不完整'})

    # 安全检查：防止危险AT指令（但允许通过 /api/modems/<id>/restart 发起的 CFUN=1,1）
    dangerous_commands = ['AT+CFUN=0', 'AT+CFUN=4', 'AT+QPOWD']
    if any(command.upper().replace(' ', '').startswith(d.replace(' ', '')) for d in dangerous_commands):
        return jsonify({'success': False, 'error': '该指令已被限制执行（可能导致模块关机或重启）'})

    start_time = time.time()
    result = modem_manager.exec_at(module_id, command, timeout=10)
    duration_ms = int((time.time() - start_time) * 1000)

    # 保存到AT历史
    try:
        history = ATCommandHistory(
            module_id=module_id,
            command=command,
            response=result.get('response', ''),
            success=result.get('success', False),
            duration_ms=duration_ms,
        )
        db.session.add(history)
        db.session.commit()
    except Exception as e:
        logger.error(f"保存AT历史失败: {e}")

    result['duration_ms'] = duration_ms
    return jsonify(result)


@app.route('/api/at/history')
@login_required
@api_error_handler
def api_at_history():
    """API: 获取AT历史"""
    module_id = request.args.get('module_id', '')
    limit = request.args.get('limit', 20, type=int)

    query = ATCommandHistory.query
    if module_id:
        query = query.filter_by(module_id=module_id)

    records = query.order_by(ATCommandHistory.executed_at.desc()).limit(limit).all()
    return jsonify([r.to_dict() for r in records])


# ---- 日志 ----

@app.route('/logs')
@login_required
def logs_page():
    """日志页面"""
    return render_template('logs.html')


@app.route('/api/logs')
@login_required
@api_error_handler
def api_logs():
    """API: 获取日志"""
    level = request.args.get('level', '')
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = SystemLog.query
    if level:
        query = query.filter_by(level=level.upper())
    if search:
        query = query.filter(
            (SystemLog.message.contains(search)) |
            (SystemLog.module.contains(search))
        )

    total = query.count()
    logs = query.order_by(SystemLog.created_at.desc()) \
        .offset((page - 1) * per_page) \
        .limit(per_page) \
        .all()

    return jsonify({
        'items': [l.to_dict() for l in logs],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
    })


@app.route('/api/logs/clear', methods=['POST'])
@login_required
@api_error_handler
def api_clear_logs():
    """API: 清空日志"""
    try:
        SystemLog.query.delete()
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/logs/download')
@login_required
@api_error_handler
def api_download_logs():
    """API: 下载日志文件"""
    log_path = os.path.join('data', 'log', 'system.log')
    if os.path.exists(log_path):
        return send_file(log_path, as_attachment=True, download_name='system.log')
    return jsonify({'error': '日志文件不存在'}), 404


# ---- 数据库维护 ----

@app.route('/database')
@login_required
def database_page():
    """数据库维护页面"""
    db_size = db_manager.get_db_size()
    counts = db_manager.get_table_counts()
    mail_stats = db_manager.get_mail_stats()
    integrity = db_manager.check_integrity()
    return render_template('database.html',
                           db_size=format_bytes(db_size),
                           counts=counts,
                           mail_stats=mail_stats,
                           integrity=integrity)


@app.route('/api/database/vacuum', methods=['POST'])
@login_required
@api_error_handler
def api_vacuum():
    """API: 优化数据库"""
    db_manager.vacuum()
    return jsonify({'success': True})


@app.route('/api/database/check', methods=['POST'])
@login_required
@api_error_handler
def api_check_integrity():
    """API: 检查数据库完整性"""
    ok = db_manager.check_integrity()
    return jsonify({'integrity': ok})


@app.route('/api/database/cleanup', methods=['POST'])
@login_required
@api_error_handler
def api_cleanup():
    """API: 清理旧数据"""
    data = request.get_json()
    days = data.get('days', 30)
    max_count = data.get('max_count', 0)

    deleted = 0
    if days and days > 0:
        deleted += db_manager.cleanup_old_sms(days)
    if max_count and max_count > 0:
        deleted += db_manager.cleanup_by_count(max_count)

    return jsonify({'success': True, 'deleted': deleted})


@app.route('/api/database/backup', methods=['POST'])
@login_required
@api_error_handler
def api_backup():
    """API: 备份数据库"""
    backup_path = db_manager.backup_database()
    return jsonify({'success': True, 'path': backup_path})


@app.route('/api/database/restore', methods=['POST'])
@login_required
@api_error_handler
def api_restore():
    """API: 恢复数据库"""
    data = request.get_json()
    backup_path = data.get('path', '')
    if not backup_path or not os.path.exists(backup_path):
        return jsonify({'success': False, 'error': '备份文件不存在'})
    db_manager.restore_database(backup_path)
    return jsonify({'success': True})


@app.route('/api/database/export')
@login_required
@api_error_handler
def api_export_database():
    """API: 导出数据库文件"""
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if db_uri.startswith('sqlite:///'):
        db_file = db_uri.replace('sqlite:///', '')
        if os.path.exists(db_file):
            return send_file(
                db_file,
                as_attachment=True,
                download_name=f'sms_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db',
                mimetype='application/octet-stream'
            )
    return jsonify({'error': '数据库文件不存在'}), 404


@app.route('/api/database/import', methods=['POST'])
@login_required
@api_error_handler
def api_import_database():
    """API: 导入数据库文件"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '未上传文件'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'})

    if not file.filename.endswith(('.db', '.sqlite', '.bak')):
        return jsonify({'success': False, 'error': '文件格式不正确，仅支持 .db/.sqlite/.bak 文件'})

    try:
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if not db_uri.startswith('sqlite:///'):
            return jsonify({'success': False, 'error': '当前数据库不是SQLite'})

        db_file = db_uri.replace('sqlite:///', '')

        # 先备份当前数据库
        backup_path = db_manager.backup_database()

        # 写入新文件
        file.save(db_file)

        # 验证完整性
        if not db_manager.check_integrity():
            # 恢复备份
            if backup_path and os.path.exists(backup_path):
                import shutil
                shutil.copy2(backup_path, db_file)
            return jsonify({'success': False, 'error': '导入的数据库文件损坏（完整性检查失败），已恢复原数据库'})

        logger.info(f"数据库已从上传文件导入: {file.filename}")
        return jsonify({'success': True, 'message': '数据库导入成功'})
    except Exception as e:
        logger.error(f"导入数据库失败: {e}")
        return jsonify({'success': False, 'error': str(e)})


# ---- 系统统计 ----

@app.route('/api/stats')
@login_required
@api_error_handler
def api_stats():
    """API: 获取系统统计"""
    if HAS_PSUTIL:
        cpu = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        mem_used = format_bytes(memory.used)
        mem_total = format_bytes(memory.total)
        mem_percent = memory.percent
        disk_used = format_bytes(disk.used)
        disk_total = format_bytes(disk.total)
        disk_percent = disk.percent
    else:
        cpu = 0
        mem_used = 'N/A'
        mem_total = 'N/A'
        mem_percent = 0
        disk_used = 'N/A'
        disk_total = 'N/A'
        disk_percent = 0

    uptime = datetime.now(timezone.utc) - START_TIME

    return jsonify({
        'cpu_percent': cpu,
        'memory_percent': mem_percent,
        'memory_used': mem_used,
        'memory_total': mem_total,
        'disk_percent': disk_percent,
        'disk_used': disk_used,
        'disk_total': disk_total,
        'uptime': str(uptime).split('.')[0],
        'version': config_manager.app_version,
        'sms_stats': sms_engine.get_statistics(),
        'modem_stats': modem_manager.get_statistics(),
    })


# ---- 配置导入导出 ----

@app.route('/api/config/export')
@login_required
@api_error_handler
def api_export_config():
    """API: 导出配置"""
    config_data = config_manager.export_config()
    return Response(
        json.dumps(config_data, indent=2, ensure_ascii=False),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=config_backup.json'}
    )


@app.route('/api/config/import', methods=['POST'])
@login_required
@api_error_handler
def api_import_config():
    """API: 导入配置"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '未上传文件'})

    file = request.files['file']
    try:
        data = json.loads(file.read())
        config_manager.import_config(data)
        return jsonify({'success': True})
    except json.JSONDecodeError:
        return jsonify({'success': False, 'error': 'JSON解析错误'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ---- WebSocket 事件 ----

if HAS_SOCKETIO:
    @socketio.on('connect')
    def handle_connect():
        notifier.register_client(request.sid)
        logger.debug(f"WebSocket客户端连接: {request.sid}")

    @socketio.on('disconnect')
    def handle_disconnect():
        notifier.unregister_client(request.sid)


# ---- 上下文处理器 ----

@app.context_processor
def inject_common():
    """注入公共模板变量"""
    return {
        'app_name': config_manager.app_name,
        'app_version': config_manager.app_version,
        'current_year': datetime.now().year,
        'modem_count': len(modem_manager.get_all_modems()),
        'modem_online_count': modem_manager.get_statistics().get('online', 0),
    }


# ---- 初始化与启动 ----

def init_app():
    """初始化应用"""
    with app.app_context():
        # 创建数据库表
        db.create_all()
        logger.info("数据库表已初始化")

        # 从 modem_config.json 恢复并自动连接所有已保存的模块
        try:
            modem_manager.load_and_connect_saved_modems()
        except Exception as e:
            logger.error(f"模块恢复异常（不影响 Web 服务）: {type(e).__name__}: {e}")

        # 启动短信同步服务
        sms_engine.start_sync_service()

        # 启动自动重连监控
        modem_manager.start_auto_reconnect()

        logger.info("应用初始化完成")


def cleanup():
    """清理资源"""
    logger.info("正在关闭系统...")
    sms_engine.stop_sync_service()
    modem_manager.stop_all()


def signal_handler(signum, frame):
    """信号处理"""
    logger.info(f"收到信号 {signum}，正在关闭...")
    cleanup()
    sys.exit(0)


# 注册信号处理
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ---- 主入口 ----

if __name__ == '__main__':
    # 初始化
    init_app()

    # 启动 Flask 应用
    host = config_manager.get('app.host', '0.0.0.0')
    port = config_manager.get('app.port', 5000)
    debug = config_manager.debug

    logger.info(f"启动 Web 服务器: {host}:{port} (debug={debug})")

    try:
        if HAS_SOCKETIO and socketio:
            socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
        else:
            app.run(host=host, port=port, debug=debug)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()
