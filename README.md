# Backpack 交易所自动交易机器人

这是一个基于 Python 的 Backpack 交易所自动交易机器人，实现了智能的限价买入策略。

## 🎯 策略说明

### 交易模式
本机器人支持两种交易模式：

#### 1. 单账户模式 (Single Mode)
采用保守的限价买入策略，旨在以最优价格进行交易：

1. **持仓优先平仓**：如果检测到现有仓位，立即执行市价平仓
2. **限价买入**：以当前最高买价（买一价）下限价买单
3. **智能订单管理**：根据市场变化智能管理订单

#### 2. 对冲模式 (Dual Hedge Mode)
使用两个账户进行对冲交易，降低市场风险：

1. **双向开仓**：同时在两个账户上开多仓和空仓
2. **等待期**：持仓等待指定时间（默认30秒）
3. **同步平仓**：到期后同时平仓两个账户的仓位
4. **市场对冲**：如果一方先成交，自动对另一方进行市价对冲

### 单账户模式订单管理逻辑

#### 初次运行
- 检测到现有订单时，**自动取消所有订单**，确保持仓干净
- 然后按照正常流程下新的限价买单

#### 订单超时处理
- 订单下单后10秒未成交，触发超时检查
- **智能取消逻辑**：
  - 如果订单价格与当前买最高价相同（误差 < 0.01），**保持订单等待成交**
  - 如果订单价格偏离当前买最高价，**取消订单并重新下单**

#### 仓位管理
- 检测到任何仓位时，立即执行市价平仓
- 平仓完成后，继续执行限价买入策略

### 对冲模式交易逻辑

#### 开仓阶段 (Opening Phase)
- 同时在两个账户上下限价单：账户1做多，账户2做空
- 如果一方先成交，自动对另一方进行市价对冲
- 确保两个账户都有相应的仓位

#### 等待阶段 (Waiting Phase)
- 持仓等待配置的时间（由 `HEDGE_CLOSE_DELAY_SECONDS` 控制）
- 期间监控仓位状态，确保对冲有效

#### 平仓阶段 (Closing Phase)
- 等待期结束后，同时对两个账户进行平仓操作
- 优先使用限价单平仓，如果无法成交则使用市价单
- 确保两个账户的仓位都完全平仓

#### 风险控制
- 实时监控两个账户的仓位状态
- 自动处理部分成交、订单取消等异常情况
- 如果对冲失败，自动进行风险控制

## 🔧 配置说明

### 创建配置文件
1. 在 `config/` 目录下创建配置文件：
   ```bash
   cp config/.env.prod.template config/.env.prod
   ```

2. 编辑配置文件，填入你的 API 信息：
   ```env
   # Backpack API 配置
   BACKPACK_API_KEY=your_api_key_here
   BACKPACK_PRIVATE_KEY=your_base64_encoded_private_key_here
   BACKPACK_BASE_URL=https://api.backpack.exchange
   
   # 对冲模式需要第二个账户（仅在 dual_hedge 模式下需要）
   BACKPACK_API_KEY2=your_second_account_api_key_here
   BACKPACK_PRIVATE_KEY2=your_second_account_private_key_here
   
   # 交易配置
   TRADING_MODE=single         # 交易模式: single 或 dual_hedge
   TRADING_SYMBOL=SOL          # 交易代币符号
   TRADING_LEVERAGE=10         # 杠杆倍数
   TRADING_AMOUNT=100.0        # 单次交易金额(USDT)
   
   # 对冲模式配置（仅在 dual_hedge 模式下生效）
   HEDGE_CLOSE_DELAY_SECONDS=30  # 对冲持仓时间（秒）
   ```

### 配置参数说明

#### API 配置
- `BACKPACK_API_KEY`: 主账户的 API Key
- `BACKPACK_PRIVATE_KEY`: 主账户的 API Secret
- `BACKPACK_API_KEY2`: 第二账户的 API Key（仅对冲模式需要）
- `BACKPACK_PRIVATE_KEY2`: 第二账户的 API Secret（仅对冲模式需要）
- `BACKPACK_BASE_URL`: Backpack API 地址

