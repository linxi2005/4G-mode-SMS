# web/mail_forwarder.py
"""邮件转发模块"""
import smtplib
import threading
import logging
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from string import Template

logger = logging.getLogger(__name__)


class MailForwarder:
    """邮件转发器"""

    def __init__(self, config_manager, db_session_factory):
        self.config_manager = config_manager
        self.db_session_factory = db_session_factory
        self._lock = threading.Lock()

    def forward_sms(self, sms_id):
        """转发指定短信"""
        from database.models import SMS, ModemInfo

        session = self.db_session_factory()
        try:
            sms = session.query(SMS).filter_by(id=sms_id).first()
            if not sms:
                logger.warning(f"短信ID={sms_id} 不存在")
                return False

            # 获取模块信息
            modem_info = None
            if sms.module_id:
                modem_info = session.query(ModemInfo).filter_by(module_id=sms.module_id).first()

            # 构建邮件变量
            variables = {
                'phone': sms.phone or '',
                'content': sms.content or '',
                'time': sms.receive_time.strftime('%Y-%m-%d %H:%M:%S') if sms.receive_time else '',
                'imei': sms.imei or '',
                'carrier': modem_info.operator if modem_info else '',
                'signal': str(modem_info.signal_percent) + '%' if modem_info and modem_info.signal_percent else 'N/A',
                'operator': modem_info.operator if modem_info else '',
                'module_name': sms.modem_name or '',
                'module_port': modem_info.port if modem_info else '',
                'module_model': sms.modem_model or '',
            }

            # 发送邮件
            mail_config = self.config_manager.mail_config
            if not mail_config.get('enabled', True):
                logger.debug("邮件转发已禁用")
                return False

            subject = self._render_template(
                mail_config.get('subject_template', '收到来自{{phone}}的新短信'),
                variables
            )
            body = self._render_template(
                mail_config.get('body_template', '<p>{{content}}</p>'),
                variables
            )

            recipients = mail_config.get('recipients', [])
            if not recipients:
                logger.warning("没有配置收件人")
                return False

            success_all = True
            for recipient in recipients:
                success, error = self._send_email(subject, body, recipient)
                self._log_mail(sms_id, recipient, success, error)
                if success:
                    logger.info(f"邮件已发送至 {recipient} (SMS={sms_id})")
                else:
                    logger.error(f"邮件发送失败 {recipient}: {error}")
                    success_all = False

            # 更新短信状态
            if success_all:
                sms.forwarded = True
                sms.forward_count = (sms.forward_count or 0) + 1
                sms.last_forward_time = datetime.now(timezone.utc)
            else:
                sms.forward_count = (sms.forward_count or 0) + 1

            session.commit()
            session.close()
            return success_all

        except Exception as e:
            logger.error(f"转发短信邮件异常: {e}")
            session.rollback()
            session.close()
            return False

    def _send_email(self, subject, body, recipient):
        """发送单封邮件"""
        mail_config = self.config_manager.mail_config

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = mail_config.get('from_email', '')
            msg['To'] = recipient

            html_part = MIMEText(body, 'html', 'utf-8')
            msg.attach(html_part)

            smtp_server = mail_config.get('smtp_server', '')
            smtp_port = mail_config.get('smtp_port', 587)
            use_ssl = mail_config.get('use_ssl', False)
            use_tls = mail_config.get('use_tls', True)
            username = mail_config.get('username', '')
            password = mail_config.get('password', '')
            timeout = mail_config.get('timeout', 30)

            if not smtp_server or not username:
                return False, "SMTP配置不完整"

            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=timeout)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=timeout)

            if use_tls:
                server.starttls()

            server.login(username, password)
            server.sendmail(username, recipient, msg.as_string())
            server.quit()
            return True, None

        except smtplib.SMTPAuthenticationError:
            return False, "SMTP认证失败"
        except smtplib.SMTPConnectError:
            return False, "SMTP连接失败"
        except smtplib.SMTPException as e:
            return False, f"SMTP错误: {str(e)}"
        except Exception as e:
            return False, f"发送异常: {str(e)}"

    def _log_mail(self, sms_id, recipient, success, error):
        """记录邮件发送日志"""
        from database.models import MailLog
        from database.database import db

        session = self.db_session_factory()
        try:
            log_entry = MailLog(
                sms_id=sms_id,
                recipient=recipient,
                success=success,
                error_message=error,
                sent_time=datetime.now(timezone.utc),
            )
            session.add(log_entry)
            session.commit()
            session.close()
        except Exception as e:
            logger.error(f"记录邮件日志失败: {e}")
            session.rollback()
            session.close()

    def test_send(self, recipient=None):
        """发送测试邮件"""
        mail_config = self.config_manager.mail_config
        test_recipient = recipient or mail_config.get('from_email', '')

        if not test_recipient:
            return False, "没有指定测试收件人"

        variables = {
            'phone': '13800138000',
            'content': '这是一封测试短信，用于验证邮件转发配置是否正确。',
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'imei': '860123456789012',
            'carrier': '中国移动',
            'signal': '85%',
            'operator': '中国移动',
            'module_name': '测试模块',
            'module_port': '/dev/ttyUSB0',
            'module_model': 'EC20',
        }

        subject = self._render_template(
            mail_config.get('subject_template', '收到来自{{phone}}的新短信'),
            variables
        )
        body = self._render_template(
            mail_config.get('body_template', '<p>{{content}}</p>'),
            variables
        )

        return self._send_email(subject, body, test_recipient)

    def _render_template(self, template, variables):
        """渲染模板变量 - 使用 {{var}} 格式"""
        if not template:
            return ''
        result = template
        for key, value in variables.items():
            placeholder = '{{' + key + '}}'
            result = result.replace(placeholder, str(value) if value is not None else '')
        return result
