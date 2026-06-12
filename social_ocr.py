# -*- coding: utf-8 -*-

"""
XHS-OCR 主入口文件
支持定时任务和手动执行两种模式
"""

import os
import shutil
import stat
import sys
import time
import argparse
from datetime import datetime, timedelta
# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# 添加项目根目录到Python路径（必须放在最前面，优先级最高）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paramiko
import pytz

from core.logger import logger
from db.pipeline import run_data_processing_pipeline

from dotenv import load_dotenv
from core.run import process_images
from db.data_sync import sync_explore_data_to_remote

load_dotenv()


def cleanup_old_directories(days_ago=5):
    """
    清理指定天数前的本地目录数据

    :param days_ago: 要清理多少天前的数据，默认为5天前
    """
    shanghai_tz = pytz.timezone('Asia/Shanghai')
    home_dir = os.path.expanduser("~")

    # 需要清理的硬件目录列表
    hardware_list = ['aibox', 'futurecloud']

    # 计算阈值日期，早于此日期的目录都将被清理
    threshold_date = (datetime.now(shanghai_tz) - timedelta(days=days_ago)).strftime('%Y%m%d')

    for hardware in hardware_list:
        xhs_ocr_dir = os.path.join(home_dir, "ocr", "xhs", hardware)
        if not os.path.exists(xhs_ocr_dir):
            continue
        for date_folder in os.listdir(xhs_ocr_dir):
            date_path = os.path.join(xhs_ocr_dir, date_folder)
            # 只处理日期格式的目录（8位数字），且早于阈值日期
            if os.path.isdir(date_path) and date_folder.isdigit() and len(date_folder) == 8 and date_folder < threshold_date:
                try:
                    shutil.rmtree(date_path)
                    logger.info(f"已清空 {days_ago} 天前的本地目录: {date_path}")
                except Exception as e:
                    logger.error(f"清空 {days_ago} 天前目录失败 {date_path}: {e}")

    tiktok_ocr_dir = os.path.join(home_dir, "ocr", "tiktok")
    if os.path.exists(tiktok_ocr_dir):
        for date_folder in os.listdir(tiktok_ocr_dir):
            date_path = os.path.join(tiktok_ocr_dir, date_folder)
            # 只处理日期格式的目录（8位数字），且早于阈值日期
            if os.path.isdir(date_path) and date_folder.isdigit() and len(
                    date_folder) == 8 and date_folder < threshold_date:
                try:
                    shutil.rmtree(date_path)
                    logger.info(f"已清空 {days_ago} 天前的本地目录: {date_path}")
                except Exception as e:
                    logger.error(f"清空 {days_ago} 天前目录失败 {date_path}: {e}")
    weibo_ocr_dir = os.path.join(home_dir, "ocr", "weibo")
    if os.path.exists(weibo_ocr_dir):
        for date_folder in os.listdir(weibo_ocr_dir):
            date_path = os.path.join(weibo_ocr_dir, date_folder)
            # 只处理日期格式的目录（8位数字），且早于阈值日期
            if os.path.isdir(date_path) and date_folder.isdigit() and len(
                    date_folder) == 8 and date_folder < threshold_date:
                try:
                    shutil.rmtree(date_path)
                    logger.info(f"已清空 {days_ago} 天前的本地目录: {date_path}")
                except Exception as e:
                    logger.error(f"清空 {days_ago} 天前目录失败 {date_path}: {e}")

    # 清空远程 callfans-rpa 服务的 ocr 目录
    cleanup_remote_ocr_directory()


def _sftp_rmtree(sftp, remote_path):
    """
    递归删除远程目录（SFTP 不支持直接删除非空目录）

    :param sftp: paramiko SFTPClient 实例
    :param remote_path: 远程目录路径
    """
    for entry in sftp.listdir_attr(remote_path):
        entry_path = remote_path + "/" + entry.filename
        if stat.S_ISDIR(entry.st_mode):
            _sftp_rmtree(sftp, entry_path)
        else:
            sftp.remove(entry_path)
    sftp.rmdir(remote_path)


