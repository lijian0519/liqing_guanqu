#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import random
import paho.mqtt.client as mqtt

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 从环境变量加载配置（兼容现有的.env配置）
MQTT_BROKER_URL = os.environ.get('MQTT_BROKER_URL', 'facf0536.ala.cn-hangzhou.emqxsl.cn')
MQTT_BROKER_PORT = int(os.environ.get('MQTT_BROKER_PORT', '8883'))
MQTT_USERNAME = os.environ.get('MQTT_USERNAME', 'lijian1234')
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD', 'wanlxs0824')
MQTT_TLS_ENABLED = os.environ.get('MQTT_TLS_ENABLED', 'True').lower() == 'true'

# MQTT主题
MQTT_TOPIC_TANK_DATA = os.environ.get('MQTT_TOPIC_TANK_DATA', 'tanks/data')

# 创建MQTT客户端
client = mqtt.Client(client_id=f"test_publisher_{int(time.time())}")

# 设置用户名和密码
if MQTT_USERNAME:
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

# 配置TLS
if MQTT_TLS_ENABLED:
    client.tls_set()
    client.tls_insecure_set(True)  # 允许自签名证书

# 连接回调函数
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"成功连接到MQTT服务器: {MQTT_BROKER_URL}:{MQTT_BROKER_PORT}")
        # 连接成功后立即发布一次测试数据
        publish_test_data()
    else:
        print(f"连接MQTT服务器失败，返回码: {rc}")

# 发布测试数据
def publish_test_data():
    # 创建测试数据
    tanks_data = {
        'tanks': []
    }
    
    for i in range(1, 12):  # 创建11个罐的数据
        # 生成随机但合理的罐数据
        tank = {
            'id': i,
            'name': f'{i}#沥青罐',
            'temperature': round(random.uniform(140.0, 160.0), 1),  # 温度在140-160℃之间
            'level': round(random.uniform(2.0, 6.0), 3),  # 液位在2-6米之间
            'weight': round(random.uniform(10.0, 50.0), 3),  # 重量在10-50吨之间
            'height': 8.0,  # 罐高8米
            'high_limit': 6.4,  # 高限6.4米
            'alarm_shown': False,
            'error': 0.0
        }
        tanks_data['tanks'].append(tank)
    
    # 将数据转换为JSON字符串
    payload = json.dumps(tanks_data, ensure_ascii=False)
    
    # 发布数据
    result = client.publish(MQTT_TOPIC_TANK_DATA, payload, qos=1)
    
    # 检查发布是否成功
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print(f"成功发布测试数据到主题: {MQTT_TOPIC_TANK_DATA}")
        print(f"发布的数据: {payload}")
    else:
        print(f"发布测试数据失败，错误码: {result.rc}")

# 设置回调函数
client.on_connect = on_connect

# 连接到MQTT服务器
print(f"正在连接到MQTT服务器: {MQTT_BROKER_URL}:{MQTT_BROKER_PORT}")
client.connect(MQTT_BROKER_URL, MQTT_BROKER_PORT, 60)

# 启动MQTT循环
client.loop_start()

try:
    # 每5秒发布一次数据，共发布3次
    for i in range(3):
        time.sleep(5)
        publish_test_data()
    
    print("测试数据发布完成")
except KeyboardInterrupt:
    print("程序被用户中断")
finally:
    # 停止MQTT循环并断开连接
    client.loop_stop()
    client.disconnect()
    print("已断开MQTT连接")