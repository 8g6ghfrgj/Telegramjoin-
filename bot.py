#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram Group Joiner Bot - النسخة النهائية
بوت متكامل لإدارة حسابات تليجرام والانضمام للمجموعات
"""

import asyncio
import logging
import re
import sqlite3
import os
import sys
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from telethon import TelegramClient, errors
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.sessions import StringSession
from telethon.tl.types import KeyboardButton, ReplyKeyboardMarkup
import configparser

# ============================================
# 🔧 إعدادات البوت
# ============================================

class Config:
    """فئة لتحميل الإعدادات"""
    
    @staticmethod
    def load():
        """تحميل الإعدادات من البيئة أو ملف"""
        config = configparser.ConfigParser()
        
        # أولوية لمتغيرات البيئة
        bot_token = os.environ.get('BOT_TOKEN')
        admin_id = os.environ.get('ADMIN_ID')
        join_delay = os.environ.get('JOIN_DELAY', '60')
        links_per_session = os.environ.get('LINKS_PER_SESSION', '1000')
        log_level = os.environ.get('LOG_LEVEL', 'INFO')
        
        # إذا لم تكن متغيرات البيئة موجودة، اقرأ من ملف
        if not bot_token and os.path.exists('config.ini'):
            config.read('config.ini', encoding='utf-8')
            bot_token = config.get('BOT', 'token', fallback=None)
            admin_id = config.get('BOT', 'admin_id', fallback='8294336757')
            join_delay = config.get('BOT', 'join_delay', fallback='60')
            links_per_session = config.get('BOT', 'links_per_session', fallback='1000')
            log_level = config.get('BOT', 'log_level', fallback='INFO')
        
        # التحقق من التوكن
        if not bot_token or bot_token == 'YOUR_BOT_TOKEN_HERE':
            raise ValueError("❌ يرجى إضافة توكن البوت في config.ini أو متغير BOT_TOKEN البيئي")
        
        return {
            'bot_token': bot_token,
            'admin_id': int(admin_id) if admin_id else 8294336757,
            'join_delay': int(join_delay),
            'links_per_session': int(links_per_session),
            'log_level': log_level,
            'api_id': 6,
            'api_hash': 'eb06d4abfb49dc3eeb1aeb98ae0f581e',
            'messages_per_channel': 500
        }

# ============================================
# 📊 إعدادات التسجيل
# ============================================

def setup_logging(log_level='INFO'):
    """إعداد نظام التسجيل"""
    # إنشاء مجلدات
    os.makedirs('logs', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    os.makedirs('backups', exist_ok=True)
    
    # مستوى التسجيل
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # إعداد التسجيل
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/bot.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

# ============================================
# 🗄️ قاعدة البيانات
# ============================================

class Database:
    """مدير قاعدة البيانات"""
    
    def __init__(self, db_file='data/sessions.db'):
        """تهيئة قاعدة البيانات"""
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.setup_tables()
    
    def setup_tables(self):
        """إنشاء الجداول"""
        cursor = self.conn.cursor()
        
        # جدول الجلسات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_string TEXT UNIQUE,
                phone TEXT,
                first_name TEXT,
                username TEXT,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                links_processed INTEGER DEFAULT 0,
                max_links INTEGER DEFAULT 1000,
                total_success INTEGER DEFAULT 0,
                total_failed INTEGER DEFAULT 0
            )
        ''')
        
        # جدول الروابط
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link TEXT UNIQUE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_processed BOOLEAN DEFAULT 0,
                processed_by INTEGER,
                processed_at TIMESTAMP,
                success BOOLEAN,
                FOREIGN KEY (processed_by) REFERENCES sessions (id)
            )
        ''')
        
        # جدول القنوات المصدر
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS source_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_link TEXT UNIQUE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_scraped TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    def add_session(self, session_string, phone, first_name, username, user_id):
        """إضافة جلسة جديدة"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO sessions 
            (session_string, phone, first_name, username, user_id, last_used, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (session_string, phone, first_name, username, user_id, datetime.now(), 1))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_active_sessions(self):
        """الحصول على الجلسات النشطة"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, session_string, phone, first_name, links_processed
            FROM sessions 
            WHERE is_active = 1 AND links_processed < max_links
            ORDER BY links_processed ASC
        ''')
        return cursor.fetchall()
    
    def get_pending_links(self, limit=1000):
        """الحصول على الروابط المعلقة"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, link FROM links 
            WHERE is_processed = 0 
            ORDER BY added_at 
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()
    
    def add_links(self, links):
        """إضافة روابط جديدة"""
        cursor = self.conn.cursor()
        added = 0
        for link in links:
            try:
                cursor.execute('INSERT OR IGNORE INTO links (link) VALUES (?)', (link,))
                if cursor.rowcount > 0:
                    added += 1
            except:
                pass
        self.conn.commit()
        return added
    
    def update_link_status(self, link_id, session_id, success):
        """تحديث حالة الرابط"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE links 
            SET is_processed = 1, processed_by = ?, processed_at = ?, success = ?
            WHERE id = ?
        ''', (session_id, datetime.now(), success, link_id))
        
        # تحديث إحصائيات الجلسة
        if success:
            cursor.execute('''
                UPDATE sessions 
                SET links_processed = links_processed + 1, 
                    total_success = total_success + 1,
                    last_used = ?
                WHERE id = ?
            ''', (datetime.now(), session_id))
        else:
            cursor.execute('''
                UPDATE sessions 
                SET links_processed = links_processed + 1, 
                    total_failed = total_failed + 1,
                    last_used = ?
                WHERE id = ?
            ''', (datetime.now(), session_id))
        
        self.conn.commit()
    
    def get_statistics(self):
        """الحصول على الإحصائيات"""
        cursor = self.conn.cursor()
        
        stats = {}
        
        # إحصائيات الجلسات
        cursor.execute('SELECT COUNT(*) as total, SUM(links_processed) as processed FROM sessions WHERE is_active = 1')
        sessions = cursor.fetchone()
        stats['sessions'] = dict(sessions)
        
        # إحصائيات الروابط
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN is_processed = 1 THEN 1 ELSE 0 END) as processed,
                SUM(CASE WHEN is_processed = 0 THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success
            FROM links
        ''')
        links = cursor.fetchone()
        stats['links'] = dict(links)
        
        return stats
    
    def close(self):
        """إغلاق الاتصال"""
        if self.conn:
            self.conn.close()

# ============================================
# 🤖 البوت الرئيسي
# ============================================

class TelegramGroupJoinerBot:
    def __init__(self):
        """تهيئة البوت"""
        # تحميل الإعدادات
        self.config = Config.load()
        
        # إعدادات البوت
        self.bot_token = self.config['bot_token']
        self.admin_id = self.config['admin_id']
        self.join_delay = self.config['join_delay']
        self.links_per_session = self.config['links_per_session']
        self.api_id = self.config['api_id']
        self.api_hash = self.config['api_hash']
        
        # إعداد قاعدة البيانات
        self.db = Database()
        
        # الحالات المؤقتة
        self.user_states = {}
        
        # لوحة المفاتيح
        self.main_keyboard = ReplyKeyboardMarkup(
            [
                [KeyboardButton("📱 إضافة جلسة"), KeyboardButton("📋 عرض الجلسات")],
                [KeyboardButton("🔗 طلب روابط القنوات"), KeyboardButton("🚀 بدء الانضمام")],
                [KeyboardButton("📊 الإحصائيات"), KeyboardButton("❓ المساعدة")]
            ],
            resize_keyboard=True
        )
        
        # البوت
        self.bot_client = None
        
        logger.info("✅ تم تهيئة البوت")
    
    async def start(self):
        """بدء تشغيل البوت"""
        try:
            logger.info("🚀 بدء تشغيل البوت...")
            
            # إنشاء عميل البوت
            self.bot_client = TelegramClient(
                'bot_session',
                self.api_id,
                self.api_hash
            )
            
            # تشغيل البوت
            await self.bot_client.start(bot_token=self.bot_token)
            
            # التحقق من الاتصال
            me = await self.bot_client.get_me()
            logger.info(f"✅ البوت يعمل: @{me.username}")
            
            # إرسال رسالة البدء
            await self.send_startup_message()
            
            # إضافة معالج الرسائل
            self.bot_client.add_event_handler(self.handle_message)
            
            # تشغيل البوت
            await self.bot_client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"❌ خطأ في التشغيل: {e}")
            raise
    
    async def send_startup_message(self):
        """إرسال رسالة بدء التشغيل"""
        try:
            stats = self.db.get_statistics()
            
            message = f"""
