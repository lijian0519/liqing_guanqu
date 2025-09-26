#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# 导入必要的模块
import os
import sys
import json
import logging
import time
import signal
from datetime import datetime

# 导入Flask相关模块
from flask import Flask, render_template, jsonify, request, make_response
from flask_socketio import SocketIO, emit

# 设置默认编码为UTF-8
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 导入配置
from config import current_config

# 导入数据管理器
from data_manager import DataManager

# 导入标准MQTT客户端
import paho.mqtt.client as mqtt

# 初始化Flask应用
app = Flask(__name__)
app.config.from_object(current_config)

# 添加响应拦截器，确保所有响应都设置正确的编码
@app.after_request
def set_response_encoding(response):
    """确保所有响应都使用UTF-8编码"""
    if 'Content-Type' in response.headers and 'text/' in response.headers['Content-Type']:
        response.headers['Content-Type'] += '; charset=utf-8'
    elif 'Content-Type' not in response.headers:
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

# 初始化SocketIO，用于实时通信
socketio = SocketIO(app, cors_allowed_origins="*")

# 配置日志
logging.basicConfig(
    level=getattr(logging, current_config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(current_config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('MQTTWebInterface')

# 初始化全局变量
mqtt_client_instance = None
tank_data = {}
# MQTT连接状态
is_connected = False

# 确保数据目录存在
data_dir = os.path.join(os.path.dirname(__file__), current_config.DATA_FOLDER)
os.makedirs(data_dir, exist_ok=True)

# 初始化罐数据
def initialize_tanks():
    """初始化罐数据结构"""
    tanks = {}
    for i in range(1, current_config.MAX_TANKS + 1):
        tanks[i] = {
            'id': i,
            'name': f'{i}#沥青罐',
            'temperature': 0.0,
            'level': 0.0,
            'weight': 0.0,
            'height': current_config.DEFAULT_TANK_HEIGHT,
            'high_limit': current_config.DEFAULT_TANK_HEIGHT * current_config.HIGH_LEVEL_THRESHOLD_PERCENTAGE,
            'alarm_shown': False,
            'error': 0.0
        }
    return tanks

# 初始化罐数据
tank_data = initialize_tanks()

# MQTT回调函数
def on_mqtt_connect(client, userdata, flags, rc):
    """MQTT连接回调函数
    当客户端连接到MQTT服务器时被调用，处理连接状态更新和主题订阅
    
    Args:
        client: MQTT客户端实例
        userdata: 用户数据
        flags: 连接标志
        rc: 连接返回码，0表示成功连接
    """
    global is_connected
    if rc == 0:
        logger.info(f"成功连接到MQTT服务器")
        is_connected = True
        # 发送连接状态到前端
        socketio.emit('mqtt_status', {'connected': True, 'message': '已连接到MQTT服务器'})
        # 订阅主题
        client.subscribe(current_config.MQTT_TOPICS['tank_data'], qos=0)
        client.subscribe(current_config.MQTT_TOPICS['adjustments'], qos=0)
    else:
        is_connected = False
        # 定义返回码含义字典
        rc_meanings = {
            1: "连接被拒绝 - 协议版本不支持",
            2: "连接被拒绝 - 客户端ID无效",
            3: "连接被拒绝 - 服务器不可用",
            4: "连接被拒绝 - 用户名或密码错误",
            5: "连接被拒绝 - 未授权",
            7: "连接被服务器拒绝 - 客户端标识符无效"
        }
        
        # 获取返回码含义
        rc_message = rc_meanings.get(rc, f"未知返回码: {rc}")
        logger.error(f"MQTT连接失败: {rc_message}")
        socketio.emit('mqtt_status', {'connected': False, 'message': f'连接失败: {rc_message}'})


def on_mqtt_disconnect(client, userdata, rc):
    """MQTT断开连接回调函数
    当客户端与MQTT服务器断开连接时被调用，更新连接状态
    
    Args:
        client: MQTT客户端实例
        userdata: 用户数据
        rc: 断开连接返回码，0表示正常断开
    """
    global is_connected
    is_connected = False
    if rc != 0:
        logger.warning(f"MQTT连接意外断开，返回码: {rc}")
    else:
        logger.info("MQTT连接正常断开")
    socketio.emit('mqtt_status', {'connected': False, 'message': 'MQTT连接已断开'})


def on_mqtt_message(client, userdata, msg):
    """MQTT消息接收回调函数
    当客户端接收到MQTT消息时被调用，处理不同主题的消息
    
    Args:
        client: MQTT客户端实例
        userdata: 用户数据
        msg: MQTT消息对象，包含topic和payload
    """
    try:
        # 尝试解析JSON消息
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
        
        # 添加更详细的接收数据日志
        logger.info(f"[MQTT接收] 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}, 主题: {msg.topic}, 负载: {json.dumps(data, ensure_ascii=False)}")
        
        # 处理罐数据
        if msg.topic == current_config.MQTT_TOPICS['tank_data']:
            # 支持两种格式：
            # 1. {"tanks": [{...}, {...}]} - 带有tanks键的格式
            # 2. [{...}, {...}] 或 {...} - 直接的列表或字典格式
            if isinstance(data, dict) and 'tanks' in data:
                # 提取tanks列表并处理
                update_tank_data(data['tanks'])
            else:
                # 处理原始格式
                update_tank_data(data)
            logger.debug(f"处理罐数据 - 主题: {msg.topic}")
        
        # 处理误差调整数据
        elif msg.topic == current_config.MQTT_TOPICS['adjustments']:
            update_tank_adjustments(data)
            logger.debug(f"处理误差调整数据 - 主题: {msg.topic}")
        
        # 发送消息到WebSocket客户端
        socketio.emit('mqtt_message', {
            'topic': msg.topic,
            'payload': data
        })
        
        # 记录日志
        logger.debug(f"收到消息 - 主题: {msg.topic}, 负载: {payload[:100]}...")
    except Exception as e:
        logger.error(f"处理MQTT消息时出错: {str(e)}")

def update_tank_adjustments(data):
    """更新罐的误差调整值"""
    global tank_data
    try:
        logger.debug(f"收到误差调整数据: {data}")
        
        # 检查数据格式
        if isinstance(data, dict) and 'adjustments' in data:
            adjustments = data['adjustments']
            logger.debug(f"处理{len(adjustments)}个误差调整值")
            
            # 处理每个调整值
            for i, adjustment in enumerate(adjustments):
                tank_id = i + 1  # 索引从0开始，罐ID从1开始
                
                if 1 <= tank_id <= current_config.MAX_TANKS:
                    adjustment_factor = float(adjustment.get('adjustmentFactor', 0))
                    logger.debug(f"更新罐{tank_id}的误差值为: {adjustment_factor}")
                    
                    # 更新罐的误差值
                    if tank_id in tank_data:
                        tank_data[tank_id]['error'] = adjustment_factor
            
            # 保存更新后的误差数据
            save_error_data()
            
            # 通知前端数据已更新
            socketio.emit('tank_data_update', tank_data)
            logger.info(f"已成功更新{min(len(adjustments), current_config.MAX_TANKS)}个罐的误差值")
        else:
            logger.warning(f"收到的误差调整数据格式不正确: {data}")
    except Exception as e:
        logger.error(f"处理误差调整数据时出错: {str(e)}")

def update_tank_data(data):
    """更新罐数据"""
    global tank_data
    
    try:
        # 检查数据格式是否正确
        if isinstance(data, dict):
            # 检查是否是带有tanks键的格式
            if 'tanks' in data:
                logger.debug(f"处理带有tanks键的字典格式数据")
                update_tank_data(data['tanks'])
            else:
                # 处理单罐数据
                logger.debug(f"处理单罐数据")
                process_tank_data(data)
        elif isinstance(data, list):
            # 处理多罐数据
            logger.debug(f"处理多罐数据列表，包含{len(data)}个罐")
            
            # 对于用户提供的格式（没有id字段的列表），使用索引作为id
            if data and isinstance(data[0], dict) and 'id' not in data[0]:
                logger.debug(f"处理没有id字段的列表格式数据")
                # 假设列表顺序对应罐1到罐11
                for i, tank in enumerate(data):
                    tank_id = i + 1  # 索引从0开始，罐ID从1开始
                    if 1 <= tank_id <= current_config.MAX_TANKS:
                        tank_with_id = tank.copy()
                        tank_with_id['id'] = tank_id
                        logger.debug(f"为罐{i+1}添加ID并处理数据: {tank_with_id}")
                        process_tank_data(tank_with_id)
            else:
                # 对于有id字段的列表，直接处理
                logger.debug(f"处理有id字段的列表格式数据")
                for tank in data:
                    process_tank_data(tank)
        
        # 发送更新后的罐数据到WebSocket客户端
        socketio.emit('tank_data_update', tank_data)
        
        # 保存数据到文件
        save_subscribed_data()
    except Exception as e:
        logger.error(f"更新罐数据时出错: {str(e)}")

def process_tank_data(data):
    """处理单个罐的数据"""
    global tank_data
    
    try:
        tank_id = int(data.get('id', 0))
        # 使用info级别并添加时间戳，记录详细的罐数据处理过程
        logger.info(f"[罐数据处理] 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}, ID: {tank_id}, 原始数据: {json.dumps(data, ensure_ascii=False)}")
        if tank_id in tank_data:
            # 更新罐数据
            if 'temperature' in data:
                tank_data[tank_id]['temperature'] = float(data['temperature'])
            if 'level' in data:
                # 不再应用误差调整，直接使用原始液位值
                level = float(data['level'])
                tank_data[tank_id]['level'] = level
                logger.info(f"[罐数据处理] 罐{tank_id}: 更新液位值为 {level}")
            if 'weight' in data:
                tank_data[tank_id]['weight'] = float(data['weight'])
            
            # 添加对高限数据的处理，允许通过订阅信息修改高限
            if 'high_limit' in data:
                new_high_limit = float(data['high_limit'])
                logger.info(f"[罐数据处理] 罐{tank_id}: 更新高限数据 (high_limit) 为 {new_high_limit}")
                tank_data[tank_id]['high_limit'] = new_high_limit
            elif 'levelHighLimit' in data:  # 兼容旧格式的高限字段
                new_high_limit = float(data['levelHighLimit'])
                logger.info(f"[罐数据处理] 罐{tank_id}: 更新高限数据 (levelHighLimit) 为 {new_high_limit}")
                tank_data[tank_id]['high_limit'] = new_high_limit
            
            # 检查是否需要报警
            check_alarm(tank_id)
            logger.info(f"[罐数据处理] 罐{tank_id}: 处理完成，更新后数据: {json.dumps(tank_data[tank_id], ensure_ascii=False)}")
        else:
            logger.warning(f"罐ID {tank_id} 不存在")
    except Exception as e:
        logger.error(f"处理单个罐数据时出错: {str(e)}")

def check_alarm(tank_id):
    """检查是否需要报警"""
    if tank_id in tank_data:
        tank = tank_data[tank_id]
        if tank['level'] > tank['high_limit'] and not tank['alarm_shown']:
            tank['alarm_shown'] = True
            socketio.emit('alarm', {
                'tank_id': tank_id,
                'tank_name': tank['name'],
                'level': tank['level'],
                'high_limit': tank['high_limit']
            })
        elif tank['level'] <= tank['high_limit'] and tank['alarm_shown']:
            tank['alarm_shown'] = False

def save_subscribed_data():
    """保存订阅的数据到文件"""
    try:
        with open(current_config.SUBSCRIBED_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(tank_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存订阅数据时出错: {str(e)}")

def load_subscribed_data():
    """从文件加载订阅的数据"""
    global tank_data
    try:
        if os.path.exists(current_config.SUBSCRIBED_DATA_FILE):
            with open(current_config.SUBSCRIBED_DATA_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                # 合并加载的数据，但保留初始结构
                for tank_id, tank_info in loaded_data.items():
                    # 确保tank_id可以转换为整数
                    try:
                        tank_id_int = int(tank_id)
                        if tank_id_int in tank_data:
                            for key, value in tank_info.items():
                                if key in tank_data[tank_id_int]:
                                    tank_data[tank_id_int][key] = value
                    except ValueError:
                        logger.warning(f"跳过无效的罐ID: {tank_id}")
    except Exception as e:
        logger.error(f"加载订阅数据时出错: {str(e)}")

# 初始化MQTT客户端
def initialize_mqtt_client():
    """初始化MQTT客户端"""
    global mqtt_client_instance, is_connected
    
    try:
        # 优先使用环境变量中的MQTT_HOST和MQTT_PORT，兼容测试脚本的配置
        mqtt_host = os.environ.get('MQTT_HOST', current_config.MQTT_BROKER_URL)
        mqtt_port = int(os.environ.get('MQTT_PORT', str(current_config.MQTT_BROKER_PORT)))
        
        # 检查并设置TLS，确保与测试脚本一致
        use_tls = os.environ.get('MQTT_USE_TLS', str(current_config.MQTT_TLS_ENABLED).lower()).lower() == 'true'
        
        # 打印调试信息，确认当前使用的配置值
        logger.debug(f"[配置调试] MQTT_HOST: {mqtt_host}")
        logger.debug(f"[配置调试] MQTT_PORT: {mqtt_port}")
        logger.debug(f"[配置调试] MQTT_USE_TLS: {use_tls}")
        logger.debug(f"[配置调试] MQTT_USERNAME: {current_config.MQTT_USERNAME}")
        logger.debug(f"[配置调试] MQTT_PASSWORD: {'******' if current_config.MQTT_PASSWORD else '空'}")
        
        # 从环境变量获取WebSocket相关配置，如果没有则使用默认值
        use_websockets = os.environ.get('MQTT_USE_WEBSOCKETS', 'False').lower() == 'true'
        websocket_path = os.environ.get('MQTT_WEBSOCKET_PATH', '/mqtt')
        
        # 检查是否需要使用WebSocket（如果启用了TLS且端口是8084）
        if use_tls and mqtt_port == 8084:
            use_websockets = True
            logger.info(f"自动启用MQTT over WebSocket连接 (TLS + 端口8084)")
        
        if use_websockets:
            logger.info(f"正在使用MQTT over WebSocket连接到 {mqtt_host}:{mqtt_port}{websocket_path}")
        else:
            logger.info(f"正在使用MQTT TCP连接到 {mqtt_host}:{mqtt_port}, TLS: {use_tls}")
        
        # 创建标准MQTT客户端实例
        # 总是使用时间戳生成动态客户端ID，避免多实例冲突和固定ID问题
        client_id = f"mqtt_web_interface_{int(time.time())}_{os.urandom(4).hex()}"
        logger.info(f"使用动态生成的MQTT客户端ID: {client_id}")
        
        # 创建MQTT客户端，使用MQTT v3.1.1，这是与大多数MQTT服务器兼容的稳定版本
        mqtt_client_instance = mqtt.Client(client_id=client_id, clean_session=True, protocol=mqtt.MQTTv311)
        
        # 设置回调函数
        mqtt_client_instance.on_connect = on_mqtt_connect
        mqtt_client_instance.on_disconnect = on_mqtt_disconnect
        mqtt_client_instance.on_message = on_mqtt_message
        
        # 配置自动重连策略 - 更保守的重连策略（兼容旧版本paho-mqtt）
        mqtt_client_instance.reconnect_delay_set(min_delay=2, max_delay=30)
        # 注意：enable_bridge_mode()可能在某些paho-mqtt版本中不可用，这里不使用它
        
        # 设置心跳包频率，确保与服务器保持活跃连接
        keepalive = int(os.environ.get('MQTT_KEEPALIVE', str(current_config.MQTT_KEEPALIVE)))
        logger.debug(f"[配置调试] MQTT_KEEPALIVE: {keepalive}")
        
        # 设置用户名和密码 - 直接从环境变量获取，确保与run.py中的设置一致
        mqtt_username = os.environ.get('MQTT_USERNAME', current_config.MQTT_USERNAME)
        mqtt_password = os.environ.get('MQTT_PASSWORD', current_config.MQTT_PASSWORD)
        if mqtt_username:
            mqtt_client_instance.username_pw_set(username=mqtt_username, password=mqtt_password)
            logger.info(f"已设置MQTT用户名: {mqtt_username}")
        
        # 配置TLS - 更健壮的TLS配置
        if use_tls:
            try:
                # 为EMQX Cloud配置TLS
                mqtt_client_instance.tls_set(
                    ca_certs=None,  # 使用系统默认CA证书
                    certfile=None,  # 客户端证书（如果需要）
                    keyfile=None,   # 客户端私钥（如果需要）
                    cert_reqs=mqtt.ssl.CERT_NONE,  # 不验证服务器证书
                    tls_version=mqtt.ssl.PROTOCOL_TLS_CLIENT,  # 使用自动选择的TLS版本
                    ciphers=None  # 使用默认密码套件
                )
                # 允许自签名证书 - 这对于EMQX Cloud是必要的
                mqtt_client_instance.tls_insecure_set(True)
                logger.info("TLS配置已完成，已设置允许自签名证书")
            except Exception as e:
                logger.error(f"配置TLS时出错: {str(e)}")
                # 如果TLS配置失败，尝试不使用TLS重新连接
                logger.warning("尝试在不使用TLS的情况下重新连接...")
                use_tls = False
        
        # 连接到MQTT服务器
        try:
            logger.info(f"正在连接到MQTT服务器: {mqtt_host}:{mqtt_port}")
            # 使用更保守的连接参数
            mqtt_client_instance.connect(
                host=mqtt_host,
                port=mqtt_port,
                keepalive=keepalive
            )
            
            # 启动网络循环（非阻塞模式）
            mqtt_client_instance.loop_start()
            logger.info("MQTT客户端已启动")
            
            # 连接后等待一小段时间，确保连接稳定
            time.sleep(1)
        except Exception as e:
            logger.error(f"连接MQTT服务器失败: {str(e)}")
            socketio.emit('mqtt_status', {'connected': False, 'message': f'连接MQTT服务器失败: {str(e)}'})
    except Exception as e:
        logger.error(f"初始化MQTT客户端时出错: {str(e)}")
        # 添加错误状态通知到前端
        socketio.emit('mqtt_status', {'connected': False, 'message': f'初始化MQTT客户端失败: {str(e)}'})

# Flask路由
@app.route('/')
def index():
    """首页路由"""
    # 检查MQTT客户端实例是否存在并获取连接状态
    return render_template('index.html', tanks=tank_data, mqtt_connected=is_connected)

@app.route('/api/tanks')
def get_tanks():
    """获取所有罐数据的API"""
    return jsonify(tank_data)

@app.route('/api/mqtt/status')
def get_mqtt_status():
    """获取MQTT连接状态的API"""
    global is_connected
    subscribed_topics = []
    if mqtt_client_instance and is_connected:
        # 获取已订阅的主题列表
        try:
            # 由于我们使用标准客户端，这里简化处理
            subscribed_topics = [
                {'topic': current_config.MQTT_TOPICS['tank_data'], 'qos': 0},
                {'topic': current_config.MQTT_TOPICS['adjustments'], 'qos': 0}
            ]
        except:
            pass
        
        return jsonify({
            'connected': is_connected,
            'topics': subscribed_topics,
            'broker': current_config.MQTT_BROKER_URL
        })
    return jsonify({
        'connected': is_connected,
        'topics': [],
        'broker': current_config.MQTT_BROKER_URL
    })

@app.route('/api/storage/days', methods=['GET'])
def get_storage_days():
    """获取数据存储天数"""
    days = data_manager.get_storage_days()
    return jsonify({
        'storage_days': days
    })

@app.route('/api/storage/days', methods=['POST'])
def set_storage_days():
    """设置数据存储天数"""
    try:
        data = request.json
        days = int(data.get('days', 7))
        updated_days = data_manager.set_storage_days(days)
        return jsonify({
            'success': True,
            'storage_days': updated_days
        })
    except Exception as e:
        logger.error(f"设置存储天数时出错: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/history/points', methods=['GET'])
def get_history_points():
    """获取历史数据点数量设置"""
    points = data_manager.get_max_history_points()
    return jsonify({
        'history_points': points
    })

@app.route('/api/history/points', methods=['POST'])
def set_history_points():
    """设置历史数据点数量"""
    try:
        data = request.json
        points = int(data.get('points', 10000))
        updated_points = data_manager.set_max_history_points(points)
        return jsonify({
            'success': True,
            'history_points': updated_points
        })
    except Exception as e:
        logger.error(f"设置历史数据点数量时出错: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/history/<tank_id>', methods=['GET'])
def get_tank_history(tank_id):
    """获取特定罐的历史数据
    
    可选参数:
    - start_time: 开始时间（ISO格式字符串）
    - end_time: 结束时间（ISO格式字符串）
    - limit: 返回的数据点数量限制
    """
    try:
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        limit = request.args.get('limit', type=int)
        
        history_data = data_manager.get_tank_history(tank_id, start_time, end_time, limit)
        
        return jsonify({
            'success': True,
            'tank_id': tank_id,
            'history': history_data
        })
    except Exception as e:
        logger.error(f"获取历史数据时出错: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

# 确保data_manager在全局作用域中可用
data_manager = None

# WebSocket事件处理
@socketio.on('connect')
def handle_connect():
    """处理WebSocket客户端连接
    当客户端连接到WebSocket时，发送初始罐数据和MQTT连接状态
    """
    logger.info("WebSocket客户端已连接")
    # 发送初始罐数据到客户端
    emit('tank_data_update', tank_data)
    # 发送当前MQTT连接状态到客户端
    global is_connected
    emit('mqtt_status', {'connected': is_connected})

@socketio.on('disconnect')
def handle_disconnect():
    """处理WebSocket断开连接"""
    logger.info("WebSocket客户端已断开连接")

# 误差处理相关函数
@app.route('/api/tank/<int:tank_id>/error', methods=['POST'])
def update_tank_error(tank_id):
    """更新罐的误差值并通过MQTT发布，支持3位小数点精度，最大调整值为罐的高度"""
    try:
        data = request.get_json()
        error = float(data.get('error', 0))
        
        if tank_id in tank_data:
            # 获取罐的高度
            tank_height = tank_data[tank_id]['height']
            
            # 限制误差值精度为3位小数
            error = round(error, 3)
            
            # 限制误差值不超过罐的高度
            if abs(error) > tank_height:
                error = tank_height if error > 0 else -tank_height
                logger.warning(f"误差值 {error} 超过了罐 {tank_id} 的高度 {tank_height}，已自动调整")
            
            tank_data[tank_id]['error'] = error
            # 保存误差数据
            save_error_data()
            
            # 发布所有罐的误差数据到MQTT
            if mqtt_client_instance and is_connected:
                # 构建误差调整数据格式
                adjustments_data = {
                    'adjustments': []
                }
                for i in range(1, current_config.MAX_TANKS + 1):
                    adjustment = {
                        'adjustmentFactor': tank_data[i]['error'] if i in tank_data else 0.0
                    }
                    adjustments_data['adjustments'].append(adjustment)
                
                # 发布到MQTT主题
                topic = current_config.MQTT_TOPICS.get('adjustments', 'tanks/adjustments')
                payload = json.dumps(adjustments_data)
                mqtt_client_instance.publish(topic, payload, qos=1)
                logger.info(f"[MQTT发布] 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}, 主题: {topic}, 负载: 误差调整数据")
            
            return jsonify({'success': True, 'message': f'罐 {tank_id} 的误差值已更新为 {error}（3位小数，最大为罐高度 {tank_height}），并通过MQTT发布'})
        else:
            return jsonify({'success': False, 'message': f'罐 {tank_id} 不存在'}), 404
    except Exception as e:
        logger.error(f"更新罐误差值时出错: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

def save_error_data():
    """保存误差数据到文件"""
    try:
        error_data = {}
        for tank_id, tank_info in tank_data.items():
            error_data[tank_id] = tank_info.get('error', 0)
        
        with open(current_config.ERROR_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(error_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存误差数据时出错: {str(e)}")

def load_error_data():
    """从文件加载误差数据"""
    try:
        if os.path.exists(current_config.ERROR_DATA_FILE):
            with open(current_config.ERROR_DATA_FILE, 'r', encoding='utf-8') as f:
                error_data = json.load(f)
                for tank_id, error in error_data.items():
                    tank_id_int = int(tank_id)
                    if tank_id_int in tank_data:
                        tank_data[tank_id_int]['error'] = float(error)
    except Exception as e:
        logger.error(f"加载误差数据时出错: {str(e)}")

# 初始化已订阅主题列表
subscribed_topics = []

# WebSocket事件处理 - 扩展
@socketio.on('subscribe_topic')
def handle_subscribe_topic(data):
    """处理订阅主题请求"""
    global mqtt_client_instance
    try:
        topic = data.get('topic')
        qos = data.get('qos', 1)
        
        if mqtt_client_instance and is_connected and topic:
            mqtt_client_instance.subscribe(topic, qos=qos)
            subscribed_topics.append(topic)
            logger.info(f"已订阅主题: {topic}")
            emit('subscription_status', {'success': True, 'message': f'已订阅主题: {topic}'})
        else:
            emit('subscription_status', {'success': False, 'message': '订阅失败，MQTT未连接或主题无效'})
    except Exception as e:
        logger.error(f"订阅主题时出错: {str(e)}")
        emit('subscription_status', {'success': False, 'message': str(e)})

@socketio.on('publish_message')
def handle_publish_message(data):
    """处理发布消息请求"""
    global mqtt_client_instance
    try:
        topic = data.get('topic')
        payload = data.get('payload', '')
        qos = data.get('qos', 1)
        retain = data.get('retain', False)
        
        if mqtt_client_instance and is_connected and topic:
            # 确保payload是字符串
            if isinstance(payload, dict):
                payload = json.dumps(payload)
            elif not isinstance(payload, str):
                payload = str(payload)
            
            mqtt_client_instance.publish(topic, payload, qos=qos, retain=retain)
            # 添加更详细的发布数据日志
            logger.info(f"[MQTT发布] 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}, 主题: {topic}, QoS: {qos}, 保留: {retain}, 负载: {payload}")
            
            # 特殊处理tanks/adjustments主题，确保发布后立即更新前端
            if topic == current_config.MQTT_TOPICS.get('adjustments', 'tanks/adjustments'):
                try:
                    # 解析发布的消息内容
                    adjustments_data = json.loads(payload)
                    # 直接调用update_tank_adjustments来更新数据并通知前端
                    update_tank_adjustments(adjustments_data)
                except Exception as e:
                    logger.error(f"处理发布的误差调整数据时出错: {str(e)}")
            
            emit('publish_status', {'success': True, 'message': '消息发布成功'})
        else:
            emit('publish_status', {'success': False, 'message': '发布失败，MQTT未连接或主题无效'})
    except Exception as e:
        logger.error(f"发布消息时出错: {str(e)}")
        emit('publish_status', {'success': False, 'message': str(e)})



# 获取当前罐数据的API端点
@app.route('/api/tanks/data')
def get_tanks_data():
    """获取当前所有罐数据的API端点"""
    try:
        global tank_data
        return jsonify({'success': True, 'data': tank_data})
    except Exception as e:
        logger.error(f"获取罐数据时出错: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# 初始化应用
def initialize_app():
    """初始化整个应用"""
    global data_manager
    logger.info("正在初始化MQTT Web界面监控系统...")
    
    # 加载之前保存的数据
    load_subscribed_data()
    load_error_data()
    
    # 初始化MQTT客户端
    initialize_mqtt_client()
    
    # 初始化数据管理器
    data_manager = DataManager(
        data_dir=current_config.DATA_FOLDER,
        history_file=current_config.HISTORY_FILE,
        storage_days=7
    )
    
    logger.info(f"应用已初始化，配置: {current_config.__class__.__name__}")

def cleanup_resources(signum=None, frame=None):
    """清理资源，在应用程序关闭时调用"""
    global mqtt_client_instance, is_connected
    logger.info("正在清理资源...")
    
    # 优雅地断开MQTT连接
    if mqtt_client_instance:
        try:
            logger.info("正在断开MQTT连接...")
            if is_connected:
                # 断开连接
                mqtt_client_instance.disconnect()
            
            # 停止MQTT循环
            mqtt_client_instance.loop_stop()
            is_connected = False
            logger.info("MQTT连接已断开")
        except Exception as e:
            logger.error(f"断开MQTT连接时出错: {str(e)}")
    
    logger.info("资源清理完成")

# 注册信号处理程序，捕获终止信号
if hasattr(signal, 'SIGINT'):
    signal.signal(signal.SIGINT, cleanup_resources)  # Ctrl+C
if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, cleanup_resources)  # 终止信号

# 在模块加载时自动初始化应用，确保无论是直接运行还是通过run.py导入都能正确初始化
initialize_app()

# 应用启动
if __name__ == '__main__':
    try:
        # 启动Flask应用和SocketIO
        logger.info(f"正在启动Web服务器，访问地址: http://{current_config.HOST}:{current_config.PORT}")
        socketio.run(app, host=current_config.HOST, port=current_config.PORT, debug=app.config['DEBUG'])
    finally:
        # 确保在应用退出时清理资源
        cleanup_resources()