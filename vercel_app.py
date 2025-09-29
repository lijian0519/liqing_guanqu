# -*- coding: utf-8 -*-

# 导入必要的模块
import os
import sys
import json
import logging
from datetime import datetime

# 设置默认编码为UTF-8
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 设置环境变量，确保在Vercel环境中正确运行
os.environ['CONFIG_NAME'] = 'production'
os.environ['DEBUG'] = 'false'
os.environ['DISABLE_SOCKETIO'] = 'true'
os.environ['MAX_TANKS'] = '11'
os.environ['PORT'] = '80'

# 获取当前文件目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 导入Flask
from flask import Flask, jsonify, request, render_template

# 初始化Flask应用，并设置模板和静态文件路径
app = Flask(
    __name__, 
    template_folder=os.path.join(current_dir, 'templates'),
    static_folder=os.path.join(current_dir, 'static')
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('VercelApp')

# 模拟数据管理器类，用于Vercel环境，避免文件操作和后台线程
class MockDataManager:
    def __init__(self):
        # 初始化内存中的数据结构
        self.tanks_data = {}
        self.initialize_tanks()
        logger.info("MockDataManager已初始化")
    
    def initialize_tanks(self):
        # 初始化11个罐的模拟数据
        max_tanks = int(os.environ.get('MAX_TANKS', 11))
        for i in range(1, max_tanks + 1):
            self.tanks_data[str(i)] = {
                'tank_id': str(i),
                'timestamp': datetime.now().isoformat(),
                'temperature': 150.0,
                'level': 50.0,
                'pressure': 1.0,
                'error': 0.0,
                'status': 'normal',
                'alert_message': '',
                'name': f'{i}#沥青罐'
            }
    
    def get_tank_data(self, tank_id=None):
        if tank_id:
            return self.tanks_data.get(str(tank_id), {})
        return self.tanks_data
    
    def get_tank_history(self, tank_id, start_time=None, end_time=None, limit=10):
        # 返回模拟历史数据
        tank_id_str = str(tank_id)
        if tank_id_str not in self.tanks_data:
            return []
        
        history = []
        # 生成最近10个时间点的模拟数据
        for i in range(limit):
            timestamp = (datetime.now() - timedelta(minutes=i*10)).isoformat()
            history.append({
                'timestamp': timestamp,
                'temperature': 150.0 + (i % 5 - 2),
                'level': 50.0 + (i % 10 - 5),
                'pressure': 1.0,
                'status': 'normal'
            })
        
        return history
    
    def get_all_tanks_summary(self):
        summary = {}
        for tank_id, data in self.tanks_data.items():
            summary[tank_id] = {
                'tank_id': tank_id,
                'status': data['status'],
                'temperature': data['temperature'],
                'level': data['level'],
                'pressure': data['pressure'],
                'alert_message': data['alert_message'],
                'last_updated': data['timestamp'],
                'name': data['name']
            }
        return summary

# 初始化模拟数据管理器
data_manager = MockDataManager()

# 健康检查端点
@app.route('/api/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'environment': 'Vercel Serverless'
    })

# 获取所有罐数据的API端点
@app.route('/api/tanks')
def get_tanks():
    try:
        # 返回模拟的罐数据
        tanks = {}
        max_tanks = int(os.environ.get('MAX_TANKS', 11))
        for i in range(1, max_tanks + 1):
            tanks[i] = {
                'id': i,
                'name': f'{i}#沥青罐',
                'temperature': 150.0,
                'level': 50.0,
                'weight': 0.0,
                'height': 8.0,
                'high_limit': 6.4,
                'alarm_shown': False,
                'error': 0.0
            }
        return jsonify({'success': True, 'data': tanks})
    except Exception as e:
        logger.error(f"获取罐数据时出错: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# 获取当前罐数据的API端点
@app.route('/api/tanks/data')
def get_tanks_data():
    try:
        # 返回模拟的罐数据
        tanks_data = {}
        max_tanks = int(os.environ.get('MAX_TANKS', 11))
        for i in range(1, max_tanks + 1):
            tanks_data[i] = {
                'id': i,
                'name': f'{i}#沥青罐',
                'temperature': 150.0,
                'level': 50.0,
                'weight': 0.0,
                'height': 8.0,
                'high_limit': 6.4,
                'alarm_shown': False,
                'error': 0.0
            }
        return jsonify({'success': True, 'data': tanks_data})
    except Exception as e:
        logger.error(f"获取罐数据时出错: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# MQTT状态端点
@app.route('/api/mqtt/status')
def mqtt_status():
    # 在Vercel环境中返回模拟的MQTT状态
    return jsonify({
        'connected': False,
        'message': '在Vercel环境中使用模拟数据',
        'environment': 'Vercel Serverless'
    })

# 存储天数端点
@app.route('/api/storage/days', methods=['GET', 'POST'])
def storage_days():
    if request.method == 'POST':
        try:
            data = request.json
            days = data.get('days', 7)
            # 在Vercel环境中，这个设置不会持久化
            return jsonify({'success': True, 'days': days, 'message': '在Vercel环境中，此设置不会持久化'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    else:
        # 返回默认值
        return jsonify({'success': True, 'days': 7})

# 历史数据端点
@app.route('/api/history/points', methods=['GET', 'POST'])
def history_points():
    if request.method == 'POST':
        try:
            data = request.json
            points = data.get('points', 1000)
            # 在Vercel环境中，这个设置不会持久化
            return jsonify({'success': True, 'points': points, 'message': '在Vercel环境中，此设置不会持久化'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    else:
        # 返回默认值
        return jsonify({'success': True, 'points': 1000})

# 单个罐的历史数据端点
@app.route('/api/history/<tank_id>')
def get_tank_history(tank_id):
    try:
        limit = request.args.get('limit', 10, type=int)
        history = data_manager.get_tank_history(tank_id, limit=limit)
        return jsonify({'success': True, 'data': history})
    except Exception as e:
        logger.error(f"获取罐历史数据时出错: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# 主页路由
@app.route('/')
@app.route('/index')
def index():
    try:
        # 生成模拟的罐数据
        max_tanks = int(os.environ.get('MAX_TANKS', 11))
        tanks = {}
        for i in range(1, max_tanks + 1):
            tanks[i] = {
                'id': i,
                'name': f'{i}#沥青罐',
                'temperature': 150.0 + (i * 2),  # 给每个罐一个不同的温度
                'level': 3.0 + (i * 0.3),  # 给每个罐一个不同的液位
                'weight': 20.0 + (i * 2),  # 给每个罐一个不同的重量
                'height': 8.0,
                'high_limit': 6.4,
                'alarm_shown': False,
                'error': 0.0
            }
        
        # 渲染完整的index.html模板，并传递必要的变量
        return render_template('index.html', tanks=tanks)
    except Exception as e:
        logger.error(f"加载主页时出错: {str(e)}")
        return str(e), 500

# 创建WSGI应用入口
application = app

# 确保在模块加载时不会执行任何初始化代码

# 直接运行时使用
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)