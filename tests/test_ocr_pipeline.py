import unittest
from db import build_ocr_record, get_source_type


class TestOcrPipeline(unittest.TestCase):

    def test_get_source_type(self):
        self.assertEqual(get_source_type("xhs"), "1894230222988058625")
        self.assertEqual(get_source_type("weibo"), "1948663593734004737")
        self.assertEqual(get_source_type("tiktok"), "1866687481668411393")
        self.assertEqual(get_source_type("unknown"), "")

    def test_build_ocr_record(self):
        tag = "note_data_overview_top"
        post_title = "测试作品"
        note_link = "http://example.com/note/123"
        content_type = "图文"
        ocr_data = ["100", "50", "5.2%"]
        index_mapping = ["曝光数", "观看数", "封面点击率"]
        date_dir = "20251217"
        ip_port_dir = "192.168.1.1:5555"
        account_id = "test_acc"
        app_name = "xhs"

        record = build_ocr_record(
            tag, post_title, note_link, content_type,
            ocr_data, index_mapping, date_dir, ip_port_dir, account_id, app_name
        )

        self.assertEqual(record["数据来源"], "1894230222988058625")
        self.assertEqual(record["设备IP"], ip_port_dir)
        self.assertEqual(record["账号ID"], account_id)
        self.assertEqual(record["作品标题"], post_title)
        self.assertEqual(record["链接"], note_link)
        self.assertEqual(record["采集日期"], date_dir)
        self.assertEqual(record["内容类型"], content_type)
        self.assertEqual(record["曝光数"], "100")
        self.assertEqual(record["观看数"], "50")
        self.assertEqual(record["封面点击率"], "5.2%")

    def test_post_records_merging_in_memory(self):
        # 模拟同一帖子的 top 和 bottom 截图数据在内存中叠加
        post_records = {}

        # 1. 第一张图（top）
        top_record = build_ocr_record(
            tag="note_data_overview_top",
            post_title="大象帖",
            note_link="http://xhslink.com/1",
            content_type="图文",
            ocr_data=["1000", "500", "10%"],
            index_mapping_data=["曝光数", "观看数", "封面点击率"],
            date_dir="20251217",
            ip_port_dir="127.0.0.1:5555",
            account_id="acc1",
            app_name="xhs"
        )
        key = (top_record["链接"], top_record["作品标题"], top_record["账号ID"], top_record["采集日期"])
        if key not in post_records:
            post_records[key] = top_record
        else:
            for f, v in top_record.items():
                if v != '':
                    post_records[key][f] = v

        # 2. 第二张图（bottom）
        bottom_record = build_ocr_record(
            tag="note_data_overview_bottom",
            post_title="大象帖",
            note_link="http://xhslink.com/1",
            content_type="图文",
            ocr_data=["200", "30", "50", "10", "12s", "5"],
            index_mapping_data=["点赞数", "评论数", "收藏数", "分享数", "平均观看时长", "涨粉数"],
            date_dir="20251217",
            ip_port_dir="127.0.0.1:5555",
            account_id="acc1",
            app_name="xhs"
        )
        key2 = (bottom_record["链接"], bottom_record["作品标题"], bottom_record["账号ID"], bottom_record["采集日期"])
        if key2 not in post_records:
            post_records[key2] = bottom_record
        else:
            for f, v in bottom_record.items():
                if v != '':
                    post_records[key2][f] = v

        # 3. 验证融合结果只有 1 条记录，包含 top 和 bottom 的所有字段
        self.assertEqual(len(post_records), 1)
        merged = post_records[key]
        self.assertEqual(merged["作品标题"], "大象帖")
        self.assertEqual(merged["曝光数"], "1000")
        self.assertEqual(merged["观看数"], "500")
        self.assertEqual(merged["封面点击率"], "10%")
        self.assertEqual(merged["点赞数"], "200")
        self.assertEqual(merged["评论数"], "30")
        self.assertEqual(merged["收藏数"], "50")
        self.assertEqual(merged["分享数"], "10")
        self.assertEqual(merged["平均观看时长"], "12s")
        self.assertEqual(merged["涨粉数"], "5")

    def test_field_updates_on_same_post(self):
        # 测试同一作品多张截图的字段更新逻辑：
        # 图1 识别到点赞数=100
        # 图2 识别到观看时长=30s
        # 图3 识别到更新的点赞数=120
        # 最终合并结果应该具备最新的点赞数(120)和观看时长(30s)
        post_records = {}
        key = ("http://xhslink.com/test", "测试帖", "acc1", "20251217")

        # 1. 图1 (仅含点赞数)
        r1 = build_ocr_record(
            tag="note_data_overview_bottom",
            post_title="测试帖",
            note_link="http://xhslink.com/test",
            content_type="图文",
            ocr_data=["100"],
            index_mapping_data=["点赞数"],
            date_dir="20251217",
            ip_port_dir="127.0.0.1:5555",
            account_id="acc1",
            app_name="xhs"
        )
        post_records[key] = r1

        # 2. 图2 (仅含观看时长)
        r2 = build_ocr_record(
            tag="note_data_overview_bottom",
            post_title="测试帖",
            note_link="http://xhslink.com/test",
            content_type="图文",
            ocr_data=["30s"],
            index_mapping_data=["平均观看时长"],
            date_dir="20251217",
            ip_port_dir="127.0.0.1:5555",
            account_id="acc1",
            app_name="xhs"
        )
        for f, v in r2.items():
            if v != '':
                post_records[key][f] = v

        # 3. 图3 (点赞数更新为120)
        r3 = build_ocr_record(
            tag="note_data_overview_bottom",
            post_title="测试帖",
            note_link="http://xhslink.com/test",
            content_type="图文",
            ocr_data=["120"],
            index_mapping_data=["点赞数"],
            date_dir="20251217",
            ip_port_dir="127.0.0.1:5555",
            account_id="acc1",
            app_name="xhs"
        )
        for f, v in r3.items():
            if v != '':
                post_records[key][f] = v

        # 验证结果：只有一条记录，点赞数被更新为120，观看时长保留30s
        self.assertEqual(len(post_records), 1)
        self.assertEqual(post_records[key]["点赞数"], "120")
        self.assertEqual(post_records[key]["平均观看时长"], "30s")

    def test_validate_ocr_texts(self):
        from core.run import validate_ocr_texts

        # 1. 成功案例
        self.assertTrue(validate_ocr_texts(["100", "50", "5.2%"], ["曝光数", "观看数", "封面点击率"]))
        
        # 2. 数量不匹配
        self.assertFalse(validate_ocr_texts(["100", "50"], ["曝光数", "观看数", "封面点击率"]))

        # 3. 包含空值或纯空格
        self.assertFalse(validate_ocr_texts(["100", "", "5.2%"], ["曝光数", "观看数", "封面点击率"]))
        self.assertFalse(validate_ocr_texts(["100", "  ", "5.2%"], ["曝光数", "观看数", "封面点击率"]))

        # 4. 包含纯特殊噪音符号
        self.assertFalse(validate_ocr_texts(["100", "-", "5.2%"], ["曝光数", "观看数", "封面点击率"]))
        self.assertFalse(validate_ocr_texts(["~", "50", "5.2%"], ["曝光数", "观看数", "封面点击率"]))

        # 5. 数值/比例/时长字段不含数字 (包括纯中文、纯字母)
        self.assertFalse(validate_ocr_texts(["无数据", "50", "5.2%"], ["曝光数", "观看数", "封面点击率"]))
        self.assertFalse(validate_ocr_texts(["100", "50", "暂无"], ["曝光数", "观看数", "封面点击率"]))
        self.assertFalse(validate_ocr_texts(["abc", "50", "5.2%"], ["曝光数", "观看数", "封面点击率"]))
        self.assertFalse(validate_ocr_texts(["100", "XYZ", "5.2%"], ["曝光数", "观看数", "封面点击率"]))

        # 6. 非数值/纯文本字段可以不含数字
        self.assertTrue(validate_ocr_texts(["首页推荐"], ["观看来源-首页推荐"]))


if __name__ == "__main__":
    unittest.main()