🚀 **تم تشغيل البوت بنجاح!**

📊 **الإحصائيات:**
• 📱 الجلسات: {stats['sessions']['total'] or 0}
• 🔗 الروابط المعلقة: {stats['links']['pending'] or 0}
• ✅ الناجحة: {stats['links']['success'] or 0}

⚙️ **الإعدادات:**
• ⏱️ التأخير: {self.join_delay} ثانية
• 🔢 روابط/جلسة: {self.links_per_session}

📌 **استخدم الأزرار للتحكم**
            """
            
            await self.bot_client.send_message(self.admin_id, message, buttons=self.main_keyboard)
            
        except Exception as e:
            logger.error(f"خطأ في إرسال رسالة البدء: {e}")
    
    async def handle_message(self, event):
        """معالجة الرسائل"""
        try:
            # التحقق من المسؤول
            if event.message.sender_id != self.admin_id:
                return
            
            text = event.message.text or ""
            
            # معالجة الأزرار
            if text == "📱 إضافة جلسة":
                await self.start_add_session(event)
            
            elif text == "📋 عرض الجلسات":
                await self.list_sessions(event)
            
            elif text == "🔗 طلب روابط القنوات":
                await self.request_channel_links(event)
            
            elif text == "🚀 بدء الانضمام":
                await self.start_joining(event)
            
            elif text == "📊 الإحصائيات":
                await self.show_statistics(event)
            
            elif text == "❓ المساعدة":
                await self.show_help(event)
            
            elif text == "/start":
                await self.send_welcome(event)
            
            else:
                await self.handle_user_state(event, text)
                
        except Exception as e:
            logger.error(f"خطأ في معالجة الرسالة: {e}")
            await event.reply("❌ حدث خطأ", buttons=self.main_keyboard)
    
    async def send_welcome(self, event):
        """إرسال رسالة ترحيبية"""
        welcome = """
