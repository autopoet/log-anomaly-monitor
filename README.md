# 分布式日志异常检测与监控系统

这是一个基于 RabbitMQ 的分布式日志采集、异常分析和实时可视化小项目，主要用于完成课程第二次作业。项目通过多个模拟采集节点生成设备日志，再由分析服务按设备维度统计 WARN/ERROR 占比，并在前端页面中实时展示设备状态和告警信息。

项目没有做得特别复杂，重点放在消息队列解耦、按设备独立分析、异常检测和实时展示这几部分，方便本地运行和课程演示。

## 功能说明

- 使用多个进程模拟分布式日志采集节点。
- 每个采集节点可以指定自己的节点编号。
- 采集节点默认每 100ms 生成一条日志消息。
- 日志消息通过 RabbitMQ 发布到原始日志队列。
- 分析服务订阅原始日志队列，并按 `device_id` 独立维护最近 `N` 条日志。
- 统计每台设备最近日志中的 WARN 占比和 ERROR 占比。
- 记录每台设备最近一次 ERROR 事件及其时间。
- 每隔 `T` 秒将分析结果发布到分析结果队列。
- 如果最近 `S` 秒内 ERROR 占比超过 50%，生成严重告警消息。
- 使用 SQLite 保存原始日志、分析结果和告警记录。
- 使用 FastAPI + WebSocket + ECharts 实现实时监控页面。

## 技术栈

- Python 3.11+
- RabbitMQ
- FastAPI
- WebSocket
- SQLite
- ECharts
- Pytest

## 系统结构

```text
日志采集节点 -> RabbitMQ logs.raw -> 日志分析服务 -> RabbitMQ logs.analysis
                                      |            -> RabbitMQ logs.alerts
                                      v
                                   SQLite
                                      ^
                                      |
                               FastAPI + WebSocket -> 实时监控页面
```

## 日志消息格式

日志采集节点生成的消息为 JSON 格式，示例如下：

```json
{
  "device_id": "device_01",
  "timestamp": "2026-04-23 12:00:00",
  "log_level": "INFO",
  "message": "system is healthy"
}
```

其中 `log_level` 取值为：

- `INFO`
- `WARN`
- `ERROR`

## 快速启动

先进入项目目录：

```bash
cd log-anomaly-monitor
```

安装依赖：

```bash
python -m pip install -r requirements.txt
```

### 方式一：Docker 一键启动完整系统

如果电脑已经安装 Docker Desktop，可以直接启动完整系统：

```bash
docker compose up --build
```

启动后访问监控页面：

```text
http://localhost:8000
```

RabbitMQ 管理页面为：

```text
http://localhost:15672
guest / guest
```

这个方式会同时启动：

- RabbitMQ
- 日志分析服务
- 日志采集节点
- Web 监控服务

### 方式二：手动启动完整实验链路

如果只想先启动 RabbitMQ，可以执行：

```bash
docker compose up -d rabbitmq
```

然后分别打开多个终端启动下面几个服务。

启动日志分析服务：

```bash
python -m analyzer.consumer
```

启动日志采集节点，建议另开一个终端：

```bash
python -m collector.producer --node-id collector-01
```

如果想模拟多个采集节点，可以再开一个终端：

```bash
python -m collector.producer --node-id collector-02
```

启动 Web 监控服务：

```bash
python -m uvicorn web.main:app --reload
```

浏览器打开：

```text
http://localhost:8000
```

页面中可以看到设备数量、严重告警数量、各设备 WARN/ERROR 占比、最近一次 ERROR 事件以及 WARN/ERROR 趋势折线图。

### 方式三：可视化预览模式

如果电脑没有 Docker，也没有安装 RabbitMQ，可以使用预览模式先查看页面效果：

```bash
python -m uvicorn web.preview:app --reload
```

然后打开：

```text
http://localhost:8000
```

预览模式会在 Web 服务内部生成模拟分析数据，并通过 WebSocket 推送到页面。它只用于快速查看可视化效果和截图，不替代 RabbitMQ 完整实验链路。真正的消息队列功能仍然需要使用方式一或方式二运行。

## 配置项

项目通过环境变量读取配置。默认配置已经可以直接运行，也可以参考 `.env.example` 修改。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | RabbitMQ 连接地址 |
| `RAW_LOG_QUEUE` | `logs.raw` | 原始日志队列 |
| `ANALYSIS_QUEUE` | `logs.analysis` | 分析结果队列 |
| `ALERT_QUEUE` | `logs.alerts` | 告警队列 |
| `WINDOW_SIZE` | `100` | 每个设备保留的最近日志条数 |
| `ANALYSIS_INTERVAL_SECONDS` | `3` | 分析结果发布间隔 |
| `ALERT_WINDOW_SECONDS` | `10` | 严重告警检测时间窗口 |
| `ERROR_RATIO_THRESHOLD` | `0.5` | ERROR 占比告警阈值 |
| `SQLITE_PATH` | `data/log_monitor.db` | SQLite 数据库路径 |

## 目录结构

```text
Dockerfile
docker-compose.yml
analyzer/
  consumer.py      # 消费原始日志并发布分析结果
  detector.py      # 滑动窗口统计和异常检测逻辑
collector/
  producer.py      # 模拟日志采集节点
common/
  config.py        # 配置读取
  models.py        # 共享数据模型
  mq.py            # RabbitMQ 操作封装
  storage.py       # SQLite 存储和查询
docs/
  requirements.md  # 需求分析
  design.md        # 系统设计
web/
  main.py          # FastAPI 服务和 WebSocket 推送
  preview.py       # 无 RabbitMQ 的可视化预览入口
  static/          # 前端页面资源
tests/
  test_detector.py # 异常检测逻辑测试
```

## 测试

运行单元测试：

```bash
python -m pytest
```

当前测试主要覆盖：

- WARN/ERROR 占比计算。
- 最近一次 ERROR 记录。
- 最近 `N` 条日志窗口维护。
- 不同设备之间的状态隔离。
- 严重告警只在状态切换时触发，避免重复刷屏。

## 作业文档

`docs/` 目录中包含本项目的需求分析和系统设计说明：

- `docs/requirements.md`
- `docs/design.md`

这两份文档可以作为实验报告的基础材料。

## 后续可以改进的地方

- 接入真实日志文件或 HTTP 日志上报接口。
- 增加邮件、Webhook 等告警通知方式。
- 增加设备分组和筛选功能。
- 给采集器、分析器和 Web 服务分别补充 Dockerfile。
- 增加更多异常检测规则，例如连续 ERROR 次数、WARN 突增等。
