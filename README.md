# MQTT Web界面监控系统

这是一个基于Web的MQTT监控系统，用于实时监控沥青罐的温度、液位和吨位数据。本系统基于原有的`python_mqtt_client_optimized.py`客户端应用，并将其功能扩展到Web平台，方便用户通过浏览器访问和监控数据。

## 项目功能

- 实时监控多个沥青罐的温度、液位和吨位数据
- 通过Web界面显示监控数据和可视化图表
- 支持MQTT协议的消息发布和订阅
- 实现数据的实时更新和历史数据查看
- 提供报警功能，当数据超过阈值时发出警告
- 用户友好的Web界面，支持响应式设计

## 技术栈

- **后端**：Python Flask
- **前端**：HTML, CSS, JavaScript
- **数据可视化**：Chart.js
- **消息协议**：MQTT (Paho-MQTT)
- **Web服务器**：Flask内置开发服务器 (生产环境可使用Gunicorn/uWSGI)

## 项目结构

```
mqtt_web_interface/
├── app.py                # Flask应用主入口
├── requirements.txt      # 项目依赖
├── static/               # 静态资源文件
│   ├── css/              # CSS样式文件
│   ├── js/               # JavaScript脚本
│   └── images/           # 图片资源
├── templates/            # HTML模板文件
├── mqtt/                 # MQTT相关代码
│   ├── client.py         # MQTT客户端实现
│   └── handlers.py       # MQTT消息处理
├── data/                 # 数据管理
│   ├── manager.py        # 数据管理器
│   └── models.py         # 数据模型
└── config.py             # 配置文件
```

## 安装和运行

1. 安装依赖
   ```
   pip install -r requirements.txt
   ```

2. 配置MQTT连接参数
   在`config.py`中设置MQTT服务器地址、端口、用户名和密码等参数

3. 运行应用
   ```
   python app.py
   ```

4. 在浏览器中访问
   ```
   http://localhost:5000
   ```

## 开发说明

本项目基于原有`python_mqtt_client_optimized.py`客户端应用开发，保留了其核心功能并扩展到Web平台。开发过程中应注意以下几点：

1. 保持MQTT连接的稳定性
2. 优化数据传输效率，减少不必要的网络请求
3. 确保Web界面的响应速度和用户体验
4. 实现良好的错误处理和日志记录机制
5. 考虑安全性，特别是在处理MQTT连接凭证时

## 注意事项

- 本项目在开发环境中使用Flask内置的开发服务器，生产环境中应使用专业的Web服务器
- 定期备份数据，避免数据丢失
- 根据实际需求调整监控频率和报警阈值
- 当监控的数据量较大时，考虑使用数据库存储历史数据