🤖 **مرحباً بك في بوت إدارة حسابات Telegram**

🎯 **المميزات:**
• إدارة عدة حسابات تيليجرام
• استخراج الروابط من القنوات
• انضمام تلقائي للمجموعات
• إحصائيات مفصلة

📌 **استخدم الأزرار للبدء**
        """
        
        await event.reply(welcome, buttons=self.main_keyboard)
    
    async def start_add_session(self, event):
        """بدء إضافة جلسة"""
        self.user_states[event.sender_id] = 'awaiting_session'
        await event.reply("📱 **أرسل جلسة التيثون (String Session):**")
    
    async def add_session(self, event, session_string):
        """إضافة جلسة"""
        try:
            session_string = session_string.strip()
            
            # التحقق من الجلسة
            temp_client = TelegramClient(
                StringSession(session_string),
                self.api_id,
                self.api_hash
            )
            
            await temp_client.connect()
            
            if not await temp_client.is_user_authorized():
                await event.reply("❌ الجلسة غير صالحة", buttons=self.main_keyboard)
                return
            
            # معلومات الحساب
            me = await temp_client.get_me()
            
            # حفظ في قاعدة البيانات
            session_id = self.db.add_session(
                session_string,
                me.phone or "غير معروف",
                me.first_name or "",
                me.username or "",
                me.id
            )
            
            response = f"""
