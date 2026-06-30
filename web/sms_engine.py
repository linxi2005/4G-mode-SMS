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
        """实时短信到达处理（结构化日志 + 自动转发）"""
        try:
            modem = self.modem_manager.get_modem(module_id)
            if not modem:
                logger.warning(f"收到未知模块的短信: {module_id}")
                return

            # ── 结构化日志：收到短信通知 ──
            phone = sms_data.get('phone', '')
            receive_time = sms_data.get('receive_time', datetime.now(timezone.utc))
            content = sms_data.get('content', '')
            encoding = sms_data.get('encoding', 'GSM7')
            imei = modem.info.get('imei', '')
            sms_index = sms_data.get('sms_index', '')
            storage = sms_data.get('storage', 'ME')
            status_str = sms_data.get('status', 'N/A')

            # 格式化时间输出
            if isinstance(receive_time, datetime):
                time_display = receive_time.strftime('%Y-%m-%d %H:%M:%S')
            else:
                time_display = str(receive_time)

            log_lines = [
                f"[{modem.name}] ╔══ 收到短信通知 ══",
                f"[{modem.name}] ║ Storage : {storage}",
                f"[{modem.name}] ║ Index   : {sms_index if sms_index else 'N/A'}",
                f"[{modem.name}] ║ Status  : {status_str}",
                f"[{modem.name}] ╠══ 开始读取短信...",
                f"[{modem.name}] ║ 发送人  : {phone}",
                f"[{modem.name}] ║ 时间    : {time_display}",
                f"[{modem.name}] ║ 编码    : {encoding}",
                f"[{modem.name}] ║ 内容    :",
            ]
            for content_line in content.replace('\r', '').split('\n'):
                log_lines.append(f"[{modem.name}] ║          {content_line}")
            log_lines.append(f"[{modem.name}] ╚{'═' * 20}")

            for log_line in log_lines:
                logger.info(log_line)

            # 生成哈希
            sms_hash = generate_sms_hash(phone, str(receive_time), content, imei)

            # 保存到数据库
            sms_id = self._save_sms(
                module_id=module_id,
                modem_name=modem.name,
                modem_model=modem.info.get('model', ''),
                imei=imei,
                phone=phone,
                receive_time=receive_time,
                content=content,
                encoding=encoding,
                sms_hash=sms_hash,
                sms_index=sms_index if sms_index else None,
                storage=storage if storage else None,
            )

            if sms_id:
                logger.info(f"[{modem.name}] ✅ 短信已保存 SQLite (ID={sms_id})")
                # 触发转发
                self._trigger_forward(sms_id)
            else:
                logger.info(f"[{modem.name}] ⏭ 短信已存在（去重跳过）")

        except Exception as e:
            logger.error(f"处理实时短信异常: {e}")

    def _save_sms(self, module_id, modem_name, modem_model, imei, phone,
                  receive_time, content, encoding, sms_hash, sms_index=None,
                  status=None, storage=None):
        """保存短信到数据库（去重 + 异常重试）
        
        去重策略:
        1. 优先按 hash 去重（号码+时间+内容+IMEI 的 SHA256）
        2. 如果 sms_index 和 module_id 都有值，额外按 (module_id, sms_index) 检查
        """
        from database.models import SMS
        from database.database import db

        session = self.db_session_factory()
        try:
            # 去重检查 1: 哈希去重
            existing = session.query(SMS).filter_by(hash=sms_hash).first()
            if existing:
                logger.debug(f"短信哈希重复，跳过: hash={sms_hash[:16]}...")
                session.close()
                return None

            # 去重检查 2: (module_id, sms_index) 索引去重
            if module_id and sms_index is not None:
                dup_by_index = session.query(SMS).filter_by(
                    module_id=module_id, sms_index=sms_index
                ).first()
                if dup_by_index:
                    logger.debug(
                        f"短信索引重复，跳过: module={module_id[:8]}..., index={sms_index}"
                    )
                    session.close()
                    return None

            sms = SMS(
                module_id=module_id,
                modem_name=modem_name,
                modem_model=modem_model,
                imei=imei,
                sms_index=sms_index,
                storage=storage,
                phone=phone,
                receive_time=receive_time,
                content=content,
                encoding=encoding,
                is_read=(
                    True if status is None
                    else (status == 1 or str(status).upper() in ('REC READ', 'READ'))
                ),
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
            try:
                session.close()
            except Exception:
                pass
            return None

    def _is_sms_duplicate(self, module_id, phone, receive_time, content, imei, sms_index=None):
        """检查短信是否已存在（用于补扫去重）"""
        from database.models import SMS
        session = self.db_session_factory()
        try:
            sms_hash = generate_sms_hash(phone, str(receive_time), content, imei)
            if session.query(SMS).filter_by(hash=sms_hash).first():
                return True
            if module_id and sms_index is not None:
                if session.query(SMS).filter_by(
                    module_id=module_id, sms_index=sms_index
                ).first():
                    return True
            return False
        except Exception as e:
            logger.warning(f"去重检查异常: {e}")
            return False
        finally:
            try:
                session.close()
            except Exception:
                pass

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
        """同步循环（全量同步 + 未读补扫）"""
        sync_interval = self.config_manager.sms_sync_interval
        # 补扫间隔默认 3 分钟，不超过 sync_interval
        rescan_interval = min(180, sync_interval)
        last_rescan = 0

        # 启动时立即执行一次全量同步
        logger.info("短信同步服务: 启动时执行全量同步...")
        self.sync_all()

        while not self._stop_event.is_set():
            time.sleep(min(10, sync_interval))  # 每 10 秒检查一次
            if self._stop_event.is_set():
                break

            now = time.time()
            try:
                # 定期全量同步
                if now - last_rescan >= sync_interval:
                    self.sync_all()
                    last_rescan = now

                # 定时补扫未读短信（每 3~5 分钟）
                if now - last_rescan >= rescan_interval:
                    self._rescan_unread_all()
                    # 注意: 不更新 last_rescan，让全量同步和补扫独立计时

            except Exception as e:
                logger.error(f"同步循环异常: {e}")

    def _rescan_unread_all(self):
        """补扫所有在线模块的未读短信（CMGL REC UNREAD）"""
        online_modems = self.modem_manager.get_online_modems()
        if not online_modems:
            return

        for module_id, modem in online_modems.items():
            try:
                self._rescan_modem_unread(modem)
            except Exception as e:
                logger.error(f"补扫模块 [{modem.name}] 未读短信异常: {e}")

    def _rescan_modem_unread(self, modem):
        """补扫单个模块的未读短信"""
        if not modem.is_online or not modem.driver:
            return

        unread_msgs = modem.sync_unread_sms()
        if not unread_msgs:
            return

        imei = modem.info.get('imei', '')
        saved_count = 0
        skipped_count = 0

        for msg in unread_msgs:
            try:
                index = msg.get('index', 0)
                phone = msg.get('phone', '') or msg.get('sender', '')
                content = msg.get('content', '')
                encoding = msg.get('encoding', 'GSM7')
                receive_time = msg.get('receive_time', datetime.now(timezone.utc))
                status = msg.get('status', 'REC UNREAD')
                storage = msg.get('storage', 'ME')

                if not phone or not content:
                    continue

                # 去重检查
                if self._is_sms_duplicate(
                    modem.module_id, phone, receive_time, content, imei, index
                ):
                    skipped_count += 1
                    logger.debug(f"[{modem.name}] 补扫: 短信已存在，跳过 index={index}")
                    continue

                # 保存到数据库
                sms_hash = generate_sms_hash(phone, str(receive_time), content, imei)
                sms_id = self._save_sms(
                    module_id=modem.module_id,
                    modem_name=modem.name,
                    modem_model=modem.info.get('model', ''),
                    imei=imei,
                    phone=phone,
                    receive_time=receive_time,
                    content=content,
                    encoding=encoding,
                    sms_hash=sms_hash,
                    sms_index=index,
                    status=(1 if str(status).upper() == 'REC READ' else 0),
                    storage=storage,
                )

                if sms_id:
                    saved_count += 1
                    logger.info(
                        f"[{modem.name}] 补扫保存: 发送人={phone}, "
                        f"时间={receive_time}, 内容={content[:20]}..."
                    )
                    self._trigger_forward(sms_id)

            except Exception as e:
                logger.error(f"[{modem.name}] 补扫处理单条短信异常: {e}")
                continue

        if saved_count > 0 or skipped_count > 0:
            logger.info(
                f"[{modem.name}] 未读短信补扫完成: "
                f"新增={saved_count}, 已跳过={skipped_count}"
            )

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
        """同步单个模块的短信到数据库（全量同步）"""
        if not modem.is_online or not modem.driver:
            return 0

        messages = modem.sync_sms()
        synced = 0
        imei = modem.info.get('imei', '')

        for msg in messages:
            try:
                index = msg.get('index', 0)
                phone = msg.get('phone', '') or msg.get('sender', '')
                content = msg.get('content', '')
                encoding = msg.get('encoding', 'GSM7')
                receive_time = msg.get('receive_time', datetime.now(timezone.utc))
                status = msg.get('status', 0)
                storage = msg.get('storage', 'ME')

                if not phone or not content:
                    continue

                sms_hash = generate_sms_hash(phone, str(receive_time), content, imei)

                sms_id = self._save_sms(
                    module_id=modem.module_id,
                    modem_name=modem.name,
                    modem_model=modem.info.get('model', ''),
                    imei=imei,
                    phone=phone,
                    receive_time=receive_time,
                    content=content,
                    encoding=encoding,
                    sms_hash=sms_hash,
                    sms_index=index,
                    status=status,
                    storage=storage,
                )

                if sms_id:
                    synced += 1
                    logger.debug(
                        f"[{modem.name}] 全量同步保存: index={index}, "
                        f"phone={phone}, content={content[:20]}..."
                    )
                    # CMGR 读取后 EC20 自动标记为已读，不需要额外操作
                    # 除非配置明确开启自动删除
                    auto_delete_days = self.config_manager.get('sms.auto_delete_days', 0)
                    if auto_delete_days > 0:
                        logger.debug(
                            f"[{modem.name}] 自动删除已启用 (>{auto_delete_days}天)，"
                            f"不删除模块端短信（仅删除数据库记录）"
                        )

            except Exception as e:
                logger.error(f"[{modem.name}] 同步单条短信失败: {e}")
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
