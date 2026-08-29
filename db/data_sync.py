import configparser
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from core.logger import logger

load_dotenv()
current_dir = os.path.dirname(os.path.abspath(__file__))
# 加载 config.ini
config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config.ini')
config = configparser.ConfigParser()
config.read(config_file, encoding='utf-8')

# 获取字段映射
FIELD_MAPPING = {}
for section in config.sections():
    if section.startswith('fields'):
        for key, value in config.items(section):
            FIELD_MAPPING[value] = key  # 中文 -> 英文



def _get_db_config():
    """获取MySQL数据库配置，如果未配置返回None"""
    db_config = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", 3306)),
        "user": os.getenv("MYSQL_USER", ""),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "")
    }
    if not all([db_config["host"], db_config["user"], db_config["password"], db_config["database"]]):
        return None
    return db_config


def _create_mysql_connection(db_config):
    """创建MySQL连接"""
    import pymysql
    return pymysql.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        use_unicode=True,
        ssl_disabled=True,
        init_command="SET SESSION time_zone='+08:00'"
    )


def sync_ocr_records_to_remote(records: list, app_name: str):
    """
    将OCR内存记录直接同步到MySQL目标表 s_xhs_data_overview_traffic_analysis

    参数:
    records: OCR记录字典列表，每个字典包含中文字段名和对应的值
    app_name: 应用名称
    """
    if not records:
        logger.info("没有OCR记录需要同步")
        return

    db_config = _get_db_config()
    if not db_config:
        logger.warning("未配置远程数据库，跳过OCR数据同步")
        return

    table_name = 's_xhs_data_overview_traffic_analysis'

    try:
        mysql_conn = _create_mysql_connection(db_config)
    except ImportError:
        logger.error("缺少 pymysql 库，请安装: pip install pymysql")
        return
    except Exception as e:
        logger.error(f"连接MySQL数据库失败: {str(e)}")
        return

    try:
        with mysql_conn.cursor() as cursor:
            # 检查表是否存在
            cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
            if not cursor.fetchall():
                logger.warning(f"表 {table_name} 不存在，请手动初始化")
                return

            # 获取目标表现有列名
            cursor.execute(f"SHOW COLUMNS FROM {table_name}")
            existing_columns = {row['Field'] for row in cursor.fetchall()}
            logger.debug(f"目标表 {table_name} 现有列: {existing_columns}")

            warned_columns = set()
            success_count = 0

            for record in records:
                # 将中文字段名映射为英文列名
                en_record = {}
                for cn_key, value in record.items():
                    # 采集日期 → collection_time（与原有行为保持一致）
                    if cn_key == "采集日期":
                        en_key = "collection_time"
                    elif cn_key in FIELD_MAPPING:
                        en_key = FIELD_MAPPING[cn_key]
                    else:
                        en_key = cn_key

                    # 仅插入目标表中存在的列
                    if en_key in existing_columns:
                        en_record[en_key] = value
                    elif en_key not in warned_columns:
                        logger.warning(f"MySQL表中不存在列 `{en_key}`（来自OCR字段 `{cn_key}`），跳过该字段")
                        warned_columns.add(en_key)

                if not en_record:
                    continue

                columns = list(en_record.keys())
                values = list(en_record.values())

                columns_str = ", ".join([f"`{col}`" for col in columns])
                placeholders = ", ".join(["%s"] * len(columns))
                update_parts = [f"`{col}` = VALUES(`{col}`)" for col in columns if col != 'id']

                insert_sql = f"""
                    INSERT INTO {table_name} ({columns_str})
                    VALUES ({placeholders})
                    ON DUPLICATE KEY UPDATE {", ".join(update_parts)}
                """

                try:
                    cursor.execute(insert_sql, values)
                    success_count += 1
                except Exception as e:
                    logger.error(f"插入OCR记录时出错: {str(e)}, 链接: {en_record.get('url', '未知')}")

            mysql_conn.commit()
            logger.info(f"成功同步 {success_count}/{len(records)} 条OCR记录到MySQL表 {table_name}")

    except Exception as e:
        logger.error(f"同步OCR数据到MySQL时出错: {str(e)}")
    finally:
        mysql_conn.close()


