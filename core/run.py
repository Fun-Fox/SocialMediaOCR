import json
import os
import re
import cv2
import numpy as np
from PIL import Image
from core.logger import logger
# from core.ocr import sort_text_lines_by_surya_position, ocr, sort_text_lines_by_paddle_position
from core.ocr import sort_text_lines_by_surya_position, sort_text_lines_by_paddle_position
# 调用同步函数将数据同步到远程数据库
from db.data_sync import sync_post_data_to_remote, sync_user_info_to_remote, sync_ocr_records_to_remote
# 引入数据库模块
from db import build_ocr_record
import time
import configparser
from datetime import datetime, timedelta

from dotenv import load_dotenv

# 配置日志文件
load_dotenv()

# 蒙版图路径
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# OCR 图片目录
ocr_root = os.getenv("OCR_IMAGES_PATH", os.path.join(root_dir, "images"))
ocr_engine = os.getenv("OCR_ENGINE", "surya")

ocr = None
if ocr_engine == "PaddleOCR":
    from core.ppocr_api import GetOcrApi

    # OCR 引擎路径
    ocr_engine_path = os.getenv("OCR_ENGINE_PATH")
    if not ocr_engine_path:
        logger.error("OCR_ENGINE_PATH 环境变量未设置")
    elif not os.path.exists(ocr_engine_path):
        logger.error(f"OCR引擎路径不存在: {ocr_engine_path}")
    else:
        # 初始化 OCR 引擎
        try:
            ocr = GetOcrApi(ocr_engine_path)
        except Exception as e:
            logger.error(f"初始化OCR引擎失败: {e}")

# 读取配置文件
config = configparser.ConfigParser()
with open(os.path.join(root_dir, 'config.ini'), encoding='utf-8') as f:
    config.read_file(f)


def upscale_image(image, scale_factor=2):
    """
    放大图像

    Args:
        image: 输入图像
        scale_factor: 放大倍数，默认为2

    Returns:
        放大后的图像
    """
    return cv2.resize(image, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)


def preprocess_image(image):
    """
    对图像进行预处理：去噪和二值化

    Args:
        image: 输入图像

    Returns:
        预处理后的图像
    """
    # 转换为灰度图
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 应用高斯模糊去噪
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # 使用自适应阈值进行二值化
    binary = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        11,
        2
    )

    return binary


def enhance_image(image, alpha=1.5, beta=50):
    """
    增加图像的对比度和亮度

    Args:
        image: 输入图像
        alpha: 对比度控制参数，默认为1.5
        beta: 亮度控制参数，默认为50

    Returns:
        增强后的图像
    """
    # 使用公式：output = alpha * input + beta
    enhanced_img = cv2.convertScaleAbs(image, alpha=alpha, beta=beta)
    return enhanced_img


