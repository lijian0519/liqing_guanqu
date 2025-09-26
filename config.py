#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class Config:
    """基础配置类 - 定义应用程序的核心配置参数
    
    此类包含应用程序的基础配置，包括Web服务器设置、MQTT连接参数、
    数据存储配置和监控参数。所有配置都可以通过环境变量进行覆盖，
    提供了灵活的部署选项。
    """
    # Web服务器配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'  # 密钥，生产环境应使用强密钥
    DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'      # 默认启用调试模式
    HOST = os.environ.get('HOST', '0.0.0.0')                       # 默认主机地址
    PORT = int(os.environ.get('PORT', 5000))                       # 默认端口
    
    # MQTT配置
    MQTT_BROKER_URL = os.environ.get('MQTT_HOST', 'localhost')     # MQTT服务器地址
    MQTT_BROKER_PORT = int(os.environ.get('MQTT_PORT', 1883))      # MQTT服务器端口
    MQTT_USERNAME = os.environ.get('MQTT_USERNAME', '')            # MQTT用户名
    MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD', '')            # MQTT密码
    # 客户端ID配置
    # 优先使用环境变量中的MQTT_FIXED_CLIENT_ID，如果没有则使用MQTT_CLIENT_ID，最后才使用默认值
    MQTT_CLIENT_ID = os.environ.get('MQTT_FIXED_CLIENT_ID') or os.environ.get('MQTT_CLIENT_ID', 'web_interface_client')
    MQTT_KEEPALIVE = int(os.environ.get('MQTT_KEEPALIVE', 60))      # 心跳间隔（秒）
    MQTT_TLS_ENABLED = os.environ.get('MQTT_USE_TLS', 'False').lower() == 'true'  # 是否启用TLS
    MQTT_USE_WEBSOCKETS = os.environ.get('MQTT_USE_WEBSOCKETS', 'False').lower() == 'true'  # 是否使用WebSocket
    MQTT_WEBSOCKET_PATH = os.environ.get('MQTT_WEBSOCKET_PATH', '/mqtt')  # WebSocket路径
    
    # MQTT主题配置
    MQTT_TOPICS = {
        'tank_data': os.environ.get('MQTT_TOPIC_TANK_DATA', 'tanks/data'),      # 罐数据主题
        'control': os.environ.get('MQTT_TOPIC_CONTROL', 'tanks/adjustments'),    # 控制命令主题
        'error': os.environ.get('MQTT_TOPIC_ERROR', 'tanks/error'),              # 错误信息主题
        'adjustments': os.environ.get('MQTT_TOPIC_ADJUSTMENTS', 'tanks/adjustments')  # 调整命令主题
    }
    
    # 数据存储配置
    DATA_FOLDER = os.environ.get('DATA_DIR', 'data')                 # 数据存储目录
    ERROR_DATA_FILE = os.path.join(DATA_FOLDER, 'tank_error_data.json')
    SUBSCRIBED_DATA_FILE = os.path.join(DATA_FOLDER, 'subscribed_mqtt_data.json')
    HISTORY_FILE = os.path.join(DATA_FOLDER, os.environ.get('HISTORY_FILE', 'tank_history.json'))  # 历史数据文件名
    MAX_HISTORY_POINTS = int(os.environ.get('MAX_HISTORY_POINTS', 1000))  # 最大历史数据点
    
    # 监控配置
    MAX_TANKS = int(os.environ.get('MAX_TANKS', 11))                 # 最大罐数量
    DEFAULT_TANK_HEIGHT = float(os.environ.get('DEFAULT_TANK_HEIGHT', 8.0))  # 默认罐高度（米）
    HIGH_LEVEL_THRESHOLD_PERCENTAGE = float(os.environ.get('HIGH_LEVEL_THRESHOLD_PERCENTAGE', 0.8))  # 高液位报警阈值（80%）
    
    # 日志配置
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')  # 日志级别
    LOG_FILE = os.environ.get('LOG_FILE', 'mqtt_web_interface.log')  # 日志文件名

class DevelopmentConfig(Config):
    """开发环境配置 - 针对开发环境优化的配置
    
    此类继承自基础配置类，启用调试模式以便于开发和问题排查。
    """
    DEBUG = True
    LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
    """生产环境配置 - 针对生产环境优化的配置
    
    此类继承自基础配置类，禁用调试模式，调整日志级别为INFO，
    并将主机地址设置为0.0.0.0以允许外部访问。
    """
    DEBUG = False
    LOG_LEVEL = 'INFO'

# 从环境变量中获取配置名称，默认为开发环境
config_name = os.environ.get('CONFIG_NAME', 'development')

# 根据配置名称选择相应的配置类
try:
    config_map = {
        'development': DevelopmentConfig,
        'production': ProductionConfig
    }
    current_config = config_map.get(config_name, DevelopmentConfig)
    
    # 记录当前使用的配置
    # 注意：不要在日志中输出敏感信息
    print(f"正在使用配置: {config_name}")
except Exception as e:
    print(f"配置加载失败: {str(e)}")
    # 回退到开发环境配置作为安全选项
    current_config = DevelopmentConfig()