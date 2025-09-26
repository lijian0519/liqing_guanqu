#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import logging
import pandas as pd
import numpy as np
import time  # 添加time模块导入
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import threading

# 导入项目配置
from config import current_config

# 配置日志
logger = logging.getLogger('DataManager')

class DataManager:
    """数据管理类，负责处理、存储和分析从MQTT接收的储罐数据"""
    
    def __init__(self, data_dir: str = 'data', history_file: str = 'tank_history.json', storage_days: int = 7):
        """初始化数据管理器
        
        Args:
            data_dir: 数据存储目录
            history_file: 历史数据文件名
            storage_days: 数据存储天数，超过这个天数的数据将被自动删除
        """
        # 配置
        self.data_dir = data_dir
        self.history_file = history_file
        self.history_file_path = os.path.join(self.data_dir, self.history_file)
        
        # 确保数据目录存在
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 数据存储
        self.tanks_data: Dict[str, Dict[str, Any]] = {}
        self.tanks_history: Dict[str, List[Dict[str, Any]]] = {}
        self.alerts: List[Dict[str, Any]] = []
        
        # 配置参数
        self.max_history_points = getattr(current_config, 'MAX_HISTORY_POINTS', 10000)  # 每个罐保存的历史数据点数量
        self.temp_threshold_high = 180  # 温度高阈值
        self.temp_threshold_low = 120   # 温度低阈值
        self.level_threshold_high = 90  # 液位高阈值
        self.level_threshold_low = 10   # 液位低阈值
        self.error_threshold = 0.5      # 误差阈值
        self.storage_days = storage_days  # 数据存储天数
        self.default_tank_height = getattr(current_config, 'DEFAULT_TANK_HEIGHT', 8.0)  # 默认罐高度
        
        # 锁，用于线程安全
        self.data_lock = threading.Lock()
        
        # 加载历史数据
        self._load_history_data()
        
        # 立即执行一次清理，移除过期数据
        self._cleanup_expired_data()
        
        # 启动定期清理任务
        self._start_cleanup_task()
    
    def _load_history_data(self) -> None:
        """从文件加载历史数据到内存
        
        该方法尝试从配置的历史数据文件中加载储罐的当前数据、历史记录和存储天数配置。
        如果文件不存在或读取解析失败，将记录错误日志但不会中断程序运行，确保系统能够继续工作。
        加载成功后会记录包含的储罐数量信息。
        """
        try:
            if os.path.exists(self.history_file_path):
                with open(self.history_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 恢复罐数据和历史数据
                    if 'tanks_data' in data:
                        self.tanks_data = data['tanks_data']
                    if 'tanks_history' in data:
                        self.tanks_history = data['tanks_history']
                    # 恢复存储天数配置
                    if 'storage_days' in data:
                        self.storage_days = data['storage_days']
                logger.info(f"已加载历史数据，包含 {len(self.tanks_data)} 个罐的数据")
        except Exception as e:
            logger.error(f"加载历史数据时出错: {str(e)}")
    
    def _save_history_data(self) -> None:
        """将内存中的历史数据保存到文件
        
        该方法使用线程锁确保数据一致性，将当前所有储罐数据、历史记录和存储天数配置保存到文件中。
        保存过程中会记录当前时间戳，便于后续追踪数据更新情况。
        如果保存过程中发生异常，将记录错误日志但不会中断程序运行。
        """
        try:
            with self.data_lock:
                data_to_save = {
                    'tanks_data': self.tanks_data,
                    'tanks_history': self.tanks_history,
                    'storage_days': self.storage_days,
                    'timestamp': datetime.now().isoformat()
                }
                
            with open(self.history_file_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            logger.debug("历史数据已保存")
        except Exception as e:
            logger.error(f"保存历史数据时出错: {str(e)}")
    
    def process_mqtt_message(self, topic: str, payload: str) -> Optional[Dict[str, Any]]:
        """处理MQTT消息
        
        Args:
            topic: MQTT主题
            payload: MQTT消息负载
        
        Returns:
            Optional[Dict[str, Any]]: 处理后的罐数据，如果解析失败则返回None
        """
        try:
            # 尝试解析JSON消息
            if isinstance(payload, dict):
                message = payload
            else:
                message = json.loads(payload)
            
            # 提取罐数据
            tank_id = self._extract_tank_id(topic, message)
            if not tank_id:
                logger.warning(f"无法从消息中提取罐ID: {topic}")
                return None
            
            # 解析罐数据
            tank_data = self._parse_tank_data(tank_id, message)
            if not tank_data:
                return None
            
            # 更新罐数据
            updated_data = self.update_tank_data(tank_id, tank_data)
            return updated_data
        except json.JSONDecodeError as e:
            logger.error(f"解析MQTT消息JSON时出错: {str(e)}, 消息: {payload[:100]}...")
        except Exception as e:
            logger.error(f"处理MQTT消息时出错: {str(e)}")
        
        return None
    
    def _extract_tank_id(self, topic: str, message: Dict[str, Any]) -> Optional[str]:
        """从主题或消息中提取罐ID
        
        Args:
            topic: MQTT主题
            message: 解析后的消息数据
        
        Returns:
            Optional[str]: 罐ID
        """
        # 尝试从主题中提取
        topic_parts = topic.split('/')
        for part in topic_parts:
            if part.startswith('tank_') or part.isdigit():
                return part
        
        # 尝试从消息中提取
        if 'tank_id' in message:
            return str(message['tank_id'])
        if 'id' in message:
            return str(message['id'])
        
        # 默认使用主题最后一部分
        if topic_parts:
            return topic_parts[-1]
        
        return None
    
    def _parse_tank_data(self, tank_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """解析罐数据
        
        Args:
            tank_id: 罐ID
            message: 解析后的消息数据
        
        Returns:
            Dict[str, Any]: 标准化的罐数据
        """
        timestamp = datetime.now().isoformat()
        
        # 标准化数据格式
        tank_data = {
            'tank_id': tank_id,
            'timestamp': timestamp,
            'temperature': None,
            'level': None,
            'pressure': None,
            'error': None,
            'status': 'normal',  # normal, warning, alert
            'alert_message': '',
            'raw_data': message
        }
        
        # 尝试提取温度数据
        if 'temperature' in message:
            tank_data['temperature'] = float(message['temperature'])
        elif 'temp' in message:
            tank_data['temperature'] = float(message['temp'])
        
        # 尝试提取液位数据
        if 'level' in message:
            tank_data['level'] = float(message['level'])
        elif 'height' in message:
            tank_data['level'] = float(message['height'])
        elif 'liquid_level' in message:
            tank_data['liquid_level'] = float(message['liquid_level'])
        
        # 尝试提取压力数据
        if 'pressure' in message:
            tank_data['pressure'] = float(message['pressure'])
        
        # 尝试提取误差数据
        if 'error' in message:
            tank_data['error'] = float(message['error'])
        
        # 检查数据有效性
        if tank_data['temperature'] is not None or tank_data['level'] is not None:
            # 检查是否需要报警
            self._check_alerts(tank_data)
            return tank_data
        else:
            logger.warning(f"罐 {tank_id} 的数据不包含温度或液位信息")
            return {}
    
    def _check_alerts(self, tank_data: Dict[str, Any]) -> None:
        """检查是否需要报警
        
        Args:
            tank_data: 罐数据
        """
        alerts = []
        
        # 检查温度
        if tank_data['temperature'] is not None:
            if tank_data['temperature'] > self.temp_threshold_high:
                alerts.append(f"温度过高: {tank_data['temperature']}°C")
            elif tank_data['temperature'] < self.temp_threshold_low:
                alerts.append(f"温度过低: {tank_data['temperature']}°C")
        
        # 检查液位
        if tank_data['level'] is not None:
            if tank_data['level'] > self.level_threshold_high:
                alerts.append(f"液位过高: {tank_data['level']}%")
            elif tank_data['level'] < self.level_threshold_low:
                alerts.append(f"液位过低: {tank_data['level']}%")
        
        # 检查误差
        if tank_data['error'] is not None and tank_data['error'] > self.error_threshold:
            alerts.append(f"误差过大: {tank_data['error']}")
        
        # 更新状态
        if alerts:
            tank_data['status'] = 'alert' if any('过高' in alert or '过低' in alert for alert in alerts) else 'warning'
            tank_data['alert_message'] = '; '.join(alerts)
            
            # 添加到警报列表
            self.add_alert(tank_data)
        else:
            tank_data['status'] = 'normal'
            tank_data['alert_message'] = ''
    
    def add_alert(self, tank_data: Dict[str, Any]) -> None:
        """添加警报到警报列表
        
        Args:
            tank_data: 罐数据
        """
        alert = {
            'tank_id': tank_data['tank_id'],
            'timestamp': datetime.now().isoformat(),
            'status': tank_data['status'],
            'message': tank_data['alert_message'],
            'data': {
                'temperature': tank_data['temperature'],
                'level': tank_data['level'],
                'pressure': tank_data['pressure'],
                'error': tank_data['error']
            }
        }
        
        with self.data_lock:
            self.alerts.append(alert)
            # 保留最近的100条警报
            if len(self.alerts) > 100:
                self.alerts = self.alerts[-100:]
        
        logger.warning(f"警报 - {tank_data['tank_id']}: {tank_data['alert_message']}")
    
    def update_tank_data(self, tank_id: str, tank_data: Dict[str, Any]) -> Dict[str, Any]:
        """更新罐数据
        
        Args:
            tank_id: 罐ID
            tank_data: 新的罐数据
        
        Returns:
            Dict[str, Any]: 更新后的罐数据
        """
        with self.data_lock:
            # 更新当前数据
            self.tanks_data[tank_id] = tank_data
            
            # 更新历史数据
            if tank_id not in self.tanks_history:
                self.tanks_history[tank_id] = []
            
            # 添加到历史数据（只保留重要字段）
            history_entry = {
                'timestamp': tank_data['timestamp'],
                'temperature': tank_data['temperature'],
                'level': tank_data['level'],
                'pressure': tank_data['pressure'],
                'status': tank_data['status']
            }
            self.tanks_history[tank_id].append(history_entry)
            
            # 限制历史数据点数量
            if len(self.tanks_history[tank_id]) > self.max_history_points:
                self.tanks_history[tank_id] = self.tanks_history[tank_id][-self.max_history_points:]
            
            # 清理过期数据
            self._cleanup_expired_data(tank_id)
        
        # 异步保存数据
        threading.Thread(target=self._save_history_data).start()
        
        return tank_data
    
    def get_tank_data(self, tank_id: str = None) -> Dict[str, Any] or Dict[str, Dict[str, Any]]:
        """获取罐数据
        
        Args:
            tank_id: 罐ID，如果为None则返回所有罐的数据
        
        Returns:
            Dict[str, Any] or Dict[str, Dict[str, Any]]: 罐数据
        """
        with self.data_lock:
            if tank_id:
                return self.tanks_data.get(tank_id, {})
            else:
                return self.tanks_data.copy()
    
    def get_tank_history(self, tank_id: str, start_time: str = None, end_time: str = None, limit: int = None) -> List[Dict[str, Any]]:
        """获取罐的历史数据
        
        Args:
            tank_id: 罐ID
            start_time: 开始时间（ISO格式字符串）
            end_time: 结束时间（ISO格式字符串）
            limit: 返回的数据点数量限制
        
        Returns:
            List[Dict[str, Any]]: 历史数据列表
        """
        with self.data_lock:
            if tank_id not in self.tanks_history:
                return []
            
            history = self.tanks_history[tank_id].copy()
            
            # 按开始时间过滤
            if start_time:
                history = [h for h in history if h['timestamp'] >= start_time]
            
            # 按结束时间过滤
            if end_time:
                history = [h for h in history if h['timestamp'] <= end_time]
            
            # 限制返回的数据点数量
            if limit and isinstance(limit, int) and limit > 0:
                # 优先取最新的数据点
                history = history[-limit:]
            
            return history
    
    def get_all_tanks_summary(self) -> Dict[str, Dict[str, Any]]:
        """获取所有罐的摘要信息
        
        Returns:
            Dict[str, Dict[str, Any]]: 罐摘要信息字典
        """
        summary = {}
        with self.data_lock:
            for tank_id, tank_data in self.tanks_data.items():
                summary[tank_id] = {
                    'tank_id': tank_id,
                    'status': tank_data.get('status', 'normal'),
                    'temperature': tank_data.get('temperature'),
                    'level': tank_data.get('level'),
                    'pressure': tank_data.get('pressure'),
                    'alert_message': tank_data.get('alert_message', ''),
                    'last_updated': tank_data.get('timestamp')
                }
        
        return summary
    
    def get_alerts(self, tank_id: str = None, time_range: int = 60) -> List[Dict[str, Any]]:
        """获取警报列表
        
        Args:
            tank_id: 罐ID，如果为None则返回所有罐的警报
            time_range: 时间范围（分钟）
        
        Returns:
            List[Dict[str, Any]]: 警报列表
        """
        cutoff_time = (datetime.now() - timedelta(minutes=time_range)).isoformat()
        
        with self.data_lock:
            filtered_alerts = []
            for alert in self.alerts:
                # 按时间范围过滤
                if alert['timestamp'] >= cutoff_time:
                    # 按罐ID过滤
                    if not tank_id or alert['tank_id'] == tank_id:
                        filtered_alerts.append(alert)
            
            # 按时间倒序排序
            filtered_alerts.sort(key=lambda x: x['timestamp'], reverse=True)
            
            return filtered_alerts
    
    def get_tank_statistics(self, tank_id: str, time_range: int = 60) -> Dict[str, Any]:
        """获取罐的统计信息
        
        Args:
            tank_id: 罐ID
            time_range: 时间范围（分钟）
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        history = self.get_tank_history(tank_id, time_range)
        
        if not history:
            return {
                'tank_id': tank_id,
                'data_points': 0,
                'avg_temperature': None,
                'max_temperature': None,
                'min_temperature': None,
                'avg_level': None,
                'max_level': None,
                'min_level': None,
                'alert_count': 0
            }
        
        # 提取数据进行统计
        temperatures = [h['temperature'] for h in history if h['temperature'] is not None]
        levels = [h['level'] for h in history if h['level'] is not None]
        alert_count = sum(1 for h in history if h['status'] in ['warning', 'alert'])
        
        stats = {
            'tank_id': tank_id,
            'data_points': len(history),
            'time_range': time_range,
            'avg_temperature': round(np.mean(temperatures), 2) if temperatures else None,
            'max_temperature': max(temperatures) if temperatures else None,
            'min_temperature': min(temperatures) if temperatures else None,
            'avg_level': round(np.mean(levels), 2) if levels else None,
            'max_level': max(levels) if levels else None,
            'min_level': min(levels) if levels else None,
            'alert_count': alert_count
        }
        
        return stats
    
    def get_overall_status(self) -> Dict[str, Any]:
        """获取系统整体状态
        
        Returns:
            Dict[str, Any]: 整体状态信息
        """
        with self.data_lock:
            total_tanks = len(self.tanks_data)
            alert_tanks = sum(1 for tank in self.tanks_data.values() if tank['status'] == 'alert')
            warning_tanks = sum(1 for tank in self.tanks_data.values() if tank['status'] == 'warning')
            normal_tanks = total_tanks - alert_tanks - warning_tanks
            
            # 获取最近的警报
            recent_alerts = self.get_alerts(time_range=30)
            
            return {
                'total_tanks': total_tanks,
                'normal_tanks': normal_tanks,
                'warning_tanks': warning_tanks,
                'alert_tanks': alert_tanks,
                'recent_alerts_count': len(recent_alerts),
                'last_update_time': max(tank.get('timestamp', '') for tank in self.tanks_data.values()) if self.tanks_data else None
            }
    
    def set_thresholds(self, 
                      temp_high: float = None, 
                      temp_low: float = None, 
                      level_high: float = None, 
                      level_low: float = None, 
                      error: float = None) -> Dict[str, float]:
        """设置警报阈值
        
        Args:
            temp_high: 温度高阈值
            temp_low: 温度低阈值
            level_high: 液位高阈值
            level_low: 液位低阈值
            error: 误差阈值
        
        Returns:
            Dict[str, float]: 更新后的阈值
        """
        if temp_high is not None:
            self.temp_threshold_high = temp_high
        if temp_low is not None:
            self.temp_threshold_low = temp_low
        if level_high is not None:
            self.level_threshold_high = level_high
        if level_low is not None:
            self.level_threshold_low = level_low
        if error is not None:
            self.error_threshold = error
        
        # 重新检查所有罐的警报状态
        for tank_id, tank_data in self.tanks_data.items():
            self._check_alerts(tank_data)
        
        return {
            'temp_threshold_high': self.temp_threshold_high,
            'temp_threshold_low': self.temp_threshold_low,
            'level_threshold_high': self.level_threshold_high,
            'level_threshold_low': self.level_threshold_low,
            'error_threshold': self.error_threshold
        }
    
    def clear_history(self, tank_id: str = None) -> bool:
        """清除历史数据
        
        Args:
            tank_id: 罐ID，如果为None则清除所有罐的历史数据
        
        Returns:
            bool: 操作是否成功
        """
        try:
            with self.data_lock:
                if tank_id:
                    if tank_id in self.tanks_history:
                        self.tanks_history[tank_id] = []
                        logger.info(f"已清除罐 {tank_id} 的历史数据")
                else:
                    self.tanks_history = {}
                    logger.info("已清除所有罐的历史数据")
                
            # 保存更改
            self._save_history_data()
            return True
        except Exception as e:
            logger.error(f"清除历史数据时出错: {str(e)}")
            return False
    
    def remove_tank(self, tank_id: str) -> bool:
        """移除罐数据
        
        Args:
            tank_id: 罐ID
        
        Returns:
            bool: 操作是否成功
        """
        try:
            with self.data_lock:
                if tank_id in self.tanks_data:
                    del self.tanks_data[tank_id]
                if tank_id in self.tanks_history:
                    del self.tanks_history[tank_id]
                
            # 保存更改
            self._save_history_data()
            logger.info(f"已移除罐 {tank_id} 的数据")
            return True
        except Exception as e:
            logger.error(f"移除罐数据时出错: {str(e)}")
            return False
    
    def _start_cleanup_task(self) -> None:
        """启动定期清理任务
        
        该方法创建一个守护线程，定期执行数据清理操作。清理任务每天运行一次，
        移除超过配置存储天数的历史数据，确保系统资源得到有效利用。
        守护线程会在主程序退出时自动终止，避免阻止程序正常退出。
        """
        def cleanup_task():
            while True:
                try:
                    # 每天执行一次清理
                    time.sleep(24 * 60 * 60)  # 24小时
                    self._cleanup_expired_data()
                except Exception as e:
                    logger.error(f"执行定期清理任务时出错: {str(e)}")
        
        # 创建后台线程执行清理任务
        cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
        cleanup_thread.start()
        logger.info("定期清理任务已启动")
    
    def _cleanup_expired_data(self, tank_id: str = None) -> None:
        """清理过期的数据
        
        Args:
            tank_id: 可选，指定要清理的罐ID，None表示清理所有罐
        
        该方法通过以下步骤清理过期数据：
        1. 计算数据过期时间点（基于当前时间减去存储天数）
        2. 确定需要清理的罐列表
        3. 对每个罐，过滤掉过期的历史数据记录
        4. 记录清理操作的结果，包括删除的记录数量
        
        使用线程锁确保数据操作的原子性和线程安全。
        """
        try:
            # 计算过期时间点
            cutoff_time = (datetime.now() - timedelta(days=self.storage_days)).isoformat()
            
            with self.data_lock:
                # 确定要清理的罐
                tanks_to_clean = [tank_id] if tank_id else self.tanks_history.keys()
                
                for tid in tanks_to_clean:
                    if tid in self.tanks_history:
                        # 过滤出未过期的数据
                        filtered_history = [h for h in self.tanks_history[tid] if h['timestamp'] >= cutoff_time]
                        
                        # 如果删除了数据，记录日志
                        if len(filtered_history) < len(self.tanks_history[tid]):
                            removed_count = len(self.tanks_history[tid]) - len(filtered_history)
                            self.tanks_history[tid] = filtered_history
                            logger.info(f"已清理罐 {tid} 的过期数据，共删除 {removed_count} 条记录")
        except Exception as e:
            logger.error(f"清理过期数据时出错: {str(e)}")
    
    def set_storage_days(self, days: int) -> int:
        """设置数据存储天数
        
        Args:
            days: 数据存储天数
        
        Returns:
            int: 设置后的存储天数
        """
        if days > 0:
            with self.data_lock:
                old_days = self.storage_days
                self.storage_days = days
                logger.info(f"数据存储天数已从 {old_days} 天修改为 {days} 天")
                
                # 立即清理过期数据
                self._cleanup_expired_data()
                
                # 保存更改
                self._save_history_data()
            return days
        else:
            logger.warning(f"无效的存储天数: {days}，必须大于0")
            return self.storage_days
    
    def get_storage_days(self) -> int:
        """获取当前数据存储天数
        
        Returns:
            int: 当前存储天数
        """
        return self.storage_days
    
    def get_max_history_points(self) -> int:
        """获取每个罐的历史数据点最大数量
        
        Returns:
            int: 当前设置的最大历史数据点数量
        """
        return self.max_history_points
    
    def set_max_history_points(self, points: int) -> int:
        """设置每个罐的历史数据点最大数量
        
        Args:
            points: 新的最大历史数据点数量
        
        Returns:
            int: 设置后的最大历史数据点数量
        """
        # 限制范围，防止设置过小或过大的值
        if points < 100:
            points = 100
        elif points > 100000:
            points = 100000
        
        with self.data_lock:
            old_points = self.max_history_points
            self.max_history_points = points
            logger.info(f"每个罐的历史数据点数量已从 {old_points} 修改为 {points}")
            
            # 清理所有罐的历史数据，确保不超过新的限制
            for tank_id in self.tanks_history:
                if len(self.tanks_history[tank_id]) > self.max_history_points:
                    # 保留最新的数据点
                    self.tanks_history[tank_id] = self.tanks_history[tank_id][-self.max_history_points:]
            
            # 保存更改
            self._save_history_data()
        
        return self.max_history_points