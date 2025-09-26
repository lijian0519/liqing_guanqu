#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import paho.mqtt.client as mqtt_client
import logging
import os
import json
import time
import ssl
import threading
from typing import Dict, List, Any, Optional, Callable

# 配置日志
logger = logging.getLogger('MQTTClient')

class MQTTClient:
    """MQTT客户端类，用于处理MQTT连接、消息订阅和发布"""
    
    def __init__(self, 
                 broker_url: str, 
                 broker_port: int, 
                 client_id: str = None, 
                 username: str = None, 
                 password: str = None, 
                 keepalive: int = 60, 
                 tls_enabled: bool = False,
                 use_websockets: bool = False,
                 websocket_path: str = '/mqtt',
                 on_message_callback: Optional[Callable] = None,
                 on_connect_callback: Optional[Callable] = None,
                 on_disconnect_callback: Optional[Callable] = None,
                 auto_reconnect: bool = True,
                 reconnect_delay: int = 2,
                 reconnect_delay_max: int = 30,
                 reconnect_exponential_backoff: bool = True):
        # 使用传入的用户名和密码，不硬编码覆盖
        
        # 根据服务器特性和端口提供配置建议，但不强制覆盖用户设置
        # 1. 检测是否为EMQ SSL服务器
        if broker_url and 'emqxsl.cn' in broker_url and not tls_enabled:
            logger.warning("检测到EMQ SSL服务器，但TLS未启用，建议启用TLS以确保连接安全")
        
        # 2. 根据端口提供连接方式建议
        if broker_port == 8084 and not use_websockets:
            logger.warning("检测到端口8084，通常用于WebSocket连接，建议启用WebSocket")
        elif broker_port == 8883 and not tls_enabled:
            logger.warning("检测到端口8883，通常用于TLS加密连接，建议启用TLS")
        """初始化MQTT客户端
        
        Args:
            broker_url: MQTT服务器地址
            broker_port: MQTT服务器端口
            client_id: 客户端ID，默认使用固定ID
            username: 用户名，可选
            password: 密码，可选
            keepalive: 保持连接时间，单位秒
            tls_enabled: 是否启用TLS加密
            use_websockets: 是否使用WebSocket连接
            websocket_path: WebSocket路径
            on_message_callback: 消息接收回调函数
            on_connect_callback: 连接回调函数
            on_disconnect_callback: 断开连接回调函数
            auto_reconnect: 是否自动重连
            reconnect_delay: 初始重连延迟(秒)
            reconnect_delay_max: 最大重连延迟(秒)
            reconnect_exponential_backoff: 是否使用指数退避算法
        """
        # 配置参数
        self.broker_url = broker_url
        self.broker_port = broker_port
        # 客户端ID: 直接使用传入的client_id参数，如果没有则使用默认值
        # 不再使用环境变量中的MQTT_FIXED_CLIENT_ID，以避免与start_web.py中的设置冲突
        self.client_id = client_id or 'mqtt_web_interface_client'
        self.username = username
        self.password = password
        self.keepalive = keepalive
        self.tls_enabled = tls_enabled
        self.use_websockets = use_websockets
        self.websocket_path = websocket_path
        
        # 重连参数
        self.auto_reconnect = auto_reconnect
        self.reconnect_delay = reconnect_delay
        self.reconnect_delay_max = reconnect_delay_max
        self.reconnect_exponential_backoff = reconnect_exponential_backoff
        self.current_reconnect_delay = reconnect_delay
        self.last_reconnect_attempt = 0
        
        # 回调函数
        self.on_message_callback = on_message_callback
        self.on_connect_callback = on_connect_callback
        self.on_disconnect_callback = on_disconnect_callback
        
        # 状态变量
        self.client: Optional[mqtt_client.Client] = None
        self.is_connected = False
        self.subscribed_topics: List[Dict[str, Any]] = []
        self.loop_running = False
        self.loop_type = None  # 'thread', 'forever', or None
        self.loop_thread = None
        
        # 初始化客户端
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """初始化MQTT客户端实例，配置连接参数和回调函数"""
        try:
            # 创建MQTT客户端，使用clean_session=True以简化连接
            transport = 'websockets' if self.use_websockets else 'tcp'
            self.client = mqtt_client.Client(client_id=self.client_id, clean_session=True, transport=transport)
            
            # 设置回调函数
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            # 设置用户名和密码
            if self.username is not None:
                self.client.username_pw_set(self.username, self.password)
                logger.info(f"已设置MQTT用户名: {self.username if self.username else '空'}")
            
            # 只有在auto_reconnect为True时才配置重连参数
            if self.auto_reconnect:
                logger.info(f"配置MQTT自动重连 - 最小延迟: {self.reconnect_delay}秒, 最大延迟: {self.reconnect_delay_max}秒")
                self.client.reconnect_delay_set(
                    min_delay=self.reconnect_delay,
                    max_delay=self.reconnect_delay_max
                )
            else:
                logger.info("已禁用MQTT自动重连")
            
            # 如果启用了WebSocket，配置WebSocket连接
            if self.use_websockets:
                try:
                    # 配置MQTT over WebSocket
                    self.client.ws_set_options(path=self.websocket_path)
                    logger.info(f"已配置MQTT over WebSocket，路径: {self.websocket_path}")
                except Exception as e:
                    logger.error(f"配置WebSocket时出错: {str(e)}")
            
            # 启用TLS
            if self.tls_enabled:
                self._configure_tls()
                
        except Exception as e:
            logger.error(f"初始化MQTT客户端失败: {str(e)}")
            logger.error(f"异常类型: {type(e).__name__}")
    
    def _configure_tls(self) -> None:
        """配置TLS加密连接，增强安全性"""
        try:
            # 简化的TLS配置，与python_mqtt_client_optimized.py保持一致
            logger.info(f"配置TLS加密连接")
            self.client.tls_set()
            self.client.tls_insecure_set(True)  # 允许自签名证书
            logger.info("已启用MQTT TLS加密，配置为忽略证书验证")
                
        except Exception as e:
            logger.error(f"设置TLS时出错: {str(e)}")
            logger.error(f"异常类型: {type(e).__name__}")
    
    def _on_connect(self, client: mqtt_client.Client, userdata: Any, flags: Dict[str, Any], rc: int) -> None:
        """MQTT连接回调函数，处理连接成功或失败的逻辑"""
        # 记录详细的连接信息
        logger.debug(f"连接回调 - 返回码: {rc}, 标志: {flags}")
        
        if rc == 0:
            self.is_connected = True
            # 重置重连延迟
            self.current_reconnect_delay = self.reconnect_delay
            logger.info(f"已成功连接到MQTT服务器: {self.broker_url}:{self.broker_port}")
            
            # 重订阅之前的主题
            self._resubscribe_topics()
            
            # 调用用户定义的连接回调
            if self.on_connect_callback:
                try:
                    self.on_connect_callback(client, userdata, flags, rc)
                except Exception as e:
                    logger.error(f"用户连接回调函数执行失败: {str(e)}")
        else:
            self.is_connected = False
            error_message = self._get_connect_error_message(rc)
            logger.error(f"MQTT连接失败，返回码: {rc}, 错误: {error_message}")
            
            # 调用用户定义的连接回调
            if self.on_connect_callback:
                try:
                    self.on_connect_callback(client, userdata, flags, rc)
                except Exception as e:
                    logger.error(f"用户连接回调函数执行失败: {str(e)}")
    
    def _on_disconnect(self, client: mqtt_client.Client, userdata: Any, rc: int) -> None:
        """MQTT断开连接回调函数，处理正常和异常断开的情况"""
        was_connected = self.is_connected
        self.is_connected = False
        
        # 记录断开连接信息
        logger.debug(f"断开连接回调 - 返回码: {rc}")
        
        # 如果不是正常断开连接（rc=0表示正常断开），记录警告
        if rc != 0:
            error_message = self._get_connect_error_message(rc)
            logger.warning(f"MQTT意外断开连接，返回码: {rc}, 错误: {error_message}")
            logger.debug(f"断开连接时的客户端状态 - is_connected: {was_connected}, 客户端ID: {self.client_id}, 用户名: {self.username}")
        else:
            logger.info("MQTT连接已正常断开")
        
        # 调用用户定义的断开连接回调
        if self.on_disconnect_callback:
            try:
                self.on_disconnect_callback(client, userdata, rc)
            except Exception as e:
                logger.error(f"用户断开连接回调函数执行失败: {str(e)}")
    
    def _on_message(self, client: mqtt_client.Client, userdata: Any, msg: mqtt_client.MQTTMessage) -> None:
        """MQTT消息接收回调函数，增强消息处理能力"""
        try:
            # 尝试解析JSON消息
            payload = msg.payload.decode('utf-8')
            
            # 尝试解析JSON格式的消息
            try:
                data = json.loads(payload)
                logger.debug(f"收到JSON消息 - 主题: {msg.topic}, QoS: {msg.qos}, 负载: {payload[:100]}...")
            except json.JSONDecodeError:
                # 如果不是JSON格式，保持原始负载
                data = payload
                logger.debug(f"收到非JSON消息 - 主题: {msg.topic}, QoS: {msg.qos}, 负载: {data[:100]}...")
            
            # 调用用户定义的消息回调
            if self.on_message_callback:
                try:
                    self.on_message_callback(client, userdata, msg)
                except Exception as e:
                    logger.error(f"用户消息回调函数执行失败: {str(e)}")
        except Exception as e:
            logger.error(f"处理MQTT消息时出错: {str(e)}")
            logger.error(f"异常类型: {type(e).__name__}")
    
    def _resubscribe_topics(self) -> None:
        """重新订阅之前的主题，确保连接恢复后能够继续接收消息"""
        if not self.client or not self.is_connected:
            logger.warning("未连接，无法重新订阅主题")
            return
        
        for topic_info in self.subscribed_topics:
            try:
                result, mid = self.client.subscribe(topic_info['topic'], qos=topic_info['qos'])
                if result == mqtt_client.MQTT_ERR_SUCCESS:
                    logger.info(f"已重新订阅主题: {topic_info['topic']}, QoS: {topic_info['qos']}")
                else:
                    logger.error(f"重新订阅主题 {topic_info['topic']} 失败，返回码: {result}")
            except Exception as e:
                logger.error(f"重新订阅主题 {topic_info['topic']} 时出错: {str(e)}")
    
    def _get_connect_error_message(self, rc: int) -> str:
        """根据返回码获取连接错误消息，提供更详细的错误描述"""
        error_messages = {
            0: "连接成功",
            1: "连接被拒绝 - 协议版本不支持",
            2: "连接被拒绝 - 客户端ID无效或已被占用",
            3: "连接被拒绝 - 服务器不可用",
            4: "连接被拒绝 - 用户名或密码错误",
            5: "连接被拒绝 - 未授权",
            6: "连接断开 - 服务端断开",
            7: "连接被拒绝 - 未授权（返回码7）",
            # 更多错误码
            8: "连接被拒绝 - 服务器不可用（返回码8）",
            9: "连接被拒绝 - 客户端已断开连接（返回码9）",
            10: "连接被拒绝 - 连接超时（返回码10）"
        }
        return error_messages.get(rc, f"未知错误 (返回码: {rc})")
    
    def connect(self) -> bool:
        """连接到MQTT服务器，增强连接稳定性
        
        Returns:
            bool: 连接是否成功
        """
        if self.is_connected:
            logger.warning("已经连接到MQTT服务器")
            return True
        
        try:
            if self.client:
                # 验证连接参数
                if not self.broker_url:
                    logger.error("MQTT服务器地址不能为空")
                    return False
                
                if not isinstance(self.broker_port, int) or self.broker_port <= 0 or self.broker_port > 65535:
                    logger.error(f"无效的MQTT服务器端口: {self.broker_port}")
                    return False
                
                # 详细的连接参数日志
                logger.info(f"============== MQTT连接参数详情 ==============")
                logger.info(f"服务器URL: {self.broker_url}")
                logger.info(f"服务器端口: {self.broker_port}")
                logger.info(f"客户端ID: {self.client_id}")
                logger.info(f"用户名: {'已设置' if self.username is not None else '未设置'} (值: {self.username})")
                logger.info(f"密码: {'已设置' if self.password is not None else '未设置'} (长度: {len(self.password) if self.password is not None else 0})")
                logger.info(f"TLS启用: {self.tls_enabled}")
                logger.info(f"WebSocket启用: {self.use_websockets}")
                logger.info(f"WebSocket路径: {self.websocket_path}")
                logger.info(f"保活时间: {self.keepalive}秒")
                logger.info(f"自动重连: {self.auto_reconnect}")
                logger.info(f"============================================")
                
                # 检查服务器类型和端口匹配，并提供警告，但不强制覆盖用户设置
                if self.broker_url.endswith('emqxsl.cn') and not self.tls_enabled:
                    logger.warning("警告: 检测到EMQ SSL服务器，但TLS未启用，这可能导致连接失败或不安全")
                
                if self.broker_port == 8084 and not self.use_websockets:
                    logger.warning(f"警告: 端口{self.broker_port}通常用于WebSocket连接，但WebSocket未启用，这可能导致连接失败")
                elif self.broker_port == 8883 and not self.tls_enabled:
                    logger.warning(f"警告: 端口{self.broker_port}通常用于TLS加密连接，但TLS未启用，这可能导致连接失败")
                
                # 根据连接类型选择合适的连接方法
                if self.use_websockets:
                    logger.info("使用WebSocket连接模式")
                    try:
                        # 记录连接尝试的详细信息
                        logger.info(f"[连接尝试] 服务器: {self.broker_url}, 端口: {self.broker_port}, WebSocket路径: {self.websocket_path}")
                        logger.info(f"[连接尝试] TLS: {self.tls_enabled}")
                        logger.info(f"[连接尝试] 客户端ID: {self.client_id}")
                        if self.username is not None:
                            logger.info(f"[连接尝试] 使用用户名: {self.username}")
                        
                        # WebSocket连接使用异步连接方式
                        self.client.connect_async(self.broker_url, self.broker_port, self.keepalive)
                        logger.info("WebSocket连接命令已发送")
                        
                        # 立即启动客户端循环
                        self.start_loop(loop_type='thread')
                    except Exception as ws_error:
                        logger.error(f"WebSocket连接异常: {str(ws_error)}")
                        logger.error(f"异常类型: {type(ws_error).__name__}")
                        raise
                else:
                    logger.info("使用TCP连接模式")
                    try:
                        # 记录连接尝试的详细信息
                        logger.info(f"[连接尝试] 服务器: {self.broker_url}, 端口: {self.broker_port}")
                        logger.info(f"[连接尝试] TLS: {self.tls_enabled}")
                        logger.info(f"[连接尝试] 客户端ID: {self.client_id}")
                        if self.username is not None:
                            logger.info(f"[连接尝试] 使用用户名: {self.username}")
                        
                        # 常规TCP连接使用同步连接
                        self.client.connect(self.broker_url, self.broker_port, self.keepalive)
                        logger.info("TCP连接命令已发送")
                        
                        # 立即启动客户端循环
                        self.start_loop(loop_type='thread')
                    except Exception as tcp_error:
                        logger.error(f"TCP连接异常: {str(tcp_error)}")
                        logger.error(f"异常类型: {type(tcp_error).__name__}")
                        raise
                
                return True
            else:
                logger.error("MQTT客户端未初始化")
                # 尝试重新初始化客户端
                self._initialize_client()
                return False
        except Exception as e:
            logger.error(f"连接MQTT服务器时出错: {str(e)}")
            logger.error(f"异常类型: {type(e).__name__}")
            return False
    
    def disconnect(self) -> None:
        """断开与MQTT服务器的连接，确保资源正确释放"""
        if self.client:
            try:
                if self.is_connected:
                    self.client.disconnect()
                    self.is_connected = False
                    logger.info("已断开与MQTT服务器的连接")
                else:
                    logger.warning("未连接到MQTT服务器，无需断开")
            except Exception as e:
                logger.error(f"断开MQTT连接时出错: {str(e)}")
        else:
            logger.warning("MQTT客户端未初始化")
    
    def subscribe(self, topic: str, qos: int = 1) -> bool:
        """订阅MQTT主题，确保主题持久性
        
        Args:
            topic: 要订阅的主题
            qos: 服务质量等级
        
        Returns:
            bool: 订阅是否成功
        """
        if not topic:
            logger.error("订阅主题不能为空")
            return False
        
        if not self.client or not self.is_connected:
            logger.warning("无法订阅主题，MQTT未连接")
            return False
        
        try:
            result, mid = self.client.subscribe(topic, qos=qos)
            if result == mqtt_client.MQTT_ERR_SUCCESS:
                # 保存订阅的主题信息，用于重连后自动重新订阅
                topic_exists = False
                for i, t in enumerate(self.subscribed_topics):
                    if t['topic'] == topic:
                        self.subscribed_topics[i] = {'topic': topic, 'qos': qos, 'mid': mid}
                        topic_exists = True
                        break
                
                if not topic_exists:
                    self.subscribed_topics.append({
                        'topic': topic,
                        'qos': qos,
                        'mid': mid
                    })
                
                logger.info(f"已订阅主题: {topic}, QoS: {qos}")
                return True
            else:
                logger.error(f"订阅主题 {topic} 失败，返回码: {result}")
                return False
        except Exception as e:
            logger.error(f"订阅主题 {topic} 时出错: {str(e)}")
            return False
    
    def unsubscribe(self, topic: str) -> bool:
        """取消订阅MQTT主题
        
        Args:
            topic: 要取消订阅的主题
        
        Returns:
            bool: 取消订阅是否成功
        """
        if not topic:
            logger.error("取消订阅的主题不能为空")
            return False
        
        if not self.client or not self.is_connected:
            logger.warning("无法取消订阅主题，MQTT未连接")
            # 仍然从已订阅列表中删除主题
            self.subscribed_topics = [t for t in self.subscribed_topics if t['topic'] != topic]
            return True
        
        try:
            result, mid = self.client.unsubscribe(topic)
            if result == mqtt_client.MQTT_ERR_SUCCESS:
                # 从订阅列表中移除
                self.subscribed_topics = [t for t in self.subscribed_topics if t['topic'] != topic]
                logger.info(f"已取消订阅主题: {topic}")
                return True
            else:
                logger.error(f"取消订阅主题 {topic} 失败，返回码: {result}")
                return False
        except Exception as e:
            logger.error(f"取消订阅主题 {topic} 时出错: {str(e)}")
            return False
    
    def publish(self, topic: str, payload: Any, qos: int = 1, retain: bool = False) -> bool:
        """发布MQTT消息，增强消息格式处理
        
        Args:
            topic: 发布的主题
            payload: 消息负载
            qos: 服务质量等级
            retain: 是否保留消息
        
        Returns:
            bool: 发布是否成功
        """
        if not topic:
            logger.error("发布主题不能为空")
            return False
        
        if not self.client or not self.is_connected:
            logger.warning("无法发布消息，MQTT未连接")
            return False
        
        try:
            # 确保payload是字符串或可序列化对象
            if isinstance(payload, dict):
                try:
                    payload = json.dumps(payload)
                except Exception as e:
                    logger.error(f"无法序列化payload为JSON: {str(e)}")
                    return False
            elif not isinstance(payload, (str, bytes)):
                payload = str(payload)
            
            result, mid = self.client.publish(topic, payload, qos=qos, retain=retain)
            if result == mqtt_client.MQTT_ERR_SUCCESS:
                logger.info(f"已发布消息 - 主题: {topic}, QoS: {qos}, 保留: {retain}, 负载: {payload[:100]}...")
                return True
            else:
                logger.error(f"发布消息到主题 {topic} 失败，返回码: {result}")
                return False
        except Exception as e:
            logger.error(f"发布消息到主题 {topic} 时出错: {str(e)}")
            return False
    
    def start_loop(self, loop_type: str = 'thread') -> bool:
        """启动MQTT客户端循环，增强循环管理
        
        Args:
            loop_type: 循环类型，可选值: 'thread'(线程模式), 'forever'(阻塞模式)
        
        Returns:
            bool: 启动是否成功
        """
        if not self.client:
            logger.error("MQTT客户端未初始化")
            return False
        
        try:
            if self.loop_running:
                logger.warning("循环已经在运行")
                return True
            
            if loop_type == 'thread':
                # 在单独的线程中运行循环
                self.loop_type = 'thread'
                self.client.loop_start()
                self.loop_running = True
                logger.info("已启动MQTT客户端线程")
            elif loop_type == 'forever':
                # 阻塞模式，通常用于独立程序
                self.loop_type = 'forever'
                self.loop_running = True
                logger.info("已启动MQTT客户端阻塞循环")
                # 注意：这会阻塞当前线程
                try:
                    self.client.loop_forever()
                except KeyboardInterrupt:
                    logger.info("用户中断MQTT循环")
                except Exception as e:
                    logger.error(f"MQTT循环异常: {str(e)}")
                finally:
                    self.loop_running = False
            else:
                logger.error(f"不支持的循环类型: {loop_type}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"启动MQTT客户端循环时出错: {str(e)}")
            self.loop_running = False
            self.loop_type = None
            return False
    
    def stop_loop(self) -> bool:
        """停止MQTT客户端循环，确保资源正确释放
        
        Returns:
            bool: 停止是否成功
        """
        if not self.client:
            logger.error("MQTT客户端未初始化")
            return False
        
        try:
            if not self.loop_running:
                logger.warning("循环未运行")
                return True
            
            self.client.loop_stop()
            self.loop_running = False
            self.loop_type = None
            logger.info("已停止MQTT客户端线程")
            return True
        except Exception as e:
            logger.error(f"停止MQTT客户端循环时出错: {str(e)}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """获取MQTT客户端状态，提供更详细的状态信息
        
        Returns:
            Dict[str, Any]: 客户端状态信息
        """
        return {
            'connected': self.is_connected,
            'broker_url': self.broker_url,
            'broker_port': self.broker_port,
            'client_id': self.client_id,
            'subscribed_topics': [t['topic'] for t in self.subscribed_topics],
            'tls_enabled': self.tls_enabled,
            'use_websockets': self.use_websockets,
            'loop_running': self.loop_running,
            'loop_type': self.loop_type,
            'auto_reconnect': self.auto_reconnect,
            'current_reconnect_delay': self.current_reconnect_delay
        }
    
    def set_on_message_callback(self, callback: Callable) -> None:
        """设置消息接收回调函数
        
        Args:
            callback: 回调函数
        """
        if callback and callable(callback):
            self.on_message_callback = callback
            logger.info("已设置MQTT消息回调函数")
        else:
            logger.error("无效的回调函数")
    
    def set_on_connect_callback(self, callback: Callable) -> None:
        """设置连接回调函数
        
        Args:
            callback: 回调函数
        """
        if callback and callable(callback):
            self.on_connect_callback = callback
            logger.info("已设置MQTT连接回调函数")
        else:
            logger.error("无效的回调函数")
    
    def set_on_disconnect_callback(self, callback: Callable) -> None:
        """设置断开连接回调函数
        
        Args:
            callback: 回调函数
        """
        if callback and callable(callback):
            self.on_disconnect_callback = callback
            logger.info("已设置MQTT断开连接回调函数")
        else:
            logger.error("无效的回调函数")
    
    def __del__(self):
        """析构函数，确保断开连接和停止循环，防止资源泄漏"""
        try:
            # 确保停止循环
            if hasattr(self, 'loop_running') and self.loop_running:
                self.stop_loop()
            
            # 确保断开连接
            if hasattr(self, 'is_connected') and self.is_connected:
                self.disconnect()
            
        except Exception:
            # 忽略析构函数中的异常
            pass
    
    def reset_reconnect_delay(self) -> None:
        """重置重连延迟，通常在成功连接后调用
        """
        self.current_reconnect_delay = self.reconnect_delay
        logger.info(f"已重置重连延迟为: {self.reconnect_delay}秒")