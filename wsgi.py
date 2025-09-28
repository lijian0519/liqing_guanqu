# -*- coding: utf-8 -*-

"""WSGI应用入口点，用于Vercel等无服务器平台部署

这个文件提供了一个纯WSGI兼容的应用入口点，不依赖SocketIO的长连接功能，
适合在Vercel等无服务器环境中运行。
"""

import os
import sys
import importlib
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
    os.environ['MAX_TANKS'] = '11'

# 禁用SocketIO功能以适应Vercel的无服务器环境
os.environ['DISABLE_SOCKETIO'] = 'true'

# 初始化Flask应用，但避免立即导入app模块
app = None
initialized = False

def initialize_app():
    """在第一次请求时初始化Flask应用，避免在导入时触发初始化"""
    global app, initialized
    if not initialized:
        # 确保在导入app之前环境变量已设置
        print("正在初始化Flask应用...")
        
        # 动态导入app模块，但阻止其自动初始化
        # 保存原始的initialize_app函数
        import app as app_module
        
        # 获取app实例
        app = app_module.app
        
        # 添加健康检查端点
        @app.route('/api/health')
        def health_check():
            """健康检查端点，用于Vercel监控应用状态"""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "environment": os.environ.get('CONFIG_NAME', 'unknown')
            }
        
        initialized = True
        print("Flask应用初始化完成")

# WSGI应用入口点
def application(environ, start_response):
    """标准WSGI应用入口点函数，在第一次请求时初始化应用"""
    # 将环境变量传递给应用
    for key, value in environ.items():
        if key.startswith('HTTP_'):
            # 将HTTP头转换为环境变量
            env_key = key[5:].upper().replace('-', '_')
            os.environ[env_key] = value
        elif key == 'PATH_INFO':
            os.environ['PATH_INFO'] = value
    
    # 延迟初始化应用
    initialize_app()

    # 使用Flask的WSGI应用处理请求
    return app(environ, start_response)

# 如果直接运行此文件，则启动开发服务器
if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'true').lower() == 'true'
    
    # 立即初始化应用
    initialize_app()
    
    print(f"Starting WSGI server on http://{host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)