def process_images():
    # try:
    #     import subprocess
    #     import sys
    #     # 安装 Chromium 浏览器（如果尚未安装）
    #     result = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
    #                             capture_output=True, text=True)
    #     if result.returncode != 0:
    #         logger.warning(f"Playwright 安装失败: {result.stderr}")
    #     logger.info(f"Playwright chromium 安装成功")
    # except ImportError:
    #     logger.warning("playwright 模块未安装，某些功能可能不可用")
    """
    处理OCR目录下的所有图片
    """
    if ocr_engine == "PaddleOCR":
        if ocr is None:
            logger.error("OCR引擎未初始化，无法处理图片")
            return
        if ocr.getRunningMode() == "local":
            logger.info(f"初始化OCR成功，进程号为{ocr.ret.pid}")
        elif ocr.getRunningMode() == "remote":
            logger.info(f"连接远程OCR引擎成功，ip：{ocr.ip}，port：{ocr.port}")

    # 遍历 OCR 目录下的所有图片

    # 获取最近2天的日期列表
    recent_dates = []
    day = int(os.getenv("OCR_RECENT_DAYS", "2"))
    for i in range(day):
        date_str = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
        recent_dates.append(date_str)
    logger.info(f"最近{day}天日期: {recent_dates}")
    # logger.info(f"开始扫描ocr目录：{ocr_dir}")

    # 检查ocr目录是否存在
    if not os.path.exists(ocr_root):
        logger.error(f"OCR目录不存在: {ocr_root}")
        return

    # 第一步：只扫描一级目录
    level_one_dirs = []
    for item in os.listdir(ocr_root):
        item_path = os.path.join(ocr_root, item)
        if os.path.isdir(item_path):
            logger.info(f"一级目录: {item}")
            level_one_dirs.append(item)

    # 第二步：扫描二级目录
    for level_one_dir in level_one_dirs:

        level_one_path = os.path.join(ocr_root, level_one_dir)
        app_name = level_one_dir
        logger.info(f"\n====APP名称： {app_name}====\n")
        for item in os.listdir(level_one_path):
            item_path = os.path.join(level_one_path, item)
            if os.path.isdir(item_path):
                # logger.info(f"  二级目录: {level_one_dir}/{item}")

                if app_name == "xhs":
                    logger.info(f"\n======硬件名称： {item}======\n")
                    hard_ware = item
                    app_data_collection_path = os.path.join(ocr_root, app_name, hard_ware)

                elif app_name == "weibo":
                    logger.info(f"\n======采集日期： {item}======\n")

                    app_data_collection_path = os.path.join(ocr_root, app_name)
                elif app_name == "tiktok":
                    logger.info(f"\n======采集日期： {item}======\n")

                    app_data_collection_path = os.path.join(ocr_root, app_name)
                else:
                    logger.info(f"异常采集APP: {app_name}")
                    continue

                for root, dirs, files in os.walk(app_data_collection_path):
                    # 只扫描ocr_dir下最近3天的目录文件夹(例如目录是20250902的)
                    dir_contains_recent_date = any(date in root for date in recent_dates)

                    # logger.info(f"扫描目录: {root}, 包含最近日期: {dir_contains_recent_date}")

                    # 如果是根目录，继续遍历子目录
                    if root == app_data_collection_path:
                        continue

                    # 如果当前路径不包含最近3天的日期，则跳过
                    if not dir_contains_recent_date:
                        # logger.info(f"跳过目录(非最近{day}天): {root}")
                        continue

                    logger.info(f"处理最近{day}天的目录: {root}")
                    post_records = {}
                    for filename in files:
                        # 构建图片路径
                        file_path = os.path.join(root, filename)
                        parent_dir = os.path.dirname(file_path)  # 获取图片所在目录
                        if '#' in os.path.basename(parent_dir):
                            ip_port_dir, account_id = os.path.basename(parent_dir).split('#')
                        else:
                            ip_port_dir, account_id = os.path.basename(parent_dir), '无'
                        date_dir = os.path.basename(os.path.dirname(parent_dir))  # 获取日期文件夹名
                        collect_date = date_dir
                        if filename == "user_info.json" and app_name == "tiktok":
                            logger.info(f"\n====开始处理TK用户信息====\n{file_path}")
                            # 同步到本地数据库
                            user_info = {}
                            # 如果文件名是user_info.json 则读取文件
                            with open(file_path, 'r', encoding='utf-8') as f:
                                profile_data = json.load(f)
                                if isinstance(profile_data, dict):
                                    author_profile_url = profile_data.get("share_link", "")
                                    user_info['nickname'] = profile_data.get('nickname', '')
                                    user_info['follows'] = profile_data.get('follow_count', '')
                                    user_info['fans'] = profile_data.get('follower_count', '')
                                    user_info['interaction'] = convert_chinese_numbers(
                                        profile_data.get('like_count', ''))
                                    user_info['collect_time'] = collect_date  # 添加采集时间
                                    user_info['profile_url'] = author_profile_url  # 添加个人主页链接
                            try:
                                # 检查是否成功获取到用户信息（判断user_info是否包含有效数据）
                                if isinstance(user_info, dict) and user_info.get('nickname'):
                                    logger.info(f"保存用户信息成功: {user_info}")
                                    logger.info(f"account_id:{account_id}")
                                    # 同步到本地数据库
                                    # save_userinfo_data(app_name, user_info, ip_port_dir, account_id, collect_date,
                                    #                    author_profile_url)
                                    # 同步到远程数据库
                                    sync_user_info_to_remote([user_info], app_name, ip_port_dir, account_id)
                                else:
                                    logger.error(f"获取用户信息失败: {author_profile_url}")
                            except Exception as e:
                                logger.error(f"处理用户信息失败: {author_profile_url}, 错误: {e}")
                            logger.info(f"\n====处理TK用户信息完成====\n")

                        if filename == "post_data.json" and app_name == "tiktok":
                            # 读取weibo_data.json文件
                            # 直接同步到远程数据库s_xhs_data_overview_traffic_analysis
                            logger.info(f"\n====开始处理微博数据====\n{file_path}")
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    post_data_list = json.load(f)

                                # 为每条微博数据添加设备IP和账号ID
                                for post_data in post_data_list:
                                    post_data["device_ip"] = ip_port_dir
                                    post_data['collect_time'] = collect_date
                                logger.info(f"account_id:{account_id}")

                                sync_post_data_to_remote(post_data_list, app_name, account_id)
                            except Exception as e:
                                logger.error(f"处理weibo_data.json文件时出错: {e}")
                            logger.info(f"\n====处理微博数据完成====\n")

                        if filename == "weibo_data.json" and app_name == "weibo":
                            # 读取weibo_data.json文件
                            # 直接同步到远程数据库s_xhs_data_overview_traffic_analysis
                            logger.info(f"\n====开始处理微博数据====\n{file_path}")
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    post_data_list = json.load(f)

                                # 为每条微博数据添加设备IP和账号ID
                                for post_data in post_data_list:
                                    post_data["device_ip"] = ip_port_dir
                                    post_data['collect_time'] = collect_date
                                logger.info(f"account_id:{account_id}")

                                sync_post_data_to_remote(post_data_list, app_name, account_id)
                            except Exception as e:
                                logger.error(f"处理weibo_data.json文件时出错: {e}")
                            logger.info(f"\n====处理微博数据完成====\n")

                        if filename == "user_info.json" and app_name == "weibo":
                            logger.info(f"\n====开始处理微博用户信息====\n{file_path}")
                            # 同步到本地数据库
                            user_info = {}
                            # 如果文件名是user_info.json 则读取文件
                            with open(file_path, 'r', encoding='utf-8') as f:
                                profile_data = json.load(f)
                                if isinstance(profile_data, dict):
                                    author_profile_url = profile_data.get("share_link", "")
                                    user_info['nickname'] = profile_data.get('nickname', '')
                                    user_info['follows'] = profile_data.get('follow_count', '')
                                    user_info['fans'] = profile_data.get('follower_count', '')
                                    # user_info['interaction'] = ''  # 获赞与收藏(微博没有这个数据)
                                    user_info['collect_time'] = collect_date  # 添加采集时间
                                    user_info['profile_url'] = author_profile_url  # 添加个人主页链接

                            try:
                                # 检查是否成功获取到用户信息（判断user_info是否包含有效数据）
                                if isinstance(user_info, dict) and user_info.get('nickname'):
                                    logger.info(f"保存用户信息成功: {user_info}")
                                    logger.info(f"account_id:{account_id}")
                                    # 同步到本地数据库
                                    # save_userinfo_data(app_name, user_info, ip_port_dir, account_id, collect_date,
                                    #                    author_profile_url)
                                    # 同步到远程数据库
                                    sync_user_info_to_remote([user_info], app_name, ip_port_dir, account_id)
                                else:
                                    logger.error(f"获取用户信息失败: {author_profile_url}")
                            except Exception as e:
                                logger.error(f"处理用户信息失败: {author_profile_url}, 错误: {e}")
                            logger.info(f"\n====处理微博用户信息完成====\n")
                        # 处理小红书用户信息文件 (profile_url.json)
                        if filename == "profile_url.json" and app_name == "xhs":
                            logger.info(f"\n====开始处理小红书用户信息====\n{file_path}")
                            # 同步到本地数据库
                            user_info = {}
                            # 如果文件名是profile_url.json 则读取文件
                            with open(file_path, 'r', encoding='utf-8') as f:
                                profile_data = json.load(f)
                                if isinstance(profile_data, dict):
                                    author_profile_url = profile_data.get("user_profile_url", "")
                                    user_info['nickname'] = profile_data.get('nickname', '')
                                    user_info['follows'] = convert_chinese_numbers(
                                        profile_data.get('following_count', ''))
                                    user_info['fans'] = convert_chinese_numbers(profile_data.get('fans', ''))
                                    user_info['interaction'] = convert_chinese_numbers(
                                        profile_data.get('likes_collect_count', ''))  # 获赞与收藏
                                    user_info['collect_time'] = collect_date  # 添加采集时间
                                    user_info['profile_url'] = author_profile_url  # 添加个人主页链接

                            try:
                                # 检查是否成功获取到用户信息（判断user_info是否包含有效数据）
                                if isinstance(user_info, dict) and user_info.get('nickname'):
                                    logger.info(f"保存用户信息成功: {user_info}")
                                    # 同步到本地数据库
                                    # save_userinfo_data(app_name, user_info, ip_port_dir, account_id, collect_date,
                                    #                    author_profile_url)
                                    # 同步到远程数据库
                                    sync_user_info_to_remote([user_info], app_name, ip_port_dir, account_id)
                                else:
                                    logger.error(f"获取用户信息失败: {author_profile_url}")
                            except Exception as e:
                                logger.error(f"处理用户信息失败: {author_profile_url}, 错误: {e}")
                            logger.info(f"\n====处理小红书用户信息完成====\n")
                        elif filename.endswith('.png') and app_name in ("xhs"):
                            logger.info(f"\n====开始处理小红书图片====\n{file_path}")
                            tag, post_title = os.path.basename(filename).replace(".png", "").split('#')
                            json_filename = f"{post_title}.json"
                            json_file_path = os.path.join(root, json_filename)
                            logger.info(f"处理文件: {json_file_path}")
                            note_link = ""
                            if os.path.exists(json_file_path):
                                try:
                                    with open(json_file_path, 'r', encoding='utf-8') as f:
                                        json_data = json.load(f)
                                        note_link = json_data.get("note_link", "")
                                        # post_content = json_data.get("post_content", "")
                                        # clean_title = json_data.get("clean_title", "")
                                except Exception as e:
                                    logger.error(f"读取JSON文件失败: {json_file_path}, 错误: {e}")
                            else:
                                logger.warning(f"JSON文件不存在: {json_file_path}")

                            logger.info(f"处理图片: {filename}, 日期: {date_dir}, 设备: {ip_port_dir}")

                            # 查找tag文件夹中的所有蒙版文件
                            mask_folder = os.path.join(root_dir, "mask", app_name, hard_ware, tag)
                            logger.info(f"蒙版文件夹: {mask_folder}")
                            mask_files = []

                            if os.path.exists(mask_folder) and os.path.isdir(mask_folder):
                                # 获取文件夹内所有png文件
                                for file in os.listdir(mask_folder):
                                    if file.lower().endswith('.png'):
                                        mask_files.append(file)
                                mask_files.sort()  # 排序确保处理顺序一致性

                            # 依次尝试每个蒙版文件
                            ocr_success = False
                            for mask_file in mask_files:
                                try:
                                    mask_path = os.path.join(mask_folder, mask_file)
                                    logger.info(f"使用蒙版: {mask_file}")
                                    # 读取原图和蒙版图
                                    original_img = imread_with_pil(file_path)
                                    mask_img = imread_with_pil(mask_path)  # 读取带Alpha通道的蒙版图

                                    # 检查原图是否有效
                                    if original_img is None:
                                        logger.error(f"原图加载失败: {file_path}")
                                        continue

                                    # 检查蒙版图是否有效
                                    if mask_img is None:
                                        logger.error(f"蒙版图加载失败: {mask_path}")
                                        continue

                                    # 确保蒙版图与原图尺寸一致
                                    if original_img.shape[:2] != mask_img.shape[:2]:
                                        logger.warning(
                                            f"蒙版图尺寸不匹配: {mask_img.shape[:2]} vs {original_img.shape[:2]}")
                                        continue

                                    # 使用蒙版图合成新图片（保留蒙版区域，其他区域变黑）
                                    alpha = mask_img[:, :, 3] / 255.0  # 提取Alpha通道并归一化
                                    result_img = original_img * alpha[:, :, np.newaxis]  # 应用Alpha混合
                                    result_img = result_img.astype(np.uint8)

                                    # 将结果保存为临时文件
                                    temp_output_path = os.path.join(root_dir, "tmp", "temp_ocr_input.png")
                                    # temp_output_path = os.path.join(root_dir, r"tmp", f"{time.time()}.png")
                                    # 放大
                                    # result_img = upscale_image(result_img, scale_factor=2)
                                    # result_img = enhance_image(result_img, alpha=1, beta=20)  # 增加对比度和亮度
                                    cv2.imwrite(temp_output_path, result_img, [cv2.IMWRITE_PNG_COMPRESSION, 1])

                                    # 等待文件写入完成并验证
                                    timeout = 5  # 超时时间（秒）
                                    start_time = time.time()
                                    while not os.path.exists(temp_output_path):
                                        if time.time() - start_time > timeout:
                                            logger.error(f"文件写入超时: {temp_output_path}")
                                            break
                                        time.sleep(0.1)

                                    # 验证文件是否写入成功
                                    if os.path.exists(temp_output_path):
                                        file_size = os.path.getsize(temp_output_path)
                                        if file_size > 0:
                                            logger.info(f"临时文件保存完成，大小: {file_size} bytes")
                                        else:
                                            logger.warning(f"临时文件写入完成但大小为0: {temp_output_path}")
                                    else:
                                        logger.error(f"临时文件保存失败: {temp_output_path}")

                                    # 从配置文件中获取index_mapping_data
                                    index_mapping_data = []
                                    if config.has_section('tags') and config.has_option('tags', tag):
                                        index_mapping_data_str = config.get('tags', tag)
                                        index_mapping_data = [item.strip() for item in
                                                              index_mapping_data_str.split(',')]
                                    # 执行 OCR 识别
                                    # 使用快速的蒙版识别方式，使用VLM OCR方式
                                    logger.info(f"正在处理: {filename}")

                                    if ocr_engine == "PaddleOCR":
                                        getObj = ocr.run(temp_output_path)
                                        # print(getObj)
                                        if not getObj["code"] == 100:
                                            logger.info(f"OCR识别结果: {getObj}")
                                            logger.error(
                                                f"使用蒙版文件{mask_path},OCR识别失败: 请检查{file_path},是否为空白图片")
                                            continue
                                        # sorted_lines = getObj["data"]
                                        # 这里也增加从左到右 从上到下的排序功能
                                        # print("排序前:", getObj["data"])
                                        sorted_lines = sort_text_lines_by_paddle_position(getObj["data"])
                                    # surya ocr
                                    # else:
                                    #     # 执行OCR
                                    #     img = Image.open(temp_output_path)
                                    #     img_pred = ocr(img, with_bboxes=True)
                                    #     sorted_lines = sort_text_lines_by_surya_position(img_pred.text_lines)

                                    ocr_texts = []
                                    for line in sorted_lines:
                                        if ocr_engine == "PaddleOCR":
                                            text = str(line['text'])
                                        else:
                                            text = line.text
                                        if not filename.startswith("note_traffic_analysis"):
                                            text = re.sub(r'[\u4e00-\u9fff]+', '', text)
                                        text = (text.replace('秒', '')
                                                .replace(' ', '')
                                                .replace('o', '0')
                                                .replace('<b>', '')
                                                .replace('</b>', ''))
                                        if text:
                                            ocr_texts.append(text)
                                    logger.info(f"OCR识别结果：{ocr_texts}")
                                    if filename.startswith("note_traffic_analysis"):
                                        if len(ocr_texts) == 8:
                                            # 使用分隔符连接
                                            ocr_texts = ['|'.join([f"{ocr_texts[i]}:{ocr_texts[i + 1]}"
                                                                   for i in range(0, len(ocr_texts), 2)])]
                                            logger.info(f"流量分析结果：{ocr_texts}")
                                        else:
                                            ocr_texts = []
                                    if len(ocr_texts) != len(index_mapping_data):
                                        logger.warning(
                                            f"{filename}：识别到的数据个数不匹配，尝试使用蒙版库中其余蒙版")
                                        # logger.info(f"{index_mapping_data}")
                                        continue
                                    ocr_success = True
                                    logger.info(f"使用蒙版库中蒙版 {mask_file} OCR识别成功")
                                    break

                                except Exception as e:
                                    logger.warning(f"使用蒙版文件 {mask_file} 处理失败: {e}")
                                    continue

                            if not ocr_success:
                                logger.error(f"使用蒙版库中，所有蒙版，最后还是识别失败: {filename}")
                                continue

                            # 保存数据到数据库
                            tag = re.sub(r'\d+', '', tag)
                            # if note_link:
                            if 'video' in tag:
                                content_type = "视频"
                            else:
                                content_type = "图文"

                            record = build_ocr_record(tag, post_title, note_link, content_type, ocr_texts, index_mapping_data,
                                                      collect_date,
                                                      ip_port_dir,
                                                      account_id, app_name)
                            key = (note_link, post_title, account_id, collect_date)
                            if key not in post_records:
                                post_records[key] = record
                            else:
                                for field, value in record.items():
                                    if value != '':
                                        post_records[key][field] = value
                        elif filename.endswith('.png') and app_name in ("tiktok"):
                            logger.info(f"\n====开始处理tiktok图片====\n{file_path}")
                            tag, note_link = os.path.basename(filename).replace(".png", "").split('#')
                            # 查找tag文件夹中的所有蒙版文件
                            mask_folder = os.path.join(root_dir, "mask", app_name, hard_ware, tag)
                            logger.info(f"蒙版文件夹: {mask_folder}")
                            mask_files = []

                            if os.path.exists(mask_folder) and os.path.isdir(mask_folder):
                                # 获取文件夹内所有png文件
                                for file in os.listdir(mask_folder):
                                    if file.lower().endswith('.png'):
                                        mask_files.append(file)
                                mask_files.sort()  # 排序确保处理顺序一致性
                                # 依次尝试每个蒙版文件
                                ocr_success = False
                                for mask_file in mask_files:
                                    try:
                                        mask_path = os.path.join(mask_folder, mask_file)
                                        logger.info(f"使用蒙版: {mask_file}")
                                        # 读取原图和蒙版图
                                        original_img = imread_with_pil(file_path)
                                        mask_img = imread_with_pil(mask_path)  # 读取带Alpha通道的蒙版图

                                        # 检查原图是否有效
                                        if original_img is None:
                                            logger.error(f"原图加载失败: {file_path}")
                                            continue

                                        # 检查蒙版图是否有效
                                        if mask_img is None:
                                            logger.error(f"蒙版图加载失败: {mask_path}")
                                            continue

                                        # 确保蒙版图与原图尺寸一致
                                        if original_img.shape[:2] != mask_img.shape[:2]:
                                            logger.warning(
                                                f"蒙版图尺寸不匹配: {mask_img.shape[:2]} vs {original_img.shape[:2]}")
                                            continue

                                        # 使用蒙版图合成新图片（保留蒙版区域，其他区域变黑）
                                        alpha = mask_img[:, :, 3] / 255.0  # 提取Alpha通道并归一化
                                        result_img = original_img * alpha[:, :, np.newaxis]  # 应用Alpha混合
                                        result_img = result_img.astype(np.uint8)

                                        # 将结果保存为临时文件
                                        temp_output_path = os.path.join(root_dir, "tmp", "temp_ocr_input.png")
                                        # temp_output_path = os.path.join(root_dir, r"tmp", f"{time.time()}.png")
                                        # 放大
                                        # result_img = upscale_image(result_img, scale_factor=2)
                                        # result_img = enhance_image(result_img, alpha=1, beta=20)  # 增加对比度和亮度
                                        cv2.imwrite(temp_output_path, result_img, [cv2.IMWRITE_PNG_COMPRESSION, 1])

                                        # 等待文件写入完成并验证
                                        timeout = 5  # 超时时间（秒）
                                        start_time = time.time()
                                        while not os.path.exists(temp_output_path):
                                            if time.time() - start_time > timeout:
                                                logger.error(f"文件写入超时: {temp_output_path}")
                                                break
                                            time.sleep(0.1)

                                        # 验证文件是否写入成功
                                        if os.path.exists(temp_output_path):
                                            file_size = os.path.getsize(temp_output_path)
                                            if file_size > 0:
                                                logger.info(f"临时文件保存完成，大小: {file_size} bytes")
                                            else:
                                                logger.warning(f"临时文件写入完成但大小为0: {temp_output_path}")
                                        else:
                                            logger.error(f"临时文件保存失败: {temp_output_path}")

                                        # 从配置文件中获取index_mapping_data
                                        index_mapping_data = []
                                        if config.has_section('tags') and config.has_option('tags', tag):
                                            index_mapping_data_str = config.get('tags', tag)
                                            index_mapping_data = [item.strip() for item in
                                                                  index_mapping_data_str.split(',')]
                                        # 执行 OCR 识别
                                        # 使用快速的蒙版识别方式，使用VLM OCR方式
                                        logger.info(f"正在处理: {filename}")

                                        if ocr_engine == "PaddleOCR":
                                            getObj = ocr.run(temp_output_path)
                                            # print(getObj)
                                            if not getObj["code"] == 100:
                                                logger.info(f"OCR识别结果: {getObj}")
                                                logger.error(
                                                    f"使用蒙版文件{mask_path},OCR识别失败: 请检查{file_path},是否为空白图片")
                                                continue
                                            # sorted_lines = getObj["data"]
                                            # 这里也增加从左到右 从上到下的排序功能
                                            # print("排序前:", getObj["data"])
                                            sorted_lines = sort_text_lines_by_paddle_position(getObj["data"])
                                        # surya ocr
                                        # else:
                                        #     # 执行OCR
                                        #     img = Image.open(temp_output_path)
                                        #     img_pred = ocr(img, with_bboxes=True)
                                        #     sorted_lines = sort_text_lines_by_surya_position(img_pred.text_lines)

                                        ocr_texts = []
                                        for line in sorted_lines:
                                            if ocr_engine == "PaddleOCR":
                                                text = str(line['text'])
                                            else:
                                                text = line.text
                                            text = (text.replace('秒', '')
                                                    .replace('s', '')
                                                    .replace(' ', '')
                                                    .replace('o', '0')
                                                    .replace('<b>', '')
                                                    .replace('</b>', ''))
                                            if text:
                                                ocr_texts.append(text)
                                        logger.info(f"OCR识别结果：{ocr_texts}")
                                        if len(ocr_texts) != len(index_mapping_data):
                                            logger.warning(
                                                f"{filename}：识别到的数据个数不匹配，尝试使用蒙版库中其余蒙版")
                                            # logger.info(f"{index_mapping_data}")
                                            continue
                                        ocr_success = True
                                        logger.info(f"使用蒙版库中蒙版 {mask_file} OCR识别成功")
                                        break

                                    except Exception as e:
                                        logger.warning(f"使用蒙版文件 {mask_file} 处理失败: {e}")
                                        continue

                                if not ocr_success:
                                    logger.error(f"使用蒙版库中，所有蒙版，最后还是识别失败: {filename}")
                                    continue
                                note_link = note_link.replace('*', "/")

                                record = build_ocr_record(tag, '', note_link, "tiktok视频", ocr_texts, index_mapping_data,
                                                          collect_date,
                                                          ip_port_dir,
                                                          account_id, app_name)
                                key = (note_link, '', account_id, collect_date)
                                if key not in post_records:
                                    post_records[key] = record
                                else:
                                    for field, value in record.items():
                                        if value != '':
                                            post_records[key][field] = value

                    if post_records:
                        logger.info(f"正在同步 {len(post_records)} 条OCR记录到远程数据库...")
                        sync_ocr_records_to_remote(list(post_records.values()), app_name)


