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


# 添加数据库同步功能
def sync_explore_data_to_remote(table_name=None, remote_table_name=None,time_filter=None, unique_constraints=None):
    """
    将Download文件夹下的ExploreData.db sqlite数据同步到远程MySQL数据库中
    
    参数:
    table_name_list: 要同步的表名列表
    time_filter: 时间筛选条件，格式为字典{"column": "采集时间", "days": 3}表示最近3天数据
    unique_constraints: 唯一约束定义，格式为字典{表名: [约束字段列表]}
                        例如: {"table1": ["采集时间"], "table2": [["字段1", "字段2"]]}
    """
    try:
        # 从环境变量获取数据库配置
        db_config = {
            "host": os.getenv("MYSQL_HOST", "localhost"),
            "port": int(os.getenv("MYSQL_PORT", 3306)),
            "user": os.getenv("MYSQL_USER", ""),
            "password": os.getenv("MYSQL_PASSWORD", ""),
            "database": os.getenv("MYSQL_DATABASE", "")
        }

        # 如果没有配置数据库，则跳过同步
        if not all([db_config["host"], db_config["user"], db_config["password"], db_config["database"]]):
            logger.warning("未配置远程数据库，跳过数据同步")
            return

        # 获取ExploreData.db路径
        db_path = os.path.join(current_dir, 'ocr_data.db')

        # 检查数据库文件是否存在
        if not os.path.exists(db_path):
            logger.info("ocr_data.db 文件不存在，跳过数据同步")
            return

        # 连接本地SQLite数据库
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 构建查询语句
        if time_filter and time_filter.get("column") and time_filter.get("days"):
            # 如果有时间筛选条件，则只查询最近N天的数据
            time_column = time_filter["column"]
            days = time_filter["days"]
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            query = f"SELECT * FROM {table_name} WHERE {time_column} >= ?"
            cursor.execute(query, (cutoff_date,))
            logger.info(f"执行查询: {query} 参数: {cutoff_date}")
        else:
            # 查询所有数据
            cursor.execute(f"SELECT * FROM {table_name}")
            logger.info(f"执行查询: SELECT * FROM {table_name}")

        rows = cursor.fetchall()
        logger.info(f"表 {table_name} 查询到 {len(rows)} 行数据")

        # 获取列名
        column_names = [description[0] for description in cursor.description]
        # 替换 '采集日期' 为 '采集时间'
        for i, col in enumerate(column_names):
            if col == "采集日期":
                column_names[i] = "采集时间"

        logger.debug(f"列名: {column_names}")

        # 同步到MySQL数据库
        table_unique_constraints = unique_constraints.get(table_name, []) if unique_constraints else []
        sync_to_mysql(db_config, remote_table_name, column_names, rows, table_unique_constraints)
        logger.info(f"表 {table_name} 数据已同步到远程MySQL数据库")

        # 关闭本地数据库连接
        conn.close()

    except Exception as e:
        logger.error(f"同步数据到远程数据库时出错: {str(e)}")