#### 交易配置
- `TRADING_MODE`: 交易模式
  - `single`: 单账户模式（默认）
  - `dual_hedge`: 双账户对冲模式
- `TRADING_SYMBOL`: 交易代币符号
- `TRADING_LEVERAGE`: 杠杆倍数
- `TRADING_AMOUNT`: 单次交易金额(USDT)

#### 对冲模式配置
- `HEDGE_CLOSE_DELAY_SECONDS`: 对冲持仓时间（秒），默认30秒
  - 这是开仓后等待平仓的时间
  - 期间可以从价差中获利
  - 建议根据市场波动性调整

## 🚀 启动方式

### 1. 原生 Python 启动

#### 环境准备
```bash
# 安装依赖
pip install -r requirements.txt
```

#### 启动应用
```bash
ENV=prod python main.py
```

### 2. Docker 启动

#### 构建和启动
```bash
# 构建并启动（后台运行）
docker-compose up --build -d

# 查看日志
docker-compose logs -f app

# 停止服务
docker-compose down
```

#### 完整重建
```bash
# 使用提供的重建脚本
./rebuild.sh
```

该脚本会：
1. 停止现有容器
2. 删除旧镜像
3. 重新构建并启动

## 📊 监控和日志

### 日志文件
- 日志文件位置：`logs/app.log`
- Docker 启动时会自动映射日志目录

### 关键日志信息
- 仓位检测和平仓操作
- 订单下单和取消记录
- 价格获取和比较
- 错误和异常处理

## ⚠️ 注意事项

### 风险提示
1. **资金风险**：本机器人涉及真实资金交易，请谨慎使用
2. **测试建议**：建议先在测试环境充分测试
3. **监控要求**：运行期间请密切关注日志和账户状态
4. **对冲模式风险**：
   - 需要两个独立的 Backpack 账户
   - 确保两个账户都有足够的资金和保证金
   - 网络延迟可能导致对冲不完全
   - 市场剧烈波动时可能影响对冲效果

### 使用建议
1. **合理设置交易金额**：根据你的风险承受能力设置 `TRADING_AMOUNT`
2. **选择合适杠杆**：杠杆倍数越高风险越大
3. **网络稳定性**：确保运行环境网络稳定
4. **定期检查**：定期检查程序运行状态和账户资金
5. **对冲模式建议**：
   - 首次使用建议从小金额开始测试
   - 确保两个账户的API权限完全一致
   - 合理设置对冲持仓时间，避免过短或过长
   - 在市场波动较大时谨慎使用
   - 定期检查两个账户的资金和仓位状态

### 系统要求
- Python 推荐3.12 其他自测
- 稳定的网络连接
- 足够的系统资源

## 📁 项目结构

```
bp-trader/
├── main.py                 # 应用程序入口
├── config/
│   ├── config.py          # 配置管理
│   ├── .env.dev           # 开发环境配置
│   └── .env.prod          # 生产环境配置
├── service/
│   ├── backpack_client.py # Backpack API 客户端
│   └── trading_service.py # 交易服务逻辑
├── utils/
│   └── logger.py          # 日志工具
├── logs/                  # 日志目录
├── docker-compose.yml     # Docker 配置
├── Dockerfile            # Docker 镜像构建文件
├── requirements.txt      # Python 依赖
├── env.sh               # 环境激活脚本
└── rebuild.sh           # Docker 重建脚本
```

## 📞 支持

如果遇到问题，请检查：
1. 配置文件是否正确
2. API 密钥是否有效
3. 网络连接是否稳定
4. 日志中的错误信息

---

**免责声明**：本软件仅供学习和研究使用，使用者需要自行承担所有交易风险。作者不对任何因使用本软件而导致的资金损失承担责任。