def sync_post_data_to_remote(post_data_list, app_name, account_id=None):
    """
    将微博数据同步到远程MySQL数据库中的s_xhs_data_overview_traffic_analysis表
    
    参数:
    weibo_data_list: 微博数据列表，每个元素为包含微博信息的字典
    account_id: 账号ID，可选
    """
    try:
        db_config = _get_db_config()
        if not db_config:
            logger.warning("未配置远程数据库，跳过文章POST的数据同步")
            return

        mysql_conn = _create_mysql_connection(db_config)

        try:
            with mysql_conn.cursor() as cursor:
                # 确保表存在
                table_name = 's_xhs_data_overview_traffic_analysis'

                # 检查表是否存在
                try:
                    cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
                    table_result = cursor.fetchall()
                    table_exists = len(table_result) > 0
                    logger.debug(f"检查表 {table_name} 是否存在: {table_exists}, 查询结果: {table_result}")
                except Exception as e:
                    logger.warning(f"检查表 {table_name} 是否存在时出错: {str(e)}")
                    table_exists = False

                # 如果表不存在，则创建表
                if not table_exists:
                    logger.info(f"表 {table_name} 不存在，请手动初始化")
                    # 使用与现有表结构一致的定义创建表

                # 准备插入数据
                if app_name == "weibo":
                    for post_data in post_data_list:
                        # 映射微博数据到表字段
                        url = post_data.get("blog_link", "")
                        title = post_data.get("content", "")
                        collection_time = post_data.get("timestamp", "")
                        view_count = str(post_data.get("read_count", ""))
                        shares = str(post_data.get("forward_count", ""))
                        comments = str(post_data.get("comment_count", ""))
                        likes = str(post_data.get("like_count", ""))

                        # 获取设备IP和来源类型（如果有提供）
                        device_ip = post_data.get("device_ip", "")  # 如果数据中有设备IP可以传入
                        source_type = "1948663593734004737"  # 默认设为weibo

                        # 构建INSERT语句
                        insert_sql = """
                        INSERT INTO s_xhs_data_overview_traffic_analysis 
                        (device_ip, account_id, source_type, url, title, collection_time, view_count, shares, comments, likes, type)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        title = VALUES(title),
                        view_count = VALUES(view_count),
                        shares = VALUES(shares),
                        comments = VALUES(comments),
                        likes = VALUES(likes),
                        account_id = VALUES(account_id),
                        device_ip = VALUES(device_ip),
                        collection_time =VALUES(collection_time)
                        """

                        # 建议改进
                        try:
                            affected_rows = cursor.execute(insert_sql, (
                                device_ip,
                                account_id,
                                source_type,
                                url,
                                title,
                                collection_time,
                                view_count,
                                shares,
                                comments,
                                likes,
                                "微博"
                            ))
                            logger.debug(f"微博数据SQL执行成功，影响行数: {affected_rows}")
                        except Exception as e:
                            logger.error(f"执行微博数据SQL时出错: {str(e)}, SQL: {insert_sql}")
                elif app_name == 'tiktok':
                    for post_data in post_data_list:
                        # 映射微博数据到表字段
                        url = post_data.get("post_link", "")
                        title = post_data.get("title", "")
                        collection_time = post_data.get("timestamp", "")
                        view_count = str(post_data.get("view_count", ""))
                        collects = str(post_data.get("collection_count", ""))
                        comments = str(post_data.get("comment_count", ""))
                        likes = str(post_data.get("like_count", ""))

                        # 获取设备IP和来源类型（如果有提供）
                        device_ip = post_data.get("device_ip", "")  # 如果数据中有设备IP可以传入
                        source_type = "1866687481668411393"

                        # 构建INSERT语句
                        insert_sql = """
                        INSERT INTO s_xhs_data_overview_traffic_analysis 
                        (device_ip, account_id, source_type, url, title, collection_time, view_count, collects, comments, likes, type)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        title = VALUES(title),
                        view_count = VALUES(view_count),
                        collects = VALUES(collects),
                        comments = VALUES(comments),
                        likes = VALUES(likes),
                        account_id = VALUES(account_id),
                        device_ip = VALUES(device_ip),
                        collection_time =VALUES(collection_time)
                        """

                        # 建议改进
                        try:
                            affected_rows = cursor.execute(insert_sql, (
                                device_ip,
                                account_id,
                                source_type,
                                url,
                                title,
                                collection_time,
                                view_count,
                                collects,
                                comments,
                                likes,
                                "tiktok视频"
                            ))
                            logger.debug(f"POST数据SQL执行成功，影响行数: {affected_rows}")
                        except Exception as e:
                            logger.error(f"执行POST数据SQL时出错: {str(e)}, SQL: {insert_sql}")

                # 提交事务
                mysql_conn.commit()
                logger.info(f"成功同步 {len(post_data_list)} 条POST数据到MySQL数据库")

        finally:
            mysql_conn.close()

    except ImportError:
        logger.error("缺少 pymysql 库，请安装: pip install pymysql")
    except Exception as e:
        logger.error(f"同步POST数据到 MySQL 数据库时出错: {str(e)}")


