#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import webbrowser
import argparse
import logging
from threading import Timer
from typing import Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('run_app')

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""MQTT Web界面启动脚本

该脚本是MQTT Web监控界面的主入口点，负责以下任务：
1. 创建.env环境配置文件（如果不存在）
2. 安装项目依赖（可选）
3. 解析命令行参数
4. 启动Flask Web应用

注意：敏感信息（如MQTT用户名和密码）应通过环境变量或.env文件提供，
避免在代码中硬编码这些信息。
"""

def create_env_file(env_path: str) -> None:
    """创建.env环境文件（如果不存在）
    
    该函数创建一个模板.env文件，包含所有必要的配置参数，但不包含实际的敏感信息。
    用户需要手动编辑此文件以提供MQTT连接凭据等敏感信息。
    
    Args:
        env_path: .env文件路径
    """
    if not os.path.exists(env_path):
        default_env_content = '''
# Web服务器配置
FLASK_APP=app.py
FLASK_ENV=development
FLASK_RUN_HOST=127.0.0.1
FLASK_RUN_PORT=5000

# MQTT配置
# 注意：请替换为实际的MQTT服务器连接信息
MQTT_BROKER_URL=localhost
MQTT_BROKER_PORT=1883
MQTT_CLIENT_ID=mqtt_web_interface_client
# 敏感信息 - 请替换为实际的MQTT凭据
# MQTT_USERNAME=your_mqtt_username
# MQTT_PASSWORD=your_mqtt_password
MQTT_TLS_ENABLED=False
MQTT_USE_WEBSOCKETS=False
MQTT_KEEPALIVE=60

# MQTT主题配置
MQTT_TOPIC_TANK_DATA=tanks/data
MQTT_TOPIC_ADJUSTMENTS=tanks/adjustments
MQTT_TOPIC_CONTROL=tanks/adjustments
MQTT_TOPIC_ERROR=tanks/error

# 数据配置
DATA_DIR=data
HISTORY_FILE=tank_history.json
MAX_HISTORY_POINTS=1000

# 日志配置
LOG_LEVEL=INFO

# 环境选择 (development/production)
CONFIG_NAME=development
'''.strip()
        
        try:
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write(default_env_content)
            logger.info(f"已创建.env文件: {env_path}")
        except Exception as e:
            logger.error(f"创建.env文件时出错: {str(e)}")

def open_browser(url: str, delay: int = 2) -> None:
    """延迟打开浏览器
    
    该函数在指定的延迟时间后打开Web浏览器访问指定的URL。
    主要用于在应用启动后自动打开用户界面，提升用户体验。
    
    Args:
        url: 要打开的URL地址
        delay: 延迟秒数，默认值为2（秒）
    """
    def _open():
        try:
            webbrowser.open(url)
            logger.info(f"已打开浏览器访问: {url}")
        except Exception as e:
            logger.warning(f"无法打开浏览器: {str(e)}")
            logger.info(f"请手动访问以下地址: {url}")
    
    if delay > 0:
        logger.info(f"{delay}秒后打开浏览器...")
        Timer(delay, _open).start()
    else:
        _open()

# 标记为已移除的函数，仅用于兼容性目的
# 不再支持自动安装依赖，推荐用户手动安装所有必要的依赖包
def install_dependencies() -> bool:
    """安装项目依赖（已废弃）
    
    注意：该函数已废弃。为了确保依赖版本的一致性和安全性，
    建议用户手动安装所有必要的依赖包。
    
    Returns:
        bool: 始终返回True，用于保持向后兼容性
    """
    logger.warning("install_dependencies函数已废弃。请手动安装所有必要的依赖包。")
    logger.info("建议安装的依赖: Flask, paho-mqtt")
    return True

def run_app(args: argparse.Namespace) -> None:
    """运行Flask应用
    
    该函数是应用程序的核心启动函数，负责：
    1. 设置运行环境变量
    2. 导入和配置Flask应用
    3. 启动Web服务器
    
    Args:
        args: 解析后的命令行参数
    """
    try:
        # 尊重已有的环境变量设置，仅在未设置时使用命令行参数
        if 'CONFIG_NAME' not in os.environ:
            os.environ['CONFIG_NAME'] = args.env
        
        # 记录当前运行环境
        config_name = os.environ.get('CONFIG_NAME', 'development')
        logger.info(f"应用运行配置: {config_name}")
        
        # 如果设置了固定的MQTT客户端ID，记录信息
        if 'MQTT_FIXED_CLIENT_ID' in os.environ:
            logger.info(f"使用固定MQTT客户端ID: {os.environ['MQTT_FIXED_CLIENT_ID']}")
        
        # 导入Flask应用（延迟导入以提高启动速度）
        from app import app
        
        # 构建URL
        url = f"http://{args.host}:{args.port}"
        
        # 如果是开发环境且配置了自动打开浏览器，则打开浏览器
        if args.env == 'development' and args.open_browser:
            open_browser(url, delay=2)
        
        logger.info(f"正在启动Web应用 - 访问地址: {url}")
        logger.info("按Ctrl+C停止服务器")
        
        # 运行Flask应用
        app.run(host=args.host, port=args.port, debug=(args.env == 'development'))
        
    except ImportError as e:
        logger.error(f"导入模块时出错: {str(e)}")
        logger.info("请确保已安装所有依赖")
        sys.exit(1)
    except Exception as e:
        logger.error(f"启动应用时出错: {str(e)}")
        sys.exit(1)

def parse_arguments() -> argparse.Namespace:
    """解析命令行参数
    
    该函数设置并解析应用程序的命令行参数，包括运行环境、服务器配置和浏览器行为。
    
    Returns:
        argparse.Namespace: 包含所有解析后命令行参数的命名空间对象
    """
    parser = argparse.ArgumentParser(description='启动MQTT Web监控界面')
    
    # 环境配置
    default_env = os.environ.get('CONFIG_NAME', 'development')
    parser.add_argument('--env', type=str, default=default_env, choices=['development', 'production'],
                        help='运行环境 (默认: 从环境变量CONFIG_NAME获取，否则为development)')
    
    # 服务器配置
    parser.add_argument('--host', type=str, default='127.0.0.1',
                        help='服务器主机地址 (默认: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=5000,
                        help='服务器端口 (默认: 5000)')
    
    # 浏览器配置
    parser.add_argument('--open-browser', action='store_true', default=True,
                        help='自动打开浏览器 (默认: True)')
    parser.add_argument('--no-open-browser', dest='open_browser', action='store_false',
                        help='不自动打开浏览器')
    
    # 依赖配置（已废弃）
    parser.add_argument('--install-deps', action='store_true', default=False,
                        help='安装项目依赖（已废弃） (默认: False)')
    
    return parser.parse_args()

def main() -> None:
    """应用程序主入口函数
    
    该函数是整个应用程序的入口点，负责协调以下任务：
    1. 解析命令行参数
    2. 创建.env环境配置文件（如果不存在）
    3. （可选）安装项目依赖（已废弃）
    4. 启动Flask Web应用
    """
    # 解析命令行参数
    args = parse_arguments()
    
    # 获取当前目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 创建.env文件（如果不存在）
    env_path = os.path.join(current_dir, '.env')
    create_env_file(env_path)
    
    # 安装依赖（如果需要）
    if args.install_deps:
        # 尽管函数已废弃，但仍保持对该参数的支持
        install_dependencies()
    
    # 运行应用
    run_app(args)

if __name__ == '__main__':
    main()