# 结束 OCR 引擎
# ocr.exit()
# logger.info("程序结束。")


def imread_with_pil(path):
    try:
        pil_image = Image.open(path)
        # 转换为OpenCV格式
        if pil_image.mode == "RGB":
            # RGB to BGR
            open_cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        elif pil_image.mode == "RGBA":
            # RGBA to BGRA
            open_cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGBA2BGRA)
        else:
            # 灰度图或其他格式
            open_cv_image = np.array(pil_image)
        return open_cv_image
    except Exception as e:
        logger.error(f"使用PIL读取图片失败: {path}, 错误: {e}")
        return None


def convert_chinese_numbers(text):
    """
    转换中文数字表示（如：1.5万）为实际数值，始终返回 int
    """
    if text is None or text == '':
        return 0
    text = str(text).replace(',', '')
    if '万' in text:
        number_part = re.sub(r'[^\d.]', '', text)
        try:
            number = float(number_part)
            return int(number * 10000)
        except ValueError:
            return 0
    try:
        return int(float(text))
    except (ValueError, TypeError):
        return 0


if __name__ == "__main__":
    process_images()
    # 开始同步识别后的数据
    # sync_explore_data_to_remote(['s_xhs_data_overview_ocr', 's_xhs_traffic_analysis_ocr'])