✅ **تم إضافة الجلسة بنجاح!**

📋 **المعلومات:**
• 🆔 المعرف: `{session_id}`
• 📞 الهاتف: `{me.phone or 'غير معروف'}`
• 👤 الاسم: `{me.first_name or ''}`
• 🏷️ اليوزر: @{me.username or 'لا يوجد'}

🎯 **سيتم استخدامها للانضمام إلى {self.links_per_session} مجموعة**
            """
            
            await event.reply(response, buttons=self.main_keyboard)
            
            await temp_client.disconnect()
            
            # حذف الحالة
            if event.sender_id in self.user_states:
                del self.user_states[event.sender_id]
            
        except Exception as e:
            logger.error(f"خطأ في إضافة الجلسة: {e}")
            await event.reply(f"❌ خطأ: {str(e)}", buttons=self.main_keyboard)
    
    async def list_sessions(self, event):
        """عرض الجلسات"""
        try:
            sessions = self.db.get_active_sessions()
            
            if not sessions:
                await event.reply("📭 **لا توجد جلسات**", buttons=self.main_keyboard)
                return
            
            response = "📋 **الجلسات النشطة:**\n\n"
            
            for idx, session in enumerate(sessions, 1):
                response += f"""
{idx}. **{session['first_name'] or 'غير معروف'}**
   📞: `{session['phone'] or 'غير معروف'}`
   🔗: {session['links_processed']}/{self.links_per_session}
   🆔: {session['id']}
"""
            
            # إحصائيات
            stats = self.db.get_statistics()
            pending = stats['links']['pending'] or 0
            needed = (pending // self.links_per_session) + (1 if pending % self.links_per_session > 0 else 0)
            
            response += f"""
📊 **التحليل:**
• 🔗 الروابط المعلقة: {pending}
• 📱 الجلسات النشطة: {len(sessions)}
• 🎯 الجلسات المطلوبة: {needed}
• ⏱️ التأخير: {self.join_delay} ثانية
"""
            
            await event.reply(response, buttons=self.main_keyboard)
            
        except Exception as e:
            logger.error(f"خطأ في عرض الجلسات: {e}")
            await event.reply(f"❌ خطأ: {str(e)}", buttons=self.main_keyboard)
    
    async def request_channel_links(self, event):
        """طلب روابط القنوات"""
        self.user_states[event.sender_id] = 'awaiting_channel_links'
        
        instructions = """
🔗 **إضافة روابط القنوات**

📝 **أرسل روابط القنوات التي تحتوي على مجموعات:**
• رابط واحد في كل سطر
• مثال: https://t.me/channel_name
• أو: @username

📤 **أرسل الروابط الآن:**
        """
        
        await event.reply(instructions)
    
    async def process_channel_links(self, event, text):
        """معالجة روابط القنوات"""
        try:
            lines = text.strip().split('\n')
            links_to_add = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # تنظيف الرابط
                link = self.clean_telegram_link(line)
                if link:
                    links_to_add.append(link)
            
            # إضافة الروابط
            added = self.db.add_links(links_to_add)
            
            # إحصائيات
            stats = self.db.get_statistics()
            pending = stats['links']['pending'] or 0
            
            response = f"""
✅ **تمت الإضافة بنجاح!**

