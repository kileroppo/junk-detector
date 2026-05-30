"""鉴真 SDK Webhook 监听示例 - 接收异步评分回调"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# Webhook接收端口
PORT = 9090


class WebhookHandler(BaseHTTPRequestHandler):
    """处理鉴真发送的webhook回调"""

    def do_POST(self):
        # 读取请求体
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        # 解析JSON
        data = json.loads(body)
        # 处理评分结果
        print(f"收到评分回调: {data.get('verdict')} - {data.get('url', '文本评分')}")
        print(f"  分数: {data.get('overall_score')}")
        print(f"  解释: {data.get('explanation', '无')}")
        # 返回200表示接收成功
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status": "received"}')

    def log_message(self, format, *args):
        pass  # 静默HTTP日志


# 启动webhook监听服务器
print(f"鉴真 Webhook 监听器启动于 http://localhost:{PORT}")
print("在鉴真API配置webhook_url为此地址即可接收回调")
server = HTTPServer(("", PORT), WebhookHandler)
server.serve_forever()
