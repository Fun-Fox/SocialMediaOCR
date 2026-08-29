"""
XHS OCR 数据库处理模块

该模块提供了处理社交媒体OCR识别数据的功能，包括：
- 构建OCR识别数据记录（内存字典）
- 数据同步到远程MySQL数据库

主要功能：
- build_ocr_record: 构建OCR识别数据记录（返回内存字典，不写入任何数据库）
"""

from typing import List


def get_source_type(app_name: str) -> str:
    """根据应用名称获取数据来源类型ID"""
    source_types = {
        "xhs": "1894230222988058625",
        "weibo": "1948663593734004737",
        "tiktok": "1866687481668411393",
    }
    return source_types.get(app_name, "")


def build_ocr_record(tag: str, post_title: str, note_link: str, content_type: str,
                     ocr_data: List[str], index_mapping_data: List[str],
                     date_dir: str, ip_port_dir: str, account_id: str,
                     app_name: str) -> dict:
    """
    构建OCR识别数据记录（内存字典），不写入任何数据库

    :param tag: 标签名称
    :param post_title: 文件名（作品标题）
    :param note_link: 作品链接
    :param content_type: 内容类型
    :param ocr_data: OCR识别的数据列表
    :param index_mapping_data: 字段名列表
    :param date_dir: 采集日期目录名
    :param ip_port_dir: 设备IP
    :param account_id: 账号ID
    :param app_name: 应用名称
    :return: 包含所有OCR数据的字典
    """
    record = {
        "数据来源": get_source_type(app_name),
        "设备IP": ip_port_dir,
        "账号ID": account_id,
        "作品标题": post_title,
        "链接": note_link,
        "采集日期": date_dir,
        "内容类型": content_type,
    }
    for i, field_name in enumerate(index_mapping_data):
        record[field_name] = ocr_data[i] if i < len(ocr_data) else ''
    return record