def cleanup_remote_ocr_directory():
    """
    通过 SFTP 清空远程 callfans-rpa 服务上 ocr 目录下的所有内容
    （保留 ocr 目录本身，清空其下所有子目录和文件）
    """
    sftp_host = os.getenv("SFTP_HOST")
    sftp_port = int(os.getenv("SFTP_PORT", "22"))
    sftp_username = os.getenv("SFTP_USERNAME")
    sftp_password = os.getenv("SFTP_PASSWORD")
    remote_ocr_path = os.getenv("SFTP_REMOTE_OCR_PATH", "/home/callfans/ocr")

    if not all([sftp_host, sftp_username, sftp_password]):
        logger.warning("SFTP 环境变量未完整配置，跳过远程目录清理")
        return

    transport = None
    sftp = None
    try:
        transport = paramiko.Transport((sftp_host, sftp_port))
        transport.connect(username=sftp_username, password=sftp_password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        logger.info(f"SFTP 连接成功: {sftp_username}@{sftp_host}:{sftp_port}")

        # 清空 ocr 目录下所有内容
        for entry in sftp.listdir_attr(remote_ocr_path):
            entry_path = remote_ocr_path + "/" + entry.filename
            try:
                if stat.S_ISDIR(entry.st_mode):
                    _sftp_rmtree(sftp, entry_path)
                else:
                    sftp.remove(entry_path)
                logger.info(f"已清空远程目录: {entry_path}")
            except Exception as e:
                logger.error(f"清空远程目录失败 {entry_path}: {e}")

        logger.info(f"远程 ocr 目录已清空: {remote_ocr_path}")

    except Exception as e:
        logger.error(f"SFTP 远程清理失败: {e}")
    finally:
        if sftp:
            sftp.close()
        if transport:
            transport.close()
        logger.info("SFTP 连接已关闭")


def run_ocr_task():
    """
    执行OCR识别任务
    """
    cleanup_old_directories(2)  # 清理2天前的数据

    logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始执行OCR识别任务...")
    try:
        process_images()
        logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] OCR识别任务执行完成")
    except Exception as e:
        logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] OCR识别任务执行出错: {e}")


def run_sync_task():
    """
    执行数据同步任务
    """
    logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始执行数据同步任务...")
    try:
        # 本地数据加工
        day = int(os.getenv("OCR_RECENT_DAYS", "2"))
        run_data_processing_pipeline(days=day)
        # 数据同步
        sync_explore_data_to_remote(table_name='s_xhs_data_overview_traffic_analysis'
                                    , remote_table_name='social_s_xhs_data_overview_traffic_analysis'
                                    , time_filter={"column": "采集日期", "days": day})

        sync_explore_data_to_remote(table_name='s_tiktok_analysis_overview_ocr'
                                    , remote_table_name='social_s_xhs_data_overview_traffic_analysis'
                                    , time_filter={"column": "采集日期", "days": day})

        logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 数据同步任务执行完成")
    except Exception as e:
        logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 数据同步任务执行出错: {e}")


def run_all_tasks(sync_enabled=True):
    """
    执行所有任务：OCR识别 + 数据同步
    :param sync_enabled: 是否启用数据同步功能
    """
    logger.info(f"****[开始]采集数据的加工****")
    run_ocr_task()
    logger.info(f"****[完成]采集数据的加工****")
    if sync_enabled:
        logger.info(f"****[开始]数据的同步****")
        run_sync_task()
        logger.info(f"****[完成]数据的同步****")
    else:
        logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 数据同步功能已禁用")


def manual_run(sync_enabled=True):
    """
    手动执行模式
    :param sync_enabled: 是否启用数据同步功能
    """
    logger.info("XHS-OCR 手动执行模式")
    run_all_tasks(sync_enabled)


def schedule_run(interval, at_time, sync_enabled=True):
    """
    定时任务模式
    :param interval: 时间间隔（分钟）
    :param at_time: 指定时间（如 "10:00"）
    :param sync_enabled: 是否启用数据同步功能
    """
    logger.info("XHS-OCR 定时任务模式")

    try:
        import schedule

        if at_time:
            # 在指定时间执行
            schedule.every().day.at(at_time).do(run_all_tasks, sync_enabled=sync_enabled)
            logger.info(f"默认配置：每天 {at_time} 执行一次任务")
        elif interval:
            # 按时间间隔执行
            schedule.every(interval).minutes.do(run_all_tasks, sync_enabled=sync_enabled)
            logger.info(f"默认配置：每 {interval} 分钟执行一次任务")
        else:
            # 默认每小时执行
            schedule.every().hour.do(run_all_tasks, sync_enabled=sync_enabled)
            logger.info("默认配置：每小时执行一次任务")

        logger.info("定时任务已启动，按 Ctrl+C 退出")

        while True:
            schedule.run_pending()
            time.sleep(1)

    except ImportError:
        logger.error("错误：缺少 schedule 库")
        logger.error("请安装: pip install schedule")
        logger.error("或者使用手动执行模式: python main.py --mode manual")


def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(description='XHS-OCR 主程序')
    parser.add_argument(
        '--mode',
        choices=['manual', 'schedule'],
        default='manual',
        help='运行模式: manual(手动执行) 或 schedule(定时任务)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        help='定时任务时间间隔（分钟）'
    )
    parser.add_argument(
        '--at-time',
        help='定时任务执行时间（如 10:00）'
    )
    parser.add_argument(
        '--sync',
        action='store_true',
        help='是否启用数据同步功能（默认启用）'
    )
    parser.add_argument(
        '--no-sync',
        action='store_false',
        dest='sync',
        help='禁用数据同步功能'
    )
    parser.set_defaults(sync=True)

    args = parser.parse_args()

    if args.mode == 'manual':
        manual_run(args.sync)
    elif args.mode == 'schedule':
        schedule_run(args.interval, args.at_time, args.sync)


if __name__ == "__main__":
    main()