def sync_user_info_to_remote(user_info_list, app_name=None, ip_port=None, account_id=None):
    """
    将用户信息数据同步到远程MySQL数据库中的s_xhs_user_info_ocr表
    
    参数:
    user_info_list: 用户信息数据列表，每个元素为包含用户信息的字典
    app_name: 应用名称
    ip_port: 设备IP和端口
    account_id: 账号ID
    """
    try:
        db_config = _get_db_config()
        if not db_config:
            logger.warning("未配置远程数据库，跳过用户信息数据同步")
            return

        mysql_conn = _create_mysql_connection(db_config)

        try:
            with mysql_conn.cursor() as cursor:
                # 确保表存在
                table_name = 's_xhs_user_info_ocr'

                # 检查表是否存在
                try:
                    cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
                    table_result = cursor.fetchall()
                    table_exists = len(table_result) > 0
                    logger.debug(f"检查表 {table_name} 是否存在: {table_exists}, 查询结果: {table_result}")
                except Exception as e:
                    logger.warning(f"检查表 {table_name} 是否存在时出错: {str(e)}")
                    table_exists = False

                # 如果表不存在，则创建表
                if not table_exists:
                    logger.info(f"表 {table_name} 不存在，请手动初始化")
                    # 使用与现有表结构一致的定义创建表

                # 准备插入数据
                for user_info in user_info_list:
                    # 映射用户信息数据到表字段
                    nickname = user_info.get("nickname", "")
                    url = user_info.get("profile_url", "")
                    follows = str(user_info.get("follows", "0"))
                    fans = str(user_info.get("fans", "0"))
                    interaction = user_info.get("interaction")
                    try:
                        interaction = int(interaction) if interaction not in (None, '') else 0
                    except (ValueError, TypeError):
                        interaction = 0
                    collection_time = user_info.get("collect_time", "")

                    # 设备IP和来源类型
                    device_ip = ip_port  # 使用ip_port作为设备IP
                    if app_name == "xhs":
                        source_type = "1894230222988058625"
                    elif app_name == "weibo":
                        source_type = "1948663593734004737"
                    elif app_name == "tiktok":
                        source_type = "1866687481668411393"

                    # 构建INSERT语句
                    insert_sql = """
                    INSERT INTO s_xhs_user_info_ocr 
                    (device_ip, account_id, source_type, url, nickname, interaction, follows, fans, collection_time)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    nickname = VALUES(nickname),
                    follows = VALUES(follows),
                    fans = VALUES(fans),
                    interaction = VALUES(interaction),
                    account_id = VALUES(account_id),
                    device_ip = VALUES(device_ip),
                    collection_time =VALUES(collection_time)
                    """

                    try:
                        affected_rows = cursor.execute(insert_sql, (
                            device_ip,
                            account_id,
                            source_type,
                            url,
                            nickname,
                            interaction,
                            follows,
                            fans,
                            collection_time
                        ))
                        logger.debug(f"SQL执行成功，影响行数: {affected_rows}")
                    except Exception as e:
                        logger.error(f"执行SQL时出错: {str(e)}, SQL: {insert_sql}")

                # 提交事务
                mysql_conn.commit()
                logger.info(f"成功同步 {len(user_info_list)} 条用户信息数据到MySQL数据库")

        finally:
            mysql_conn.close()

    except ImportError:
        logger.error("缺少 pymysql 库，请安装: pip install pymysql")
    except Exception as e:
        logger.error(f"同步用户信息数据到 MySQL 数据库时出错: {str(e)}")
