import datetime
import time
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, Tuple

from config.config import TRADING_CONFIG, BACKPACK_CONFIG, BACKPACK_CONFIG_2
from service.backpack_client import BackpackClient
from utils.logger import setup_logger

logger = setup_logger(__name__)


class HedgePhase(Enum):
    """对冲策略阶段"""
    OPENING = "opening"  # 开仓阶段
    WAITING = "waiting"  # 等待阶段
    CLOSING = "closing"  # 平仓阶段
    COMPLETED = "completed"  # 完成阶段


class DualHedgeService:
    def __init__(self):
        # 初始化两个账户的客户端
        self.client1 = BackpackClient(BACKPACK_CONFIG)  # 账户1：做多（买单）
        self.client2 = BackpackClient(BACKPACK_CONFIG_2)  # 账户2：做空（卖单）

        # 交易配置
        self.symbol = TRADING_CONFIG["symbol"]
        self.leverage = TRADING_CONFIG["leverage"]
        self.trade_amount = TRADING_CONFIG["trade_amount"]
        self.close_delay = TRADING_CONFIG["hedge_close_delay"]
        self.trading_symbol = f"{self.symbol}_USDC_PERP"

        # 状态管理
        self.phase = HedgePhase.OPENING
        self.phase_start_time = None
        self.quantity_precision = None

        # 订单跟踪
        self.account1_order_id = None  # 账户1当前订单ID
        self.account2_order_id = None  # 账户2当前订单ID

        # 仓位跟踪
        self.account1_position = 0.0  # 账户1仓位
        self.account2_position = 0.0  # 账户2仓位

        # 杠杆检查状态
        self.leverage_checked = False

        # 初始清理状态
        self.initial_cleanup_done = False

    def get_quantity_precision(self) -> int:
        """获取数量精度"""
        if self.quantity_precision is not None:
            return self.quantity_precision

        try:
            markets = self.client1.get_markets()
            for market in markets:
                if market.get("symbol") == self.trading_symbol:
                    step_size = market.get("filters", {}).get("quantity", {}).get("stepSize")
                    if step_size:
                        step_decimal = Decimal(step_size)
                        precision = len(str(step_decimal).rstrip('0').split('.')[-1])
                        self.quantity_precision = precision
                        logger.info(f"{self.symbol}数量精度: {precision}位小数, stepSize: {step_size}")
                        return precision

            logger.warning(f"未找到{self.symbol}的精度信息，使用默认6位小数")
            self.quantity_precision = 6
            return 6

        except Exception as e:
            logger.error(f"获取数量精度失败: {e}")
            return None

    def check_and_set_leverage(self) -> bool:
        """检查并设置两个账户的杠杆"""
        if self.leverage_checked:
            return True

        try:
            # 检查账户1杠杆
            account1_info = self.client1.get_account()
            current_leverage1 = float(account1_info.get("leverageLimit", 0))

            if current_leverage1 != self.leverage:
                logger.info(f"更新账户1杠杆从 {current_leverage1} 到 {self.leverage}")
                self.client1.update_account_leverage(self.leverage)

            # 检查账户2杠杆
            account2_info = self.client2.get_account()
            current_leverage2 = float(account2_info.get("leverageLimit", 0))

            if current_leverage2 != self.leverage:
                logger.info(f"更新账户2杠杆从 {current_leverage2} 到 {self.leverage}")
                self.client2.update_account_leverage(self.leverage)

            logger.info("两个账户杠杆设置完成")
            self.leverage_checked = True
            return True

        except Exception as e:
            logger.error(f"检查/设置杠杆失败: {e}")
            return False

    def get_best_prices(self) -> Tuple[Optional[float], Optional[float]]:
        """获取最高买价和最低卖价
        Raises:
            Exception: 如果API调用失败
        """
        depth = self.client1.get_depth(self.symbol)
        bids = depth.get("bids", [])
        asks = depth.get("asks", [])

        best_bid = None
        best_ask = None

        if bids:
            best_bid = float(bids[-1][0])  # 最后一个是最高买价

        if asks:
            best_ask = float(asks[0][0])  # 第一个是最低卖价

        logger.info(f"{self.symbol} 最高买价: {best_bid}, 最低卖价: {best_ask}")
        return best_bid, best_ask

    def calculate_order_quantity(self, price: float) -> float:
        """计算下单数量"""
        quantity = self.trade_amount / price
        precision = self.get_quantity_precision()
        if precision is None:
            logger.error("无法获取数量精度，无法计算订单数量")
            return None
        quantity = round(quantity, precision)

        logger.info(f"计算订单数量: 交易额={self.trade_amount}, 价格={price}, 数量={quantity}")
        return quantity

    def get_positions(self) -> Tuple[float, float]:
        """获取两个账户的仓位
        Raises:
            Exception: 如果API调用失败
        """
        # 获取账户1仓位
        positions1 = self.client1.get_positions()
        account1_pos = 0.0
        if isinstance(positions1, list):
            for position in positions1:
                if position.get("symbol") == self.trading_symbol:
                    account1_pos = float(position.get("netQuantity", 0))
                    break

        # 获取账户2仓位
        positions2 = self.client2.get_positions()
        account2_pos = 0.0
        if isinstance(positions2, list):
            for position in positions2:
                if position.get("symbol") == self.trading_symbol:
                    account2_pos = float(position.get("netQuantity", 0))
                    break

        self.account1_position = account1_pos
        self.account2_position = account2_pos

        logger.info(f"账户仓位 - 账户1: {account1_pos}, 账户2: {account2_pos}")
        return account1_pos, account2_pos

    def get_order_status(self, client: BackpackClient, order_id: str) -> Optional[Dict]:
        """获取订单状态
        Returns:
            - Dict: 如果订单仍在挂单列表中
            - None: 如果订单不在挂单列表中（已成交或已取消）
        Raises:
            Exception: 如果API调用失败
        """
        orders = client.get_open_orders(self.symbol)
        if isinstance(orders, list):
            for order in orders:
                if order.get("id") == order_id or order.get("orderId") == order_id:
                    return order
        elif isinstance(orders, dict):
            open_orders = orders.get("orders", [])
            for order in open_orders:
                if order.get("id") == order_id or order.get("orderId") == order_id:
                    return order
        return None

    def cancel_order_by_id(self, client: BackpackClient, order_id: str, account_name: str) -> bool:
        """取消指定订单"""
        try:
            if order_id:
                client.cancel_order(order_id, self.symbol)
                logger.info(f"取消{account_name}订单成功: {order_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"取消{account_name}订单{order_id}失败: {e}")
            return False

    def cancel_all_orders(self) -> bool:
        """取消两个账户的所有订单"""
        try:
            success = True

            # 取消账户1的订单
            try:
                orders1 = self.client1.get_open_orders(self.symbol)
                if isinstance(orders1, list):
                    symbol_orders1 = [order for order in orders1 if order.get("symbol") == self.trading_symbol]
                else:
                    symbol_orders1 = [order for order in orders1.get("orders", []) if
                                      order.get("symbol") == self.trading_symbol]

                for order in symbol_orders1:
                    order_id = order.get("id") or order.get("orderId")
                    if not self.cancel_order_by_id(self.client1, order_id, "账户1"):
                        success = False
            except Exception as e:
                logger.error(f"获取账户1订单信息失败: {e}")
                success = False

            # 取消账户2的订单
            try:
                orders2 = self.client2.get_open_orders(self.symbol)
                if isinstance(orders2, list):
                    symbol_orders2 = [order for order in orders2 if order.get("symbol") == self.trading_symbol]
                else:
                    symbol_orders2 = [order for order in orders2.get("orders", []) if
                                      order.get("symbol") == self.trading_symbol]

                for order in symbol_orders2:
                    order_id = order.get("id") or order.get("orderId")
                    if not self.cancel_order_by_id(self.client2, order_id, "账户2"):
                        success = False
            except Exception as e:
                logger.error(f"获取账户2订单信息失败: {e}")
                success = False

            return success

        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            return False

    def close_existing_positions(self) -> bool:
        """清理两个账户的现有仓位"""
        try:
            try:
                pos1, pos2 = self.get_positions()
            except Exception as e:
                logger.error(f"获取仓位信息失败，无法清理仓位: {e}")
                return False

            closed_any = False

            # 平仓账户1
            if abs(pos1) > 0:
                side = "Ask" if pos1 > 0 else "Bid"  # 多头平仓卖出，空头平仓买入
                precision = self.get_quantity_precision()
                if precision is None:
                    logger.error("无法获取数量精度，无法进行市价平仓")
                    return False
                quantity_str = f"{abs(pos1):.{precision}f}"

                result1 = self.client1.place_order(
                    symbol=self.symbol,
                    side=side,
                    order_type="Market",
                    quantity=quantity_str
                )
                logger.info(f"账户1市价平仓成功: 方向={side}, 数量={quantity_str}, 结果={result1}")
                closed_any = True

            # 平仓账户2
            if abs(pos2) > 0:
                side = "Bid" if pos2 < 0 else "Ask"  # 空头平仓买入，多头平仓卖出
                precision = self.get_quantity_precision()
                if precision is None:
                    logger.error("无法获取数量精度，无法进行市价平仓")
                    return False
                quantity_str = f"{abs(pos2):.{precision}f}"

                result2 = self.client2.place_order(
                    symbol=self.symbol,
                    side=side,
                    order_type="Market",
                    quantity=quantity_str
                )
                logger.info(f"账户2市价平仓成功: 方向={side}, 数量={quantity_str}, 结果={result2}")
                closed_any = True

            if closed_any:
                logger.info("现有仓位清理完成")
            else:
                logger.info("无现有仓位需要清理")

            return True

        except Exception as e:
            logger.error(f"清理现有仓位失败: {e}")
            return False

    def initial_cleanup(self) -> bool:
        """初始清理：取消所有订单并平仓所有仓位"""
        try:
            logger.info("开始初始清理：取消订单和平仓")

            # 1. 取消所有订单
            if not self.cancel_all_orders():
                logger.warning("取消订单时有部分失败，继续执行")

            # 等待订单取消完成
            time.sleep(2)

            # 2. 平仓所有现有仓位
            if not self.close_existing_positions():
                logger.error("平仓失败")
                return False

            # 等待平仓完成
            time.sleep(2)

            # 3. 验证清理结果
            try:
                pos1, pos2 = self.get_positions()
                if abs(pos1) > 0.0001 or abs(pos2) > 0.0001:  # 允许微小的精度误差
                    logger.warning(f"清理后仍有仓位: 账户1={pos1}, 账户2={pos2}")
                else:
                    logger.info("初始清理完成，账户状态干净")
            except Exception as e:
                logger.error(f"无法验证清理结果: {e}")
                return False

            self.initial_cleanup_done = True
            return True

        except Exception as e:
            logger.error(f"初始清理失败: {e}")
            return False

    def place_opening_orders(self) -> bool:
        """下开仓订单：账户1买单，账户2卖单"""
        try:
            try:
                best_bid, best_ask = self.get_best_prices()
            except Exception as e:
                logger.error(f"获取价格信息失败: {e}")
                return False

            if not best_bid or not best_ask:
                logger.error("无法获取有效价格信息")
                return False

            # 计算订单数量
            buy_quantity = self.calculate_order_quantity(best_bid)
            sell_quantity = self.calculate_order_quantity(best_ask)

            if buy_quantity is None or sell_quantity is None:
                logger.error("无法计算订单数量，跳过下单")
                return False

            # 账户1下买单（最高买价）
            result1 = self.client1.place_order(
                symbol=self.symbol,
                side="Bid",
                order_type="Limit",
                quantity=buy_quantity,
                price=best_bid
            )
            self.account1_order_id = result1.get("orderId") or result1.get("id")
            logger.info(f"账户1下买单成功: {result1}")

            # 账户2下卖单（最低卖价）
            result2 = self.client2.place_order(
                symbol=self.symbol,
                side="Ask",
                order_type="Limit",
                quantity=sell_quantity,
                price=best_ask
            )
            self.account2_order_id = result2.get("orderId") or result2.get("id")
            logger.info(f"账户2下卖单成功: {result2}")

            return True

        except Exception as e:
            logger.error(f"下开仓订单失败: {e}")
            return False

    def place_closing_orders(self) -> bool:
        """下平仓订单"""
        try:
            try:
                best_bid, best_ask = self.get_best_prices()
            except Exception as e:
                logger.error(f"获取价格信息失败: {e}")
                return False

            if not best_bid or not best_ask:
                logger.error("无法获取有效价格信息")
                return False

            try:
                pos1, pos2 = self.get_positions()
            except Exception as e:
                logger.error(f"获取仓位信息失败: {e}")
                return False

            # 账户1平仓（如果有多头仓位则卖出）
            if pos1 > 0:
                precision = self.get_quantity_precision()
                if precision is None:
                    logger.error("无法获取数量精度，无法下平仓订单")
                    return False
                quantity_str = f"{abs(pos1):.{precision}f}"
                result1 = self.client1.place_order(
                    symbol=self.symbol,
                    side="Ask",
                    order_type="Limit",
                    quantity=quantity_str,
                    price=best_ask
                )
                self.account1_order_id = result1.get("orderId") or result1.get("id")
                logger.info(f"账户1下平仓卖单成功: {result1}")

            # 账户2平仓（如果有空头仓位则买入）
            if pos2 < 0:
                precision = self.get_quantity_precision()
                if precision is None:
                    logger.error("无法获取数量精度，无法下平仓订单")
                    return False
                quantity_str = f"{abs(pos2):.{precision}f}"
                result2 = self.client2.place_order(
                    symbol=self.symbol,
                    side="Bid",
                    order_type="Limit",
                    quantity=quantity_str,
                    price=best_bid
                )
                self.account2_order_id = result2.get("orderId") or result2.get("id")
                logger.info(f"账户2下平仓买单成功: {result2}")

            return True

        except Exception as e:
            logger.error(f"下平仓订单失败: {e}")
            return False

    def market_hedge(self, account_to_hedge: int) -> bool:
        """市价对冲指定账户"""
        try:
            try:
                pos1, pos2 = self.get_positions()
            except Exception as e:
                logger.error(f"获取仓位信息失败，无法执行对冲: {e}")
                return False

            logger.info(f"开始对冲账户{account_to_hedge}，当前仓位: 账户1={pos1}, 账户2={pos2}")

            if account_to_hedge == 1:
                # 对冲账户1：目标是让账户2的仓位 = -账户1的仓位
                target_pos2 = -pos1  # 账户2的目标仓位
                hedge_quantity = target_pos2 - pos2  # 需要对冲的数量

                logger.info(f"账户2目标仓位: {target_pos2}, 当前仓位: {pos2}, 需要对冲数量: {hedge_quantity}")

                if abs(hedge_quantity) > 0.00001:  # 避免精度误差的小数量交易
                    side = "Ask" if hedge_quantity < 0 else "Bid"
                    precision = self.get_quantity_precision()
                    if precision is None:
                        logger.error("无法获取数量精度，无法进行市价对冲")
                        return False
                    quantity_str = f"{abs(hedge_quantity):.{precision}f}"

                    result = self.client2.place_order(
                        symbol=self.symbol,
                        side=side,
                        order_type="Market",
                        quantity=quantity_str
                    )
                    logger.info(f"账户2市价对冲成功: 方向={side}, 数量={quantity_str}, 结果={result}")
                    return True
                else:
                    logger.info("对冲数量过小，无需对冲")
                    return True

            elif account_to_hedge == 2:
                # 对冲账户2：目标是让账户1的仓位 = -账户2的仓位
                target_pos1 = -pos2  # 账户1的目标仓位
                hedge_quantity = target_pos1 - pos1  # 需要对冲的数量

                logger.info(f"账户1目标仓位: {target_pos1}, 当前仓位: {pos1}, 需要对冲数量: {hedge_quantity}")

                if abs(hedge_quantity) > 0.00001:  # 避免精度误差的小数量交易
                    side = "Ask" if hedge_quantity < 0 else "Bid"
                    precision = self.get_quantity_precision()
                    if precision is None:
                        logger.error("无法获取数量精度，无法进行市价对冲")
                        return False
                    quantity_str = f"{abs(hedge_quantity):.{precision}f}"

                    result = self.client1.place_order(
                        symbol=self.symbol,
                        side=side,
                        order_type="Market",
                        quantity=quantity_str
                    )
                    logger.info(f"账户1市价对冲成功: 方向={side}, 数量={quantity_str}, 结果={result}")
                    return True
                else:
                    logger.info("对冲数量过小，无需对冲")
                    return True

            return False

        except Exception as e:
            logger.error(f"市价对冲失败: {e}")
            return False

    def check_opening_phase(self) -> bool:
        """检查开仓阶段状态"""
        try:
            # 检查订单状态
            order1_status = None
            order2_status = None

            if self.account1_order_id:
                try:
                    order1_status = self.get_order_status(self.client1, self.account1_order_id)
                except Exception as e:
                    logger.error(f"获取账户1订单状态失败: {e}")
                    return False  # API错误，无法确定状态，跳过本轮检查

            if self.account2_order_id:
                try:
                    order2_status = self.get_order_status(self.client2, self.account2_order_id)
                except Exception as e:
                    logger.error(f"获取账户2订单状态失败: {e}")
                    return False  # API错误，无法确定状态，跳过本轮检查

            # 检查是否有订单完全成交（不存在于挂单列表中）
            # 注意：订单不在挂单列表中可能是成交或被取消，需要结合上下文判断
            order1_filled = order1_status is None and self.account1_order_id is not None
            order2_filled = order2_status is None and self.account2_order_id is not None

            if order1_filled and not order2_filled:
                # 账户1订单成交，立即取消账户2订单并进行市价对冲
                logger.info("账户1订单完全成交，立即取消账户2订单并进行市价对冲")
                self.cancel_order_by_id(self.client2, self.account2_order_id, "账户2")

                # 等待取消完成，然后检查实际仓位来决定对冲
                time.sleep(1)

                try:
                    pos1, pos2 = self.get_positions()
                    logger.info(f"取消订单后实际仓位: 账户1={pos1}, 账户2={pos2}")

                    # 计算需要对冲的数量（基于实际仓位）
                    target_pos2 = -pos1  # 账户2的目标仓位
                    hedge_quantity = target_pos2 - pos2  # 需要对冲的数量

                    if abs(hedge_quantity) > 0.00001:  # 需要对冲
                        side = "Ask" if hedge_quantity < 0 else "Bid"
                        precision = self.get_quantity_precision()
                        if precision is None:
                            logger.error("无法获取数量精度，无法进行市价对冲")
                            self.account2_order_id = None
                            return False
                        quantity_str = f"{abs(hedge_quantity):.{precision}f}"

                        result = self.client2.place_order(
                            symbol=self.symbol,
                            side=side,
                            order_type="Market",
                            quantity=quantity_str
                        )
                        logger.info(f"账户2市价对冲成功: 方向={side}, 数量={quantity_str}, 结果={result}")
                        self.phase = HedgePhase.WAITING
                        self.phase_start_time = datetime.datetime.now()
                        return True
                    else:
                        logger.info("基于实际仓位计算，无需对冲")
                        self.phase = HedgePhase.WAITING
                        self.phase_start_time = datetime.datetime.now()
                        return True

                except Exception as e:
                    logger.error(f"获取仓位信息或执行对冲失败: {e}")
                    # 市价对冲失败，保持账户1订单已成交状态，下轮继续重试对冲
                    logger.error("市价对冲失败，保持状态继续重试对冲")
                    # 不清理account1_order_id，因为账户1订单已成交
                    # 清理account2_order_id，因为已取消
                    self.account2_order_id = None
                    return False

            elif order2_filled and not order1_filled:
                # 账户2订单成交，立即取消账户1订单并进行市价对冲
                logger.info("账户2订单完全成交，立即取消账户1订单并进行市价对冲")
                self.cancel_order_by_id(self.client1, self.account1_order_id, "账户1")

                # 等待取消完成，然后检查实际仓位来决定对冲
                time.sleep(1)

                try:
                    pos1, pos2 = self.get_positions()
                    logger.info(f"取消订单后实际仓位: 账户1={pos1}, 账户2={pos2}")

                    # 计算需要对冲的数量（基于实际仓位）
                    target_pos1 = -pos2  # 账户1的目标仓位
                    hedge_quantity = target_pos1 - pos1  # 需要对冲的数量

                    if abs(hedge_quantity) > 0.00001:  # 需要对冲
                        side = "Ask" if hedge_quantity < 0 else "Bid"
                        precision = self.get_quantity_precision()
                        if precision is None:
                            logger.error("无法获取数量精度，无法进行市价对冲")
                            self.account1_order_id = None
                            return False
                        quantity_str = f"{abs(hedge_quantity):.{precision}f}"

                        result = self.client1.place_order(
                            symbol=self.symbol,
                            side=side,
                            order_type="Market",
                            quantity=quantity_str
                        )
                        logger.info(f"账户1市价对冲成功: 方向={side}, 数量={quantity_str}, 结果={result}")
                        self.phase = HedgePhase.WAITING
                        self.phase_start_time = datetime.datetime.now()
                        return True
                    else:
                        logger.info("基于实际仓位计算，无需对冲")
                        self.phase = HedgePhase.WAITING
                        self.phase_start_time = datetime.datetime.now()
                        return True

                except Exception as e:
                    logger.error(f"获取仓位信息或执行对冲失败: {e}")
                    # 市价对冲失败，保持账户2订单已成交状态，下轮继续重试对冲
                    logger.error("市价对冲失败，保持状态继续重试对冲")
                    # 不清理account2_order_id，因为账户2订单已成交
                    # 清理account1_order_id，因为已取消
                    self.account1_order_id = None
                    return False

            elif order1_filled and order2_filled:
                # 两个订单都不在挂单列表中 - 可能都成交或部分被取消
                # 需要检查仓位状态确定是否真的都成交了
                try:
                    pos1, pos2 = self.get_positions()
                    # 如果两个账户都有仓位，说明订单真的都成交了
                    if abs(pos1) > 0 and abs(pos2) > 0:
                        logger.info("两个账户订单都已成交，无需对冲，直接进入等待阶段")
                        self.phase = HedgePhase.WAITING
                        self.phase_start_time = datetime.datetime.now()
                        return True
                    else:
                        # 仓位状态不一致，可能有订单被取消了，重新开始
                        logger.warning(f"订单状态异常，仓位: 账户1={pos1}, 账户2={pos2}，重置状态")
                        self.account1_order_id = None
                        self.account2_order_id = None
                        return False
                except Exception as e:
                    logger.error(f"检查仓位状态失败: {e}")
                    return False

            return False

        except Exception as e:
            logger.error(f"检查开仓阶段失败: {e}")
            return False

    def check_closing_phase(self) -> bool:
        """检查平仓阶段状态"""
        try:
            # 检查订单状态
            order1_status = None
            order2_status = None

            if self.account1_order_id:
                try:
                    order1_status = self.get_order_status(self.client1, self.account1_order_id)
                except Exception as e:
                    logger.error(f"获取账户1订单状态失败: {e}")
                    return False  # API错误，无法确定状态，跳过本轮检查

            if self.account2_order_id:
                try:
                    order2_status = self.get_order_status(self.client2, self.account2_order_id)
                except Exception as e:
                    logger.error(f"获取账户2订单状态失败: {e}")
                    return False  # API错误，无法确定状态，跳过本轮检查

            # 检查是否有订单完全成交
            order1_filled = order1_status is None and self.account1_order_id is not None
            order2_filled = order2_status is None and self.account2_order_id is not None

            if order1_filled and not order2_filled:
                # 账户1平仓单成交，取消账户2订单并市价平仓
                logger.info("账户1平仓单完全成交，取消账户2订单并进行市价平仓")
                self.cancel_order_by_id(self.client2, self.account2_order_id, "账户2")

                try:
                    pos1, pos2 = self.get_positions()
                except Exception as e:
                    logger.error(f"获取仓位信息失败: {e}")
                    # 获取仓位失败，保持状态等待重试市价平仓
                    # 不清理account1_order_id，因为账户1订单已成交
                    # 已取消account2_order_id，所以清理它
                    self.account2_order_id = None
                    return False

                if abs(pos2) > 0:
                    try:
                        side = "Bid" if pos2 < 0 else "Ask"
                        precision = self.get_quantity_precision()
                        if precision is None:
                            logger.error("无法获取数量精度，无法进行市价平仓")
                            return False
                        quantity_str = f"{abs(pos2):.{precision}f}"

                        self.client2.place_order(
                            symbol=self.symbol,
                            side=side,
                            order_type="Market",
                            quantity=quantity_str
                        )
                        logger.info("账户2市价平仓完成")
                    except Exception as e:
                        logger.error(f"账户2市价平仓失败: {e}")
                        # 市价平仓失败，保持状态等待重试市价平仓
                        # 不清理account1_order_id，因为账户1订单已成交
                        # account2_order_id已清理（已取消）
                        return False

                self.phase = HedgePhase.COMPLETED
                return True

            elif order2_filled and not order1_filled:
                # 账户2平仓单成交，取消账户1订单并市价平仓
                logger.info("账户2平仓单完全成交，取消账户1订单并进行市价平仓")
                self.cancel_order_by_id(self.client1, self.account1_order_id, "账户1")

                try:
                    pos1, pos2 = self.get_positions()
                except Exception as e:
                    logger.error(f"获取仓位信息失败: {e}")
                    # 获取仓位失败，保持状态等待重试市价平仓
                    # 已取消account1_order_id，所以清理它
                    # 不清理account2_order_id，因为账户2订单已成交
                    self.account1_order_id = None
                    return False

                if abs(pos1) > 0:
                    try:
                        side = "Ask" if pos1 > 0 else "Bid"
                        precision = self.get_quantity_precision()
                        if precision is None:
                            logger.error("无法获取数量精度，无法进行市价平仓")
                            return False
                        quantity_str = f"{abs(pos1):.{precision}f}"

                        self.client1.place_order(
                            symbol=self.symbol,
                            side=side,
                            order_type="Market",
                            quantity=quantity_str
                        )
                        logger.info("账户1市价平仓完成")
                    except Exception as e:
                        logger.error(f"账户1市价平仓失败: {e}")
                        # 市价平仓失败，保持状态等待重试市价平仓
                        # account1_order_id已清理（已取消）
                        # 不清理account2_order_id，因为账户2订单已成交
                        return False

                self.phase = HedgePhase.COMPLETED
                return True

            elif order1_filled and order2_filled:
                # 两个平仓单都成交了
                logger.info("两个账户平仓单都已成交，策略完成")
                self.phase = HedgePhase.COMPLETED
                return True

            return False

        except Exception as e:
            logger.error(f"检查平仓阶段失败: {e}")
            return False

    def reset_strategy(self):
        """重置策略状态"""
        self.phase = HedgePhase.OPENING
        self.phase_start_time = None
        self.account1_order_id = None
        self.account2_order_id = None
        self.account1_position = 0.0
        self.account2_position = 0.0
        logger.info("策略状态已重置")

    def execute_hedge_logic(self):
        """执行对冲策略逻辑"""
        try:
            logger.info(f"执行对冲策略 - 阶段: {self.phase.value}, 代币: {self.symbol}")

            # 检查并设置杠杆
            if not self.check_and_set_leverage():
                logger.error("杠杆设置失败，跳过本轮交易")
                return

            # 初始清理（只在第一次执行时进行）
            if not self.initial_cleanup_done:
                if not self.initial_cleanup():
                    logger.error("初始清理失败，跳过本轮交易")
                    return

            if self.phase == HedgePhase.OPENING:
                # 开仓阶段：检查是否已有订单，没有则下单
                if not self.account1_order_id and not self.account2_order_id:
                    # 清理现有订单
                    self.cancel_all_orders()
                    time.sleep(1)  # 等待订单取消

                    # 下开仓订单
                    if self.place_opening_orders():
                        logger.info("开仓订单已下达")
                    else:
                        logger.error("开仓订单下达失败")
                        return
                elif self.account1_order_id and not self.account2_order_id:
                    # 账户1订单已成交，账户2订单已取消，需要重试对冲
                    logger.info("检测到账户1订单已成交，账户2订单已取消，重试对冲")
                    if self.market_hedge(1):
                        self.phase = HedgePhase.WAITING
                        self.phase_start_time = datetime.datetime.now()
                        return
                    else:
                        logger.error("重试对冲失败，继续等待")
                elif not self.account1_order_id and self.account2_order_id:
                    # 账户2订单已成交，账户1订单已取消，需要重试对冲
                    logger.info("检测到账户2订单已成交，账户1订单已取消，重试对冲")
                    if self.market_hedge(2):
                        self.phase = HedgePhase.WAITING
                        self.phase_start_time = datetime.datetime.now()
                        return
                    else:
                        logger.error("重试对冲失败，继续等待")

                # 检查开仓状态
                self.check_opening_phase()

            elif self.phase == HedgePhase.WAITING:
                # 等待阶段：检查是否到了平仓时间
                if self.phase_start_time:
                    elapsed = (datetime.datetime.now() - self.phase_start_time).total_seconds()
                    if elapsed >= self.close_delay:
                        logger.info(f"等待{self.close_delay}秒完成，开始平仓")
                        self.phase = HedgePhase.CLOSING
                        self.account1_order_id = None
                        self.account2_order_id = None
                    else:
                        logger.info(f"等待平仓中，剩余时间: {self.close_delay - elapsed:.1f}秒")

            elif self.phase == HedgePhase.CLOSING:
                # 平仓阶段：检查是否已有平仓订单，没有则下单
                if not self.account1_order_id and not self.account2_order_id:
                    # 下平仓订单
                    if self.place_closing_orders():
                        logger.info("平仓订单已下达")
                    else:
                        logger.error("平仓订单下达失败")
                        return
                elif self.account1_order_id and not self.account2_order_id:
                    # 账户1订单已成交，账户2订单已取消，需要重试市价平仓
                    logger.info("检测到账户1平仓单已成交，账户2订单已取消，重试市价平仓")
                    try:
                        pos1, pos2 = self.get_positions()
                        if abs(pos2) > 0:
                            side = "Bid" if pos2 < 0 else "Ask"
                            precision = self.get_quantity_precision()
                            if precision is None:
                                logger.error("无法获取数量精度，无法进行市价平仓")
                                return
                            quantity_str = f"{abs(pos2):.{precision}f}"

                            self.client2.place_order(
                                symbol=self.symbol,
                                side=side,
                                order_type="Market",
                                quantity=quantity_str
                            )
                            logger.info("账户2市价平仓重试成功")
                            self.phase = HedgePhase.COMPLETED
                        else:
                            logger.info("账户2已无仓位，策略完成")
                            self.phase = HedgePhase.COMPLETED
                    except Exception as e:
                        logger.error(f"重试市价平仓失败: {e}")
                elif not self.account1_order_id and self.account2_order_id:
                    # 账户2订单已成交，账户1订单已取消，需要重试市价平仓
                    logger.info("检测到账户2平仓单已成交，账户1订单已取消，重试市价平仓")
                    try:
                        pos1, pos2 = self.get_positions()
                        if abs(pos1) > 0:
                            side = "Ask" if pos1 > 0 else "Bid"
                            precision = self.get_quantity_precision()
                            if precision is None:
                                logger.error("无法获取数量精度，无法进行市价平仓")
                                return
                            quantity_str = f"{abs(pos1):.{precision}f}"

                            self.client1.place_order(
                                symbol=self.symbol,
                                side=side,
                                order_type="Market",
                                quantity=quantity_str
                            )
                            logger.info("账户1市价平仓重试成功")
                            self.phase = HedgePhase.COMPLETED
                        else:
                            logger.info("账户1已无仓位，策略完成")
                            self.phase = HedgePhase.COMPLETED
                    except Exception as e:
                        logger.error(f"重试市价平仓失败: {e}")

                # 检查平仓状态
                self.check_closing_phase()

            elif self.phase == HedgePhase.COMPLETED:
                # 完成阶段：重置策略开始新一轮
                logger.info("本轮对冲策略完成，重置状态")
                self.reset_strategy()

        except Exception as e:
            logger.error(f"执行对冲策略失败: {e}")
            time.sleep(5)
