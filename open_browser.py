import webbrowser
import time

print("正在打开浏览器访问MQTT Web界面...")

# 打开默认浏览器访问Web界面
url = "http://127.0.0.1:5000"
webbrowser.open(url)

# 显示提示信息
print(f"浏览器已尝试打开，访问地址: {url}")
print("如果浏览器未自动打开，请手动在浏览器中输入上述地址")

# 等待用户看到提示
print("\n按回车键退出...")
input()