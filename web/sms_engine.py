# web/sms_engine.py
"""短信处理引擎 - 接收、存储、同步、转发"""
import hashlib
import logging
import threading
import time
from datetime import datetime, timezone

from utils.helpers import generate_sms_hash, parse_sms_time, decode_ucs2, decode_pdu_content

logger = logging.getLogger(__name__)


class SMSEngine:
    """短信处理引擎

    负责：
    - 接收实时短信通知
    - 定时同步模块短信
    - 去重存储到数据库
    - 触发邮件/Webhook转发
    """

    def __init__(self, modem_manager, config_manager, db_session_factory):
        self.modem_manager = modem_manager
        self.config_manager = config_manager
        self.db_session_factory = db_session_factory
        self._sync_thread = None
        self._stop_event = threading.Event()
        self._forward_callbacks = []

        # 注册短信回调
        self.modem_manager.add_sms_callback(self._on_sms_received)

    def add_forward_callback(self, callback):
        """添加转发回调 (sms_id)"""
        self._forward_callbacks.append(callback)

    def _on_sms_received(self, module_id, sms_data):
        """实时短信到达处理"""
        try:
            modem = self.modem_manager.get_modem(module_id)
            if not modem:
                logger.warning(f"收到未知模块的短信: {module_id}")
                return

            # 生成哈希
            phone = sms_data.get('phone', '')
            receive_time = sms_data.get('receive_time', datetime.now(timezone.utc))
            content = sms_data.get('content', '')
            imei = modem.info.get('imei', '')

            sms_hash = generate_sms_hash(phone, str(receive_time), content, imei)

            sms_id = self._save_sms(
                module_id=module_id,
                modem_name=modem.name,
                modem_model=modem.info.get('model', ''),
                imei=imei,
                phone=phone,
                receive_time=receive_time,
                content=content,
                encoding=modem.info.get('encoding', 'GSM7'),
                sms_hash=sms_hash,
            )

            if sms_id:
                logger.info(f"[{modem.name}] 短信已保存 (ID={sms_id}): {phone} - {content[:30]}...")
                # 触发转发
                self._trigger_forward(sms_id)

        except Exception as e:
            logger.error(f"处理实时短信异常: {e}")

    def _save_sms(self, module_id, modem_name, modem_model, imei, phone,
                  receive_time, content, encoding, sms_hash, sms_index=None, status=None):
        """保存短信到数据库"""
        from database.models import SMS
        from database.database import db

        session = self.db_session_factory()
        try:
            # 去重检查
            existing = session.query(SMS).filter_by(hash=sms_hash).first()
            if existing:
                # 更新现有记录
                if not existing.forwarded and existing.forward_count == 0:
                    existing.sync_time = datetime.now(timezone.utc)
                    session.commit()
                    return existing.id
                return None

            sms = SMS(
                module_id=module_id,
                modem_name=modem_name,
                modem_model=modem_model,
                imei=imei,
                sms_index=sms_index,
                phone=phone,
                receive_time=receive_time,
                content=content,
                encoding=encoding,
                is_read=(status == 1 if status is not None else True),
                forwarded=False,
                forward_count=0,
                sync_time=datetime.now(timezone.utc),
                hash=sms_hash,
            )
            session.add(sms)
            session.commit()
            sms_id = sms.id
            session.close()
            return sms_id
        except Exception as e:
            session.rollback()
            logger.error(f"保存短信到数据库失败: {e}")
            session.close()
            return None

    def _trigger_forward(self, sms_id):
        """触发所有转发回调"""
        for cb in self._forward_callbacks:
            try:
                cb(sms_id)
            except Exception as e:
                logger.error(f"转发回调异常: {e}")

    def start_sync_service(self):
        """启动定时同步服务"""
        interval = self.config_manager.sms_sync_interval
        self._stop_event.clear()
        self._sync_thread = threading.Thread(
            target=self._sync_loop,
            name="sms-sync-service",
            daemon=True,
        )
        self._sync_thread.start()
        logger.info(f"短信同步服务已启动 (间隔={interval}s)")

    def stop_sync_service(self):
        """停止同步服务"""
        self._stop_event.set()

    def _sync_loop(self):
        """同步循环"""
        interval = self.config_manager.sms_sync_interval

        # 启动时立即执行一次同步
        self.sync_all()

        while not self._stop_event.is_set():
            time.sleep(interval)
            if self._stop_event.is_set():
                break
            try:
                self.sync_all()
            except Exception as e:
                logger.error(f"同步循环异常: {e}")

    def sync_all(self):
        """同步所有在线模块的短信"""
        online_modems = self.modem_manager.get_online_modems()
        total_synced = 0

        for module_id, modem in online_modems.items():
            try:
                synced = self._sync_modem_sms(modem)
                total_synced += synced
            except Exception as e:
                logger.error(f"同步模块 [{modem.name}] 短信失败: {e}")

        return total_synced

    def _sync_modem_sms(self, modem):
        """同步单个模块的短信到数据库"""
        if not modem.is_online or not modem.driver:
            return 0

        messages = modem.sync_sms()
        synced = 0
        imei = modem.info.get('imei', '')

        for msg in messages:
            try:
                index = msg.get('index', 0)
                status = msg.get('status', 0)
                phone = msg.get('sender', '')
                date_str = msg.get('date', '')
                content = msg.get('content', '')

                if not phone or not content:
                    continue

                receive_time = parse_sms_time(date_str)
                sms_hash = generate_sms_hash(phone, str(receive_time), content, imei)

                sms_id = self._save_sms(
                    module_id=modem.module_id,
                    modem_name=modem.name,
                    modem_model=modem.info.get('model', ''),
                    imei=imei,
                    phone=phone,
                    receive_time=receive_time,
                    content=content,
                    encoding=modem.info.get('encoding', 'GSM7'),
                    sms_hash=sms_hash,
                    sms_index=index,
                    status=status,
                )

                if sms_id:
                    synced += 1
                    # 已读状态为1表示已读，不为1则标记为未读
                    if status == 0:
                        modem.mark_read(index)

            except Exception as e:
                logger.error(f"同步单条短信失败: {e}")
                continue

        return synced

    def resend_mail(self, sms_id):
        """重新发送指定短信的邮件"""
        from database.models import SMS
        session = self.db_session_factory()
        try:
            sms = session.query(SMS).filter_by(id=sms_id).first()
            if sms:
                self._trigger_forward(sms_id)
                return True
            return False
        except Exception as e:
            logger.error(f"重新发送邮件失败: {e}")
            return False
        finally:
            session.close()

    def get_sms_list(self, page=1, per_page=20, phone=None, date_from=None,
                     date_to=None, module_id=None, forwarded=None, is_read=None, search=None):
        """分页查询短信列表"""
        from database.models import SMS

        session = self.db_session_factory()
        try:
            query = session.query(SMS)

            if phone:
                query = query.filter(SMS.phone.contains(phone))
            if date_from:
                query = query.filter(SMS.receive_time >= date_from)
            if date_to:
                query = query.filter(SMS.receive_time <= date_to)
            if module_id:
                query = query.filter_by(module_id=module_id)
            if forwarded is not None:
                query = query.filter_by(forwarded=forwarded)
            if is_read is not None:
                query = query.filter_by(is_read=is_read)
            if search:
                query = query.filter(
                    (SMS.phone.contains(search)) |
                    (SMS.content.contains(search)) |
                    (SMS.modem_name.contains(search))
                )

            total = query.count()
            sms_list = query.order_by(SMS.receive_time.desc()) \
                .offset((page - 1) * per_page) \
                .limit(per_page) \
                .all()

            result = [s.to_dict() for s in sms_list]
            session.close()
            return {
                'items': result,
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page,
            }
        except Exception as e:
            logger.error(f"查询短信列表失败: {e}")
            session.close()
            return {'items': [], 'total': 0, 'page': page, 'per_page': per_page, 'pages': 0}

    def batch_action(self, sms_ids, action):
        """批量操作短信"""
        from database.models import SMS
        session = self.db_session_factory()
        try:
            sms_records = session.query(SMS).filter(SMS.id.in_(sms_ids)).all()
            count = 0

            for sms in sms_records:
                if action == 'mark_read':
                    sms.is_read = True
                    count += 1
                elif action == 'mark_unread':
                    sms.is_read = False
                    count += 1
                elif action == 'resend':
                    self._trigger_forward(sms.id)
                    count += 1
                elif action == 'delete':
                    session.delete(sms)
                    count += 1

            session.commit()
            session.close()
            return count
        except Exception as e:
            session.rollback()
            logger.error(f"批量操作失败: {e}")
            session.close()
            return 0

    def export_sms(self, format='json', phone=None, date_from=None, date_to=None,
                   module_id=None, forwarded=None):
        """导出短信"""
        from database.models import SMS
        import json
        import csv
        import io

        session = self.db_session_factory()
        try:
            query = session.query(SMS)
            if phone:
                query = query.filter(SMS.phone.contains(phone))
            if date_from:
                query = query.filter(SMS.receive_time >= date_from)
            if date_to:
                query = query.filter(SMS.receive_time <= date_to)
            if module_id:
                query = query.filter_by(module_id=module_id)
            if forwarded is not None:
                query = query.filter_by(forwarded=forwarded)

            records = query.order_by(SMS.receive_time.desc()).all()

            if format == 'json':
                data = [s.to_dict() for s in records]
                session.close()
                return json.dumps(data, indent=2, ensure_ascii=False), 'application/json'

            elif format == 'csv':
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(['ID', '模块', '型号', 'IMEI', '号码', '时间', '内容',
                                 '编码', '已读', '已转发', '转发次数'])
                for s in records:
                    writer.writerow([
                        s.id, s.modem_name, s.modem_model, s.imei,
                        s.phone, s.receive_time.isoformat() if s.receive_time else '',
                        s.content, s.encoding, s.is_read, s.forwarded, s.forward_count
                    ])
                session.close()
                return output.getvalue(), 'text/csv'

            session.close()
        except Exception as e:
            logger.error(f"导出短信失败: {e}")
            session.close()
        return '', 'text/plain'

    def get_statistics(self):
        """获取短信统计"""
        from database.models import SMS, MailLog
        from datetime import datetime, timedelta, timezone
        from database.database import db

        session = self.db_session_factory()
        try:
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

            today_received = session.query(SMS).filter(SMS.receive_time >= today).count()
            today_forwarded = session.query(SMS).filter(
                SMS.receive_time >= today, SMS.forwarded == True  # noqa: E712
            ).count()
            today_forward_failed = session.query(SMS).filter(
                SMS.receive_time >= today, SMS.forwarded == False,  # noqa: E712
                SMS.forward_count > 0
            ).count()

            # 发送的短信（通过AT+CMGS）
            today_sent = 0  # 需要额外的发送记录表

            total_sms = session.query(SMS).count()
            total_forwarded = session.query(SMS).filter_by(forwarded=True).count()

            session.close()
            return {
                'today_received': today_received,
                'today_sent': today_sent,
                'today_forwarded': today_forwarded,
                'today_forward_failed': today_forward_failed,
                'total_sms': total_sms,
                'total_forwarded': total_forwarded,
            }
        except Exception as e:
            logger.error(f"获取短信统计失败: {e}")
            session.close()
            return {}
