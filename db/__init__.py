"""
XHS OCR 数据库处理模块

该模块提供了处理小红书OCR识别数据的功能，包括：
- 保存用户信息数据
- 保存OCR识别数据
- 数据融合与同步
- 完整的数据处理流水线

主要功能：
- save_userinfo_data: 保存用户信息数据到SQLite数据库
- save_ocr_data: 保存OCR识别数据到SQLite数据库
- run_data_processing_pipeline: 运行完整的数据处理流水线
- run_partial_pipeline: 运行部分数据处理流水线
"""

import sqlite3
import os
from typing import List

# 获取当前文件所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 数据库文件路径
db_path = os.path.join(current_dir, 'ocr_data.db')


def save_userinfo_data(app_name, user_info, ip_port_dir, account_id, collect_time, author_profile_url):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    create_table_sql = f'''
            CREATE TABLE IF NOT EXISTS s_xhs_user_info_ocr (
                "数据来源" TEXT,
                "设备IP" TEXT,
                "账号ID" TEXT,
                "账号昵称" TEXT,
                "采集日期" DATE,
                "关注数" TEXT,
                "粉丝数" TEXT,
                "获赞与收藏" TEXT,
                "链接" TEXT,
                UNIQUE("账号ID", "采集日期")
            )
        '''
    cursor.execute(create_table_sql)
    conn.commit()
    source_type = ""
    if app_name == "xhs":
        source_type = "1894230222988058625"
    elif app_name == "weibo":
        source_type = "1948663593734004737"

    sql_str = f"""
            INSERT OR IGNORE INTO s_xhs_user_info_ocr (
                "设备IP","数据来源","账号ID","账号昵称","采集日期", "关注数","粉丝数", "获赞与收藏","链接"
            ) VALUES (?,?,?,?,?,?,?,?,?)
        """
    cursor.execute(sql_str, (
        ip_port_dir, source_type, account_id, user_info['nickname'], collect_time, user_info['follows'],
        user_info['fans'],
        user_info['interaction'], author_profile_url
    ))

    conn.commit()
    conn.close()


def save_ocr_data(tag, post_title: str, note_link: str, content_type: str, ocr_data: List[str], index_mapping_data,
                  date_dir,
                  ip_port_dir, account_id: str, app_name):
    """
    保存OCR识别数据到数据库
    :param tag: 标签名称
    :param post_title: 文件名（作品标题）
    :param content_type: 内容类型
    :param ocr_data: OCR识别的数据列表
    :param index_mapping_data: 字段名列表
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 对字段名进行转义，避免特殊字符导致SQL语法错误
    escaped_fields = [f'"{field}"' for field in index_mapping_data]

    # print(escaped_fields)

    # 创建表，使用作品标题和OCR采集时间作为联合主键
    create_table_sql = f'''
        CREATE TABLE IF NOT EXISTS s_{app_name}_{tag}_ocr (
            "数据来源" TEXT,
            "设备IP" TEXT,
            "账号ID" TEXT,
            "作品标题" TEXT,
            "链接" TEXT,
            "采集日期" DATE,
            "内容类型" TEXT,
            {(' TEXT, '.join(escaped_fields)) + ' TEXT' if escaped_fields else ''},
            UNIQUE("作品标题", "链接","采集日期")
        )
    '''

    cursor.execute(create_table_sql)
    conn.commit()
    if app_name == "xhs":
        source_type = "1894230222988058625"
    elif app_name == "weibo":
        source_type = "1948663593734004737"
    elif app_name == "tiktok":
        source_type = "1866687481668411393"

    # 使用 INSERT OR IGNORE 语句，当作品标题和OCR采集时间都相同时不插入
    table_len = len(index_mapping_data) + 7  # 4 是指"设备IP","数据来源","账号ID","作品标题", "截图采集日期","OCR采集时间"（这个4个字段）
    sql_str = f"""
        INSERT OR IGNORE INTO s_{app_name}_{tag}_ocr (
            "设备IP","数据来源","账号ID","作品标题", "链接","采集日期","内容类型", {','.join(escaped_fields)}
        ) VALUES ({','.join(['?' for _ in range(table_len)])})
    """
    cursor.execute(sql_str, (
        ip_port_dir, source_type, account_id, post_title, note_link, date_dir, content_type,
        *[ocr_data[i] if len(ocr_data) > i else '' for i in range(len(ocr_data))]
    ))

    conn.commit()
    conn.close()
