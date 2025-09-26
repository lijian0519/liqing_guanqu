# -*- coding: utf-8 -*-

"""WSGI应用入口点，用于Vercel等无服务器平台部署

这个文件提供了一个纯WSGI兼容的应用入口点，不依赖SocketIO的长连接功能，
适合在Vercel等无服务器环境中运行。
"""

import os
import sys
from datetime import datetime

# 设置默认编码为UTF-8
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 确保在Vercel环境中正确加载环境变量
if 'VERCEL' in os.environ:
    # 生产环境设置
    os.environ['CONFIG_NAME'] = 'production'
    os.environ['DEBUG'] = 'false'
    os.environ['PORT'] = '80'

# 导入Flask应用
from app import app

# 禁用SocketIO功能以适应Vercel的无服务器环境
# 这里应该设置环境变量，而不是app.config
os.environ['DISABLE_SOCKETIO'] = 'true'

# 添加一个简单的健康检查端点
@app.route('/api/health')
def health_check():
    """健康检查端点，用于Vercel监控应用状态"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "environment": os.environ.get('CONFIG_NAME', 'unknown')
    }

# WSGI应用入口点
def application(environ, start_response):
    """标准WSGI应用入口点函数"""
    # 将环境变量传递给应用
    for key, value in environ.items():
        if key.startswith('HTTP_'):
            # 将HTTP头转换为环境变量
            env_key = key[5:].upper().replace('-', '_')
            os.environ[env_key] = value
        elif key == 'PATH_INFO':
            os.environ['PATH_INFO'] = value

    # 使用Flask的WSGI应用处理请求
    return app(environ, start_response)

# 如果直接运行此文件，则启动开发服务器
if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'true').lower() == 'true'
    
    print(f"Starting WSGI server on http://{host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)