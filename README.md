# Backpack 交易所自动交易机器人

这是一个基于 Python 的 Backpack 交易所自动交易机器人，实现了智能的限价买入策略。

## 🎯 策略说明

### 交易策略概述
本机器人采用保守的限价买入策略，旨在以最优价格进行交易：

1. **持仓优先平仓**：如果检测到现有仓位，立即执行市价平仓
2. **限价买入**：以当前最高买价（买一价）下限价买单
3. **智能订单管理**：根据市场变化智能管理订单

### 订单管理逻辑

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
   
   # 交易配置
   TRADING_SYMBOL=SOL          # 交易代币符号
   TRADING_LEVERAGE=10         # 杠杆倍数
   TRADING_AMOUNT=100.0        # 单次交易金额(USDT)
   ```

### API 密钥说明
- `BACKPACK_API_KEY`: Backpack 交易所的 API Key
- `BACKPACK_PRIVATE_KEY`: ED25519 私钥（需要 Base64 编码）

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

### 使用建议
1. **合理设置交易金额**：根据你的风险承受能力设置 `TRADING_AMOUNT`
2. **选择合适杠杆**：杠杆倍数越高风险越大
3. **网络稳定性**：确保运行环境网络稳定
4. **定期检查**：定期检查程序运行状态和账户资金

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