📊 **النتائج:**
• 🔗 الروابط الجديدة: {added}
• ⏳ إجمالي المعلقة: {pending}
• 📱 الجلسات المطلوبة: {(pending // self.links_per_session) + 1}

💡 **كل جلسة تنضم إلى {self.links_per_session} مجموعة**
            """
            
            await event.reply(response, buttons=self.main_keyboard)
            
            # حذف الحالة
            if event.sender_id in self.user_states:
                del self.user_states[event.sender_id]
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الروابط: {e}")
            await event.reply(f"❌ خطأ: {str(e)}", buttons=self.main_keyboard)
    
    def clean_telegram_link(self, link):
        """تنظيف رابط تليجرام"""
        link = link.strip()
        
        # إزالة المسافات
        link = re.sub(r'\s+', '', link)
        
        # @username إلى رابط كامل
        if link.startswith('@'):
            link = f"https://t.me/{link[1:]}"
        
        # التحقق من أن الرابط تليجرام
        patterns = [
            r'https?://t\.me/',
            r'https?://telegram\.me/'
        ]
        
        for pattern in patterns:
            if re.match(pattern, link, re.IGNORECASE):
                return link
        
        return None
    
    async def start_joining(self, event):
        """بدء عملية الانضمام"""
        try:
            # التحقق من الجلسات
            sessions = self.db.get_active_sessions()
            if not sessions:
                await event.reply("❌ **لا توجد جلسات نشطة**", buttons=self.main_keyboard)
                return
            
            # التحقق من الروابط
            pending_links = self.db.get_pending_links(1)
            if not pending_links:
                await event.reply("❌ **لا توجد روابط معلقة**", buttons=self.main_keyboard)
                return
            
            # حساب الوقت
            total_pending = self.db.get_statistics()['links']['pending'] or 0
            estimated_time = total_pending * self.join_delay / 60  # دقائق
            
            confirmation = f"""
🚀 **بدء عملية الانضمام**

📊 **التجهيزات:**
• 📱 الجلسات: {len(sessions)}
• 🔗 الروابط: {total_pending}
• ⏱️ الوقت المتوقع: {estimated_time:.1f} دقيقة

✅ **هل تريد البدء؟**
أرسل **نعم** للموافقة أو **لا** للإلغاء
            """
            
            self.user_states[event.sender_id] = 'confirm_joining'
            await event.reply(confirmation)
            
        except Exception as e:
            logger.error(f"خطأ في بدء العملية: {e}")
            await event.reply(f"❌ خطأ: {str(e)}", buttons=self.main_keyboard)
    
    async def process_joining(self, event):
        """معالجة الانضمام"""
        try:
            await event.reply("🚀 **بدأت العملية...**")
            
            # الحصول على الجلسات والروابط
            sessions = self.db.get_active_sessions()
            all_links = self.db.get_pending_links(10000)  # 10000 رابط كحد أقصى
            
            if not sessions or not all_links:
                await event.reply("❌ **لا توجد بيانات كافية**", buttons=self.main_keyboard)
                return
            
            # توزيع الروابط
            session_links = {}
            links_per_session = self.links_per_session
            
            for session in sessions:
                session_id = session['id']
                remaining = links_per_session - session['links_processed']
                
                if remaining > 0 and all_links:
                    session_links[session_id] = {
                        'session': session,
                        'links': all_links[:remaining]
                    }
                    all_links = all_links[remaining:]
            
            # بدء المهام
            tasks = []
            for session_id, data in session_links.items():
                task = asyncio.create_task(
                    self.process_session(
                        session_id,
                        data['session']['session_string'],
                        data['links'],
                        data['session']['phone']
                    )
                )
                tasks.append(task)
            
            # انتظار الانتهاء
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # حساب النتائج
                total_success = 0
                total_failed = 0
                
                for result in results:
                    if isinstance(result, tuple):
                        success, failed = result
                        total_success += success
                        total_failed += failed
            
            # تقرير النهاية
            await self.send_joining_report(event, total_success, total_failed)
            
        except Exception as e:
            logger.error(f"خطأ في العملية: {e}")
            await event.reply(f"❌ خطأ: {str(e)}", buttons=self.main_keyboard)
    
    async def process_session(self, session_id, session_string, links, phone):
        """معالجة جلسة"""
        client = None
        success = 0
        failed = 0
        
        try:
            # إنشاء العميل
            client = TelegramClient(
                StringSession(session_string),
                self.api_id,
                self.api_hash
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error(f"الجلسة {session_id} غير مصرح بها")
                return success, failed
            
            logger.info(f"بدء الجلسة {session_id} ({phone})")
            
            # معالجة الروابط
            for link_id, link in links:
                try:
                    join_success = await self.join_group(client, link)
                    
                    # تحديث قاعدة البيانات
                    self.db.update_link_status(link_id, session_id, join_success)
                    
                    if join_success:
                        success += 1
                        logger.info(f"✅ {session_id}: انضم إلى {link[:50]}...")
                    else:
                        failed += 1
                        logger.warning(f"❌ {session_id}: فشل في {link[:50]}...")
                    
                    # تأخير
                    await asyncio.sleep(self.join_delay)
                    
                except Exception as e:
                    logger.error(f"خطأ في الرابط {link}: {e}")
                    failed += 1
                    await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"خطأ في الجلسة {session_id}: {e}")
        finally:
            if client:
                await client.disconnect()
            
            logger.info(f"انتهت الجلسة {session_id}: ✅{success} ❌{failed}")
            
            return success, failed
    
    async def join_group(self, client, link):
        """الانضمام لمجموعة"""
        try:
            clean_link = link.strip()
            
            if 'joinchat/' in clean_link:
                invite_hash = clean_link.split('joinchat/')[-1]
                await client(ImportChatInviteRequest(invite_hash))
            else:
                entity = await client.get_entity(clean_link)
                await client(JoinChannelRequest(entity))
            
            return True
            
        except errors.FloodWaitError as e:
            logger.warning(f"Flood wait: {e.seconds} ثانية")
            await asyncio.sleep(e.seconds + 10)
            return False
            
        except errors.UserAlreadyParticipantError:
            logger.info(f"مستخدم موجود بالفعل: {link}")
            return True
            
        except errors.InviteHashExpiredError:
            logger.warning(f"رابط منتهي: {link}")
            return False
            
        except Exception as e:
            logger.error(f"خطأ في الانضمام: {link} - {e}")
            return False
    
    async def send_joining_report(self, event, success, failed):
        """إرسال تقرير الانضمام"""
        try:
            stats = self.db.get_statistics()
            
            report = f"""
🏁 **تقرير عملية الانضمام**

📊 **نتائج الجلسة:**
• ✅ النجاح: {success}
• ❌ الفشل: {failed}
• 📈 المعدل: {(success/(success+failed)*100) if (success+failed) > 0 else 0:.1f}%

📊 **إجمالي الإحصائيات:**
• 🔗 المعالجة: {stats['links']['processed'] or 0}
• ⏳ المعلقة: {stats['links']['pending'] or 0}
• 📱 الجلسات: {stats['sessions']['total'] or 0}

🕐 **الوقت:** {datetime.now().strftime('%H:%M:%S')}
            """
            
            await event.reply(report, buttons=self.main_keyboard)
            
        except Exception as e:
            logger.error(f"خطأ في إرسال التقرير: {e}")
    
    async def show_statistics(self, event):
        """عرض الإحصائيات"""
        try:
            stats = self.db.get_statistics()
            
            # حساب الوقت المتبقي
            pending = stats['links']['pending'] or 0
            sessions = stats['sessions']['total'] or 0
            
            if sessions > 0 and pending > 0:
                time_needed = (pending / sessions) * self.join_delay / 3600  # ساعات
                time_text = f"{time_needed:.1f} ساعة"
            else:
                time_text = "غير متوفر"
            
            response = f"""
📊 **إحصائيات البوت**

📱 **الجلسات:**
• النشطة: {sessions}
• المعالجة: {stats['sessions']['processed'] or 0}

🔗 **الروابط:**
• الإجمالي: {stats['links']['total'] or 0}
• المعالجة: {stats['links']['processed'] or 0}
• المعلقة: {pending}
• الناجحة: {stats['links']['success'] or 0}

⏱️ **التوقيت:**
• التأخير: {self.join_delay} ثانية
• المتبقي: {time_text}
• المطلوبة: {(pending // self.links_per_session) + 1} جلسة
            """
            
            await event.reply(response, buttons=self.main_keyboard)
            
        except Exception as e:
            logger.error(f"خطأ في عرض الإحصائيات: {e}")
            await event.reply(f"❌ خطأ: {str(e)}", buttons=self.main_keyboard)
    
    async def show_help(self, event):
        """عرض التعليمات"""
        help_text = f"""
❓ **تعليمات استخدام البوت**

🎯 **خطوات العمل:**
1. **أضف جلسات** باستخدام زر 📱 إضافة جلسة
2. **أضف روابط** باستخدام زر 🔗 طلب روابط القنوات
3. **ابدأ العملية** باستخدام زر 🚀 بدء الانضمام

⚙️ **الإعدادات:**
• كل جلسة تنضم إلى {self.links_per_session} مجموعة
• التأخير بين الروابط {self.join_delay} ثانية
• البوت يتعرف على روابط تليجرام فقط

⚠️ **نصائح مهمة:**
• تأكد من صلاحية الجلسات
• أضف روابط مجموعات نشطة
• لا تبدأ بدون جلسات كافية
• راقب السجلات في logs/bot.log
        """
        
        await event.reply(help_text, buttons=self.main_keyboard)
    
    async def handle_user_state(self, event, text):
        """معالجة الحالات"""
        user_id = event.sender_id
        
        if user_id not in self.user_states:
            return
        
        state = self.user_states[user_id]
        
        if state == 'awaiting_session':
            await self.add_session(event, text)
        
        elif state == 'awaiting_channel_links':
            await self.process_channel_links(event, text)
        
        elif state == 'confirm_joining':
            if text.lower() in ['نعم', 'yes', 'y', 'ابدأ']:
                await self.process_joining(event)
            else:
                await event.reply("❌ **تم الإلغاء**", buttons=self.main_keyboard)
            
            if user_id in self.user_states:
                del self.user_states[user_id]

# ============================================
# 🚀 التشغيل الرئيسي
# ============================================

async def main():
    """الدالة الرئيسية"""
    try:
        # تحميل الإعدادات
        config = Config.load()
        
        # إعداد التسجيل
        global logger
        logger = setup_logging(config['log_level'])
        
        logger.info("=" * 50)
        logger.info("🚀 بدء تشغيل Telegram Group Joiner Bot")
        logger.info(f"👤 المسؤول: {config['admin_id']}")
        logger.info(f"⚙️  التأخير: {config['join_delay']} ثانية")
        logger.info(f"🔢 الروابط/جلسة: {config['links_per_session']}")
        logger.info("=" * 50)
        
        # إنشاء وتشغيل البوت
        bot = TelegramGroupJoinerBot()
        await bot.start()
        
    except ValueError as e:
        logger.error(str(e))
        print("\n" + "=" * 50)
        print("❌ خطأ في الإعدادات:")
        print(str(e))
        print("\n🔧 كيفية الإصلاح:")
        print("1. أضف متغيرات البيئة على Render:")
        print("   - BOT_TOKEN: توكن البوت")
        print("   - ADMIN_ID: معرفك الرقمي")
        print("2. أو أنشئ ملف config.ini")
        print("=" * 50)
        
    except KeyboardInterrupt:
        logger.info("⏹️  تم إيقاف البوت")
        
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
        
    finally:
        logger.info("👋 انتهى التشغيل")

if __name__ == "__main__":
    # تشغيل البوت
    asyncio.run(main())
