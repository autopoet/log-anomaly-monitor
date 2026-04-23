# 系统设计

## 1. 总体设计

本系统由日志采集节点、RabbitMQ 消息队列、日志分析服务、SQLite 数据库和 Web 监控服务组成。整体流程是：采集节点持续生成日志并发送到消息队列，分析服务消费日志并计算统计结果，Web 服务再将分析结果和告警信息实时推送到前端页面。

```text
+----------------+       +----------------+       +----------------+
| 日志采集节点    | ----> | RabbitMQ       | ----> | 日志分析服务    |
| producer.py    |       | logs.raw       |       | consumer.py    |
+----------------+       +----------------+       +-------+--------+
                                                          |
                                                          v
                         +----------------+       +----------------+
                         | SQLite         | <---- | 分析结果/告警   |
                         | log_monitor.db |       | 持久化          |
                         +-------+--------+       +-------+--------+
                                 ^                        |
                                 |                        v
                         +-------+--------+       +----------------+
                         | Web 监控服务    | <---- | RabbitMQ       |
                         | FastAPI        |       | logs.analysis  |
                         +----------------+       | logs.alerts    |
                                                  +----------------+
```

## 2. 消息队列设计

系统使用 RabbitMQ 作为 MOM 消息队列。为了让不同类型的消息职责清晰，设计了三个队列：

| 队列名 | 生产者 | 消费者 | 作用 |
| --- | --- | --- | --- |
| `logs.raw` | 日志采集节点 | 日志分析服务 | 保存原始日志消息 |
| `logs.analysis` | 日志分析服务 | Web 监控服务 | 保存周期性分析结果 |
| `logs.alerts` | 日志分析服务 | Web 监控服务 | 保存严重告警消息 |

这样采集节点只负责生产日志，不需要关心分析逻辑；Web 服务也不直接处理原始日志，只接收已经计算好的分析结果。

## 3. 模块划分

项目目录结构如下：

```text
collector/
  producer.py
analyzer/
  consumer.py
  detector.py
web/
  main.py
  static/
common/
  config.py
  models.py
  mq.py
  storage.py
docs/
tests/
```

### 3.1 `collector` 模块

`collector` 模块用于模拟分布式日志采集节点。每个采集节点启动后会不断随机选择一台设备，生成一条日志消息，并发布到 `logs.raw` 队列。

项目中预设了几类设备：

- `device_normal_01`：正常设备，INFO 较多。
- `device_normal_02`：正常设备，偶尔 WARN/ERROR。
- `device_warn_01`：WARN 较多。
- `device_error_01`：ERROR 较多，容易触发严重告警。
- `device_flaky_01`：状态波动较明显。

### 3.2 `analyzer` 模块

`analyzer` 模块负责日志消费、统计和告警判断。

主要逻辑包括：

- 从 `logs.raw` 队列消费原始日志。
- 按 `device_id` 为每台设备维护独立状态。
- 使用滑动窗口保存最近 `N` 条日志。
- 统计 WARN/ERROR 数量和比例。
- 记录最近一次 ERROR。
- 每隔 `T` 秒发布分析结果到 `logs.analysis`。
- 当最近 `S` 秒内 ERROR 占比超过阈值时，发布告警到 `logs.alerts`。

其中 `detector.py` 中的检测逻辑与 RabbitMQ 解耦，便于单元测试。

### 3.3 `web` 模块

`web` 模块使用 FastAPI 实现，主要提供：

- 静态监控页面。
- 查询设备最新分析结果的接口。
- 查询设备趋势数据的接口。
- 查询最近告警的接口。
- WebSocket 实时推送分析结果和告警信息。

前端页面使用原生 JavaScript 和 ECharts，展示设备卡片、告警信息和 WARN/ERROR 趋势折线图。

### 3.4 `common` 模块

`common` 模块保存多个服务共用的代码：

- `config.py`：读取环境变量配置。
- `models.py`：定义日志、分析结果和告警的数据模型。
- `mq.py`：封装 RabbitMQ 队列声明、发布和消费。
- `storage.py`：封装 SQLite 建表、写入和查询。

## 4. 数据模型