def sync_to_mysql(db_config, remote_table_name, column_names, rows, unique_constraints=None):
    """
    同步数据到MySQL数据库
    支持表不存在时创建表，字段不存在时新增字段
    """
    try:
        import pymysql
        # 创建MySQL连接
        mysql_conn = pymysql.connect(
            host=db_config.get("host", "localhost"),
            port=db_config.get("port", 3306),
            user=db_config.get("user", ""),
            password=db_config.get("password", ""),
            database=db_config.get("database", ""),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            use_unicode=True,
            ssl_disabled=True,  # 对应 useSSL=false
            init_command="SET SESSION time_zone='+08:00'"  # 对应 serverTimezone=Asia/Shanghai
        )
        try:
            with mysql_conn.cursor() as cursor:
                # 检查表是否存在
                try:
                    cursor.execute(f"SHOW TABLES LIKE '{remote_table_name}'")
                    table_result = cursor.fetchall()
                    table_exists = len(table_result) > 0
                    logger.debug(f"检查表 {remote_table_name} 是否存在: {table_exists}, 查询结果: {table_result}")
                except Exception as e:
                    logger.warning(f"检查表 {remote_table_name} 是否存在时出错: {str(e)}")
                    table_exists = False
                logger.info(f"表 {remote_table_name} 约束字段: {unique_constraints}")
                # 如果表不存在，则创建表
                if not table_exists:
                    logger.info(f"表 {remote_table_name} 不存在，正在创建...")
                    create_table_if_not_exists(cursor, remote_table_name, column_names, unique_constraints)
                # else:
                # 如果表存在，检查是否有新增字段需要添加
                # logger.info(f"表 {table_name} 已存在，检查是否需要新增字段...")
                # add_missing_columns(cursor, table_name, column_names, db_config.get("database", ""))

                if rows:
                    # 映射列名为英文名
                    mapped_column_names = []
                    for col in column_names:
                        if col in FIELD_MAPPING:
                            mapped_column_names.append(FIELD_MAPPING[col])
                        else:
                            mapped_column_names.append(col)

                    columns_str = ", ".join([f"`{col}`" for col in mapped_column_names])

                    # 构建ON DUPLICATE KEY UPDATE部分
                    update_fields = []
                    for i, col in enumerate(column_names):
                        if col not in ("id",):
                            eng_col = mapped_column_names[i] if col in FIELD_MAPPING else col
                            update_fields.append(f"`{eng_col}` = VALUES(`{eng_col}`)")

                    placeholders = ", ".join(["%s"] * len(column_names))
                    insert_sql = " ".join(f"""
                                    INSERT INTO {remote_table_name} ({columns_str})
                                    VALUES ({placeholders})
                                    ON DUPLICATE KEY UPDATE {", ".join(update_fields)}
                                    """.split())

                    logger.debug(f'insert_sql:\n{insert_sql}')
                    cursor.executemany(insert_sql, rows)

            # 提交事务
            mysql_conn.commit()
            logger.info(f"成功同步 {len(rows)} 条记录到MySQL数据库")

        finally:
            mysql_conn.close()

    except ImportError:
        logger.error("缺少 pymysql 库，请安装: pip install pymysql")
    except Exception as e:
        logger.error(f"同步到 MySQL 数据库时出错: {str(e)}")


def create_table_if_not_exists(cursor, table_name, column_names, unique_constraints=None):
    """
    如果表不存在则创建表
    """
    columns_definitions = []
    columns_definitions.append('`id` BIGINT AUTO_INCREMENT PRIMARY KEY')
    unique_keys = []

    # 首先处理所有字段定义（不区分唯一与否）
    field_definitions = {}
    for col in column_names:
        if col in FIELD_MAPPING:
            eng_col = FIELD_MAPPING[col]
            if col == "采集日期":
                field_definitions[eng_col] = f"`{eng_col}` DATE COMMENT '{col}'"
            elif col == "采集时间":
                field_definitions[eng_col] = f"`{eng_col}` DATETIME COMMENT '{col}'"
            elif col == "链接":  # 特殊处理 url 字段
                field_definitions[eng_col] = f"`{eng_col}` VARCHAR(512) COMMENT '{col}'"
            elif col == "账号ID":  # 特殊处理 url 字段
                field_definitions[eng_col] = f"`{eng_col}` VARCHAR(128) COMMENT '{col}'"
            else:
                field_definitions[eng_col] = f"`{eng_col}` TEXT COMMENT '{col}'"
        else:
            field_definitions[col] = f"`{col}` TEXT"

    # 处理唯一约束
    if unique_constraints:
        # 使用传入的唯一约束
        if isinstance(unique_constraints, str):  # 单字段唯一约束
            eng_col = FIELD_MAPPING.get(unique_constraints, unique_constraints)
            if eng_col in field_definitions:
                unique_keys.append(f"`{eng_col}`")
        elif isinstance(unique_constraints, list):  # 多字段组合唯一约束
            composite_keys = []
            for col in unique_constraints:
                eng_col = FIELD_MAPPING.get(col, col)
                if eng_col in field_definitions:
                    composite_keys.append(f"`{eng_col}`")
            if composite_keys:
                constraint_name = f"unique_constraint_{'_'.join([c.strip('`') for c in composite_keys])}"
                columns_definitions.append(f"UNIQUE KEY `{constraint_name}` ({', '.join(composite_keys)})")

    # 将字段定义添加到列定义中
    for field_def in field_definitions.values():
        columns_definitions.append(field_def)

    # 添加单字段唯一索引
    for unique_key in unique_keys:
        # 查找对应的字段定义并添加UNIQUE约束
        for i, definition in enumerate(columns_definitions):
            if unique_key in definition and not definition.startswith('`id'):
                # 如果字段定义中还没有UNIQUE关键字，则添加
                if "UNIQUE" not in definition.upper():
                    columns_definitions[i] = definition + " UNIQUE"
                break

    create_table_sql = " ".join(f"""
    CREATE TABLE {table_name} (
        {", ".join(columns_definitions)}
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """.split())

    logger.debug(f"Create table SQL: {create_table_sql}")
    cursor.execute(create_table_sql)


