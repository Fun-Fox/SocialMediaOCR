-- social_media.s_xhs_data_overview_traffic_analysis definition

CREATE TABLE `social_s_xhs_data_overview_traffic_analysis` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '自增ID 主键，非空',
  `device_ip` text COLLATE utf8mb4_unicode_ci COMMENT '设备IP',
  `account_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '平台账号',
  `source_type` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '应用appid',
  `url` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '小红书作品链接（短链）',
  `title` text COLLATE utf8mb4_unicode_ci COMMENT '作品标题',
  `type` text COLLATE utf8mb4_unicode_ci COMMENT '内容类型（图文、视频）',
  `collection_time` datetime DEFAULT NULL COMMENT '采集时间',
  `completion_rate` text COLLATE utf8mb4_unicode_ci COMMENT '完播率（视频才有）',
  `exposure_count` text COLLATE utf8mb4_unicode_ci COMMENT '曝光数',
  `view_count` text COLLATE utf8mb4_unicode_ci COMMENT '观看数',
  `click_rate` text COLLATE utf8mb4_unicode_ci COMMENT '点击率',
  `avg_watch_duration` text COLLATE utf8mb4_unicode_ci COMMENT '平均观看时长',
  `followers_gained` text COLLATE utf8mb4_unicode_ci COMMENT '涨粉数',
  `likes` text COLLATE utf8mb4_unicode_ci COMMENT '点赞数',
  `comments` text COLLATE utf8mb4_unicode_ci COMMENT '评论数',
  `collects` text COLLATE utf8mb4_unicode_ci COMMENT '收藏数',
  `shares` text COLLATE utf8mb4_unicode_ci COMMENT '分享数',
  `bullet` text COLLATE utf8mb4_unicode_ci COMMENT '弹幕数（视频才有）',
  `source_homepage` text COLLATE utf8mb4_unicode_ci COMMENT '观看来源-首页推荐',
  `exit_rate_2s` text COLLATE utf8mb4_unicode_ci COMMENT '2秒退出率',
  `post_remark` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '帖子备注',
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_constraint_url` (`url`)
) ENGINE=InnoDB AUTO_INCREMENT=1137 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='平台XHS数据概览_流量分析表';



-- social_media.social_s_xhs_user_info_ocr definition

CREATE TABLE `s_xhs_user_info_ocr` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键id',
  `nickname` text COLLATE utf8mb4_unicode_ci COMMENT '昵称',
  `device_ip` text COLLATE utf8mb4_unicode_ci COMMENT '设备id',
  `account_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '账号id',
  `source_type` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '应用id',
  `url` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '小红书主页链接',
  `follows` int DEFAULT '0' COMMENT '关注数',
  `interaction` int DEFAULT '0' COMMENT '获赞与收藏',
  `fans` int DEFAULT '0' COMMENT '粉丝数',
  `collection_time` datetime DEFAULT NULL COMMENT '采集时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_constraint_url` (`url`)
) ENGINE=InnoDB AUTO_INCREMENT=348 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;