### 4.1 原始日志 `LogEvent`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `device_id` | 字符串 | 设备编号 |
| `timestamp` | 时间 | 日志产生时间 |
| `log_level` | 字符串 | 日志级别，取值为 `INFO/WARN/ERROR` |
| `message` | 字符串 | 日志内容 |

### 4.2 分析结果 `AnalysisResult`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `device_id` | 字符串 | 设备编号 |
| `timestamp` | 时间 | 分析结果生成时间 |
| `total_count` | 整数 | 当前窗口日志总数 |
| `warn_count` | 整数 | 当前窗口 WARN 数量 |
| `error_count` | 整数 | 当前窗口 ERROR 数量 |
| `warn_ratio` | 小数 | WARN 占比 |
| `error_ratio` | 小数 | ERROR 占比 |
| `latest_error_message` | 字符串或空 | 最近一次 ERROR 内容 |
| `latest_error_timestamp` | 时间或空 | 最近一次 ERROR 时间 |
| `severe` | 布尔值 | 当前是否处于严重告警状态 |
| `alert_count` | 整数 | 该设备累计告警次数 |

### 4.3 告警消息 `AlertEvent`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `device_id` | 字符串 | 设备编号 |
| `timestamp` | 时间 | 告警产生时间 |
| `error_ratio` | 小数 | 告警窗口内 ERROR 占比 |
| `window_seconds` | 整数 | 检测窗口大小 |
| `message` | 字符串 | 告警说明 |

## 5. 异常检测设计

分析服务对每台设备维护两种窗口：

- 计数窗口：最近 `N` 条日志，用于周期性统计 WARN/ERROR 占比。
- 时间窗口：最近 `S` 秒内的日志，用于判断严重告警。

严重告警判断公式为：

```text
最近 S 秒内 ERROR 数量 / 最近 S 秒内日志总数 > 阈值
```

默认阈值为 `0.5`，也就是 ERROR 占比超过 50% 时触发严重告警。

为了避免同一设备在异常期间重复产生大量告警，系统记录设备当前是否已经处于严重状态。只有从正常状态进入严重状态时，才会发送新的告警消息。

## 6. 数据持久化设计

项目使用 SQLite 保存运行数据，主要有三张表：

- `logs`：保存原始日志。
- `analysis_results`：保存周期性分析结果。
- `alerts`：保存严重告警记录。

SQLite 的作用主要是支持页面刷新后的历史数据查询，以及趋势图的最近数据展示。对于本课程实验来说，SQLite 足够轻量，也不需要额外安装数据库服务。

## 7. 接口设计

| 接口 | 说明 |
| --- | --- |
| `GET /` | 打开监控页面 |
| `GET /api/devices` | 查询所有设备的最新状态 |
| `GET /api/devices/{device_id}/summary` | 查询某台设备最新状态 |
| `GET /api/devices/{device_id}/trend` | 查询某台设备 WARN/ERROR 趋势 |
| `GET /api/alerts` | 查询最近严重告警 |
| `WS /ws/monitor` | 实时推送分析结果和告警消息 |

## 8. 运行流程

1. 通过 Docker Compose 启动 RabbitMQ。
2. 启动日志分析服务，声明并监听需要的队列。
3. 启动 Web 监控服务，准备接收分析结果和告警消息。
4. 启动一个或多个日志采集节点。
5. 采集节点持续发布原始日志到 `logs.raw`。
6. 分析服务消费日志，更新每台设备的滑动窗口。
7. 分析服务定时发布分析结果到 `logs.analysis`。
8. 如果满足严重告警条件，分析服务发布告警到 `logs.alerts`。
9. Web 服务通过 WebSocket 将结果推送到前端页面。

## 9. 边界情况处理

- 如果某台设备暂时没有日志，则统计数量和比例为 0。
- 不同设备的日志状态相互独立，互不影响。
- 如果 Web 接口查询不存在的设备，返回 404。
- 如果队列中出现格式错误的消息，分析服务会记录错误并忽略该消息。
- 告警只在状态切换时触发，避免同一异常持续刷屏。
- 日志时间使用 ISO 字符串存储，便于 SQLite 查询和前端展示。