def add_missing_columns(cursor, table_name, column_names, database_name):
    """
    为已存在的表添加缺失的字段
    使用 SHOW COLUMNS 作为系统表查询的替代方案
    """
    try:
        # 使用 SHOW COLUMNS 查询表结构
        cursor.execute(f"SHOW COLUMNS FROM {table_name}")
        existing_columns = [row[0] for row in cursor.fetchall()]
        logger.debug(f"表 {table_name} 的现有字段: {existing_columns}")
    except Exception as e:
        logger.error(f"无法获取表 {table_name} 的字段信息: {str(e)} (数据库: {database_name})")
        return

    # 检查是否有新增字段
    for col in column_names:
        # 映射中文字段名为英文名
        eng_col = FIELD_MAPPING.get(col, col)

        # 检查英文字段名是否已存在
        if eng_col not in existing_columns:
            # 添加缺失的字段
            if col in FIELD_MAPPING:
                if col == "采集日期":
                    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN `{eng_col}` DATE COMMENT '{col}'"
                elif col == "采集时间":
                    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN `{eng_col}` DATETIME COMMENT '{col}'"
                else:
                    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN `{eng_col}` TEXT COMMENT '{col}'"
            else:
                alter_sql = f"ALTER TABLE {table_name} ADD COLUMN `{col}` TEXT"

            logger.info(f"添加缺失字段: {alter_sql}")
            try:
                cursor.execute(alter_sql)
            except Exception as e:
                logger.error(f"添加字段 {eng_col} 时出错: {str(e)} (SQL: {alter_sql})")


def sync_post_data_to_remote(post_data_list, app_name, account_id=None):
    """
    将微博数据同步到远程MySQL数据库中的s_xhs_data_overview_traffic_analysis表
    
    参数:
    weibo_data_list: 微博数据列表，每个元素为包含微博信息的字典
    account_id: 账号ID，可选
    """
    try:
        # 从环境变量获取数据库配置
        db_config = {
            "host": os.getenv("MYSQL_HOST", "localhost"),
            "port": int(os.getenv("MYSQL_PORT", 3306)),
            "user": os.getenv("MYSQL_USER", ""),
            "password": os.getenv("MYSQL_PASSWORD", ""),
            "database": os.getenv("MYSQL_DATABASE", "")
        }

        # 如果没有配置数据库，则跳过同步
        if not all([db_config["host"], db_config["user"], db_config["password"], db_config["database"]]):
            logger.warning("未配置远程数据库，跳过文章POST的数据同步")
            return

        # 导入pymysql
        import pymysql

        # 创建MySQL连接
        mysql_conn = pymysql.connect(
            host=db_config.get("host", "localhost"),
            port=db_config.get("port", 3306),
            user=db_config.get("user", ""),
            password=db_config.get("password", ""),
            database=db_config.get("database", ""),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            use_unicode=True,
            ssl_disabled=True,  # 对应 useSSL=false
            init_command="SET SESSION time_zone='+08:00'"  # 对应 serverTimezone=Asia/Shanghai
        )

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
                        INSERT INTO social_s_xhs_data_overview_traffic_analysis 
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
                        INSERT INTO social_s_xhs_data_overview_traffic_analysis 
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
        # 从环境变量获取数据库配置
        db_config = {
            "host": os.getenv("MYSQL_HOST", "localhost"),
            "port": int(os.getenv("MYSQL_PORT", 3306)),
            "user": os.getenv("MYSQL_USER", ""),
            "password": os.getenv("MYSQL_PASSWORD", ""),
            "database": os.getenv("MYSQL_DATABASE", "")
        }

        # 如果没有配置数据库，则跳过同步
        if not all([db_config["host"], db_config["user"], db_config["password"], db_config["database"]]):
            logger.warning("未配置远程数据库，跳过用户信息数据同步")
            return

        # 导入pymysql
        import pymysql

        # 创建MySQL连接
        mysql_conn = pymysql.connect(
            host=db_config.get("host", "localhost"),
            port=db_config.get("port", 3306),
            user=db_config.get("user", ""),
            password=db_config.get("password", ""),
            database=db_config.get("database", ""),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            use_unicode=True,
            ssl_disabled=True,  # 对应 useSSL=false
            init_command="SET SESSION time_zone='+08:00'"  # 对应 serverTimezone=Asia/Shanghai
        )

        try:
            with mysql_conn.cursor() as cursor:
                # 确保表存在
                table_name = 'social_s_xhs_user_info_ocr'

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
                    INSERT INTO social_s_xhs_user_info_ocr 
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
