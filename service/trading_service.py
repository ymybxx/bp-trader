from typing import Dict, List, Optional
import time
from decimal import Decimal
import datetime

from service.backpack_client import BackpackClient
from config.config import TRADING_CONFIG
from utils.logger import setup_logger

logger = setup_logger(__name__)


class TradingService:
    def __init__(self):
        self.client = BackpackClient()
        self.symbol = TRADING_CONFIG["symbol"]
        self.leverage = TRADING_CONFIG["leverage"]
        self.trade_amount = TRADING_CONFIG["trade_amount"]
        self.trading_symbol = f"{self.symbol}_USDC_PERP"
        self.last_order_time = None  # 记录最后下单时间
        self.quantity_precision = None  # 数量精度

    def get_position(self) -> Optional[Dict]:
        """获取指定代币的仓位信息"""
        try:
            positions = self.client.get_positions()

            # positions是一个数组
            if isinstance(positions, list):
                for position in positions:
                    if position.get("symbol") == self.trading_symbol:
                        quantity = float(position.get("netQuantity", 0))
                        if quantity != 0:
                            logger.info(f"发现{self.symbol}仓位: {quantity}")
                            return position

            return None

        except Exception as e:
            logger.error(f"检查仓位失败: {e}")
            raise

    def get_open_orders(self) -> List[Dict]:
        """获取指定代币的挂单列表"""
        try:
            orders = self.client.get_open_orders(self.symbol)
            symbol_orders = []

            # orders可能是一个数组
            if isinstance(orders, list):
                # 过滤指定代币的挂单
                symbol_orders = [order for order in orders if order.get("symbol") == self.trading_symbol]
            elif isinstance(orders, dict):
                # 如果是字典格式
                open_orders = orders.get("orders", [])
                symbol_orders = [order for order in open_orders if order.get("symbol") == self.trading_symbol]

            if symbol_orders:
                logger.info(f"发现{self.symbol}挂单: {len(symbol_orders)}个")

            return symbol_orders

        except Exception as e:
            logger.error(f"检查挂单失败: {e}")
            return []

    def has_open_orders(self) -> bool:
        """检查是否存在指定代币的挂单"""
        return len(self.get_open_orders()) > 0

    def get_best_bid_price(self) -> Optional[float]:
        """获取买一价"""
        try:
            depth = self.client.get_depth(self.symbol)
            bids = depth.get("bids", [])

            if bids:
                best_bid = bids[-1]  # 最后一个是最高买价
                price = float(best_bid[0])
                logger.info(f"{self.symbol}买一价: {price}")
                return price

            return None

        except Exception as e:
            logger.error(f"获取买一价失败: {e}")
            return None

    def get_quantity_precision(self) -> int:
        """获取数量精度"""
        if self.quantity_precision is not None:
            return self.quantity_precision

        try:
            markets = self.client.get_markets()
            for market in markets:
                if market.get("symbol") == self.trading_symbol:
                    step_size = market.get("filters", {}).get("quantity", {}).get("stepSize")
                    if step_size:
                        # 计算stepSize的小数位数，移除末尾的0
                        step_decimal = Decimal(step_size)
                        precision = len(str(step_decimal).rstrip('0').split('.')[-1])
                        self.quantity_precision = precision
                        logger.info(f"{self.symbol}数量精度: {precision}位小数, stepSize: {step_size}")
                        return precision

            # 如果找不到，默认使用6位精度（适合大多数交易对）
            logger.warning(f"未找到{self.symbol}的精度信息，使用默认6位小数")
            self.quantity_precision = 6
            return 6

        except Exception as e:
            logger.error(f"获取数量精度失败: {e}")
            # 回退到默认精度
            self.quantity_precision = 6
            return 6

    def calculate_order_quantity(self, price: float) -> float:
        """计算下单数量"""
        # 单次交易额 / 价格 = 数量
        # 考虑杠杆率，保证金 = 交易额 / 杠杆率
        margin_needed = self.trade_amount / self.leverage
        quantity = self.trade_amount / price

        # 获取动态精度并四舍五入
        precision = self.get_quantity_precision()
        quantity = round(quantity, precision)

        logger.info(f"计算订单数量: 交易额={self.trade_amount}, 杠杆={self.leverage}, "
                   f"保证金={margin_needed}, 价格={price}, 数量={quantity}, 精度={precision}")

        return quantity

    def place_limit_buy_order(self) -> bool:
        """下限价买单"""
        try:
            # 获取买一价
            best_bid = self.get_best_bid_price()
            if not best_bid:
                logger.error("无法获取买一价")
                return False

            # 计算下单数量
            quantity = self.calculate_order_quantity(best_bid)

            # 下限价买单
            result = self.client.place_order(
                symbol=self.symbol,
                side="Bid",  # 买入
                order_type="Limit",
                quantity=quantity,
                price=best_bid
            )

            # 记录下单时间
            self.last_order_time = datetime.datetime.now()

            logger.info(f"下限价买单成功: {result}")
            return True

        except Exception as e:
            logger.error(f"下限价买单失败: {e}")
            return False

    def close_position_market(self, position: Dict) -> bool:
        """市价平仓"""
        try:
            quantity = float(position.get("netQuantity", 0))

            if quantity != 0:
                # 确定平仓方向
                side = "Ask" if quantity > 0 else "Bid"  # 多头平仓卖出，空头平仓买入
                abs_quantity = abs(quantity)

                # 获取数量精度并格式化，避免科学计数法
                precision = self.get_quantity_precision()
                formatted_quantity = f"{abs_quantity:.{precision}f}"

                logger.info(f"平仓数量: 原始={abs_quantity}, 格式化={formatted_quantity}")

                # 市价平仓，使用reduceOnly确保只平仓不开新仓
                result = self.client.place_order(
                    symbol=self.symbol,
                    side=side,
                    order_type="Market",
                    quantity=formatted_quantity,  # 直接传递字符串格式
                )

                logger.info(f"市价平仓成功: 方向={side}, 数量={formatted_quantity}, 结果={result}")
                return True

            logger.info("仓位数量为0，无需平仓")
            return False

        except Exception as e:
            logger.error(f"市价平仓失败: {e}")
            return False

    def cancel_old_orders(self, existing_orders: List[Dict] = None) -> bool:
        """取消旧的挂单"""
        try:
            cancel_errors = []
            
            # 如果传入了已有订单数据，直接使用，避免重复请求
            if existing_orders is not None:
                symbol_orders = existing_orders
            else:
                symbol_orders = self.get_open_orders()

            # 取消所有订单
            for order in symbol_orders:
                order_id = order.get("id") or order.get("orderId")
                if order_id:
                    try:
                        self.client.cancel_order(order_id, self.symbol)
                        logger.info(f"取消订单成功: {order_id}")
                    except Exception as e:
                        logger.error(f"取消订单{order_id}失败: {e}")
                        cancel_errors.append(order_id)

            # 如果有取消失败的订单，返回False
            if cancel_errors:
                logger.error(f"有{len(cancel_errors)}个订单取消失败，不允许下新订单")
                return False
                
            return len(symbol_orders) > 0

        except Exception as e:
            logger.error(f"获取订单信息失败: {e}")
            return False

    def execute_trading_logic(self):
        """执行交易逻辑"""
        try:
            logger.info(f"开始执行交易逻辑 - 代币: {self.symbol}, 杠杆: {self.leverage}, 交易额: {self.trade_amount}")

            # 检查是否存在仓位
            position = self.get_position()
            if position:
                logger.info("检测到仓位，执行市价平仓")
                self.close_position_market(position)
                return

            # 获取当前挂单
            open_orders = self.get_open_orders()
            if open_orders:
                # 如果是初次运行（没有记录下单时间），直接取消所有订单保证持仓干净
                if self.last_order_time is None:
                    logger.info("初次运行，取消所有现有订单保证持仓干净")
                    cancel_success = self.cancel_old_orders(open_orders)  # 传递已获取的订单数据
                    if not cancel_success:
                        logger.error("取消订单失败，跳过本轮交易")
                        return
                    self.place_limit_buy_order()
                # 检查订单是否超时（10秒）
                elif (datetime.datetime.now() - self.last_order_time).total_seconds() > 10:
                    # 获取当前买一价
                    best_bid = self.get_best_bid_price()
                    if best_bid:
                        # 检查是否有订单价格与买最高价相同
                        should_cancel = True
                        for order in open_orders:
                            order_price = float(order.get("price", 0))
                            if abs(order_price - best_bid) < 0.01:  # 价格相差小于0.01认为相同
                                logger.info(f"订单价格{order_price}与买最高价{best_bid}相同，不取消订单")
                                should_cancel = False
                                break

                        if should_cancel:
                            logger.info("订单超时10秒且价格不是买最高价，取消订单并重新下单")
                            cancel_success = self.cancel_old_orders(open_orders)  # 传递已获取的订单数据
                            if not cancel_success:
                                logger.error("取消订单失败，跳过本轮交易")
                                return
                            self.last_order_time = None
                            self.place_limit_buy_order()
                        else:
                            logger.info("订单价格为买最高价，继续等待成交")
                    else:
                        logger.error("无法获取买一价，跳过本轮交易")
                else:
                    logger.info("已存在挂单，等待成交")
            else:
                logger.info("无挂单，准备下限价买单")
                self.place_limit_buy_order()

        except Exception as e:
            logger.error(f"执行交易逻辑失败: {e}")
            logger.info("等待5秒后重试...")
            time.sleep(5)
