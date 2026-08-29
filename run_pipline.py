import os

from db.data_sync import sync_explore_data_to_remote
from db.pipeline import run_data_processing_pipeline
from dotenv import load_dotenv
load_dotenv()
if __name__ == "__main__":
    # 默认运行完整流水线
    # day = int(os.getenv("OCR_RECENT_DAYS", "2"))
    # run_data_processing_pipeline(days=day)

    # sync_explore_data_to_remote(['s_xhs_user_info_ocr', 's_xhs_data_overview_traffic_analysis']
    #                             , {"column": "采集日期", "days": 1},
    #                             unique_constraints={
    #                                 's_xhs_user_info_ocr': [ "账号ID", "采集时间"],
    #                                 's_xhs_data_overview_traffic_analysis': [ "账号ID", "采集时间","链接"]})
    #
    sync_explore_data_to_remote( table_name='s_xhs_data_overview_traffic_analysis'
                                ,remote_table_name='s_xhs_data_overview_traffic_analysis'
                                , time_filter={"column": "采集日期", "days": 1},
                                unique_constraints={
                                    's_xhs_data_overview_traffic_analysis': [ "账号ID", "采集时间","链接"]})
