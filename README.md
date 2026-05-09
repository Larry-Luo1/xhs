# 小红书爬虫项目

基于协议逆向的小红书评论采集系统。

## 项目结构

```
xhs/
├── analysis.md          # 技术方案分析文档
├── details.md           # 需求和方案详情
├── demo.py              # 演示脚本
├── README.md            # 项目说明
├── requirements.txt     # Python依赖
├── src/                 # 源代码
│   ├── crawler/         # 爬虫核心
│   ├── account/         # 账号池管理
│   ├── proxy/           # 代理池管理
│   └── utils/           # 工具函数
├── tests/               # 测试代码
├── config/              # 配置文件
└── logs/                # 日志输出
```

## 快速开始

### 环境要求

- Python 3.9+
- Chrome/Chromium
- 小红书账号（测试用）
- 代理IP（可选）

### 安装依赖

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
```

### 基础使用

```python
from src.crawler import XhsCrawler

crawler = XhsCrawler()
comments = crawler.fetch_comments(note_id="xxx", account_id="001")
```

## 技术方案

详见 [analysis.md](./analysis.md) 和 [details.md](./details.md)

推荐架构：**方案B（JS注入+签名调用）**

## 核心模块

- **AccountPool**: 多账号管理与状态机
- **ProxyPool**: IP轮转与绑定
- **SignService**: 请求签名生成
- **ThrottleManager**: 请求频率控制
- **XsecTokenManager**: Token刷新管理

## 注意事项

⚠️ 本项目仅用于学习研究和小范围内部测试，不用于大规模商业行为

## 开发环境

推荐：**Ubuntu 22.04 LTS** 或 **WSL2 + Ubuntu**

详见 [analysis.md](./analysis.md) 中的平台选择指南

## License

Internal Use Only
