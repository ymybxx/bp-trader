import base64
import time
from typing import Dict, Optional, Any

import requests
from nacl.encoding import Base64Encoder
from nacl.signing import SigningKey

from config.config import BACKPACK_CONFIG
from utils.logger import setup_logger

logger = setup_logger(__name__)


class BackpackClient:
    def __init__(self, config=None):
        """
        初始化Backpack客户端
        Args:
            config: 可选的配置字典，如果不提供则使用默认的BACKPACK_CONFIG
        """
        if config is None:
            config = BACKPACK_CONFIG
            
        self.api_key = config["api_key"]
        self.private_key = config["private_key"]
        self.base_url = config["base_url"]

        if not self.api_key or not self.private_key:
            raise ValueError("BACKPACK_API_KEY和BACKPACK_PRIVATE_KEY必须设置")

        # 初始化签名密钥
        self.signing_key = SigningKey(self.private_key, encoder=Base64Encoder)

    def _generate_signature(self, method: str, endpoint: str, params: Optional[Dict] = None,
                            timestamp: int = None, window: int = 5000) -> Dict[str, str]:
        """生成API请求签名"""
        if timestamp is None:
            timestamp = int(time.time() * 1000)

        # 获取指令类型
        instruction = self._get_instruction_prefix(endpoint, method)

        # 构建签名字符串
        sign_parts = []

        # 添加指令
        if instruction:
            sign_parts.append(f"instruction={instruction}")

        # 添加参数(按字母顺序排序)
        if params:
            sorted_params = sorted(params.items())
            for key, value in sorted_params:
                sign_parts.append(f"{key}={value}")

        # 添加时间戳和窗口
        sign_parts.append(f"timestamp={timestamp}")
        sign_parts.append(f"window={window}")

        # 构建最终签名字符串
        message = "&".join(sign_parts)

        # 使用ED25519私钥签名
        signature = self.signing_key.sign(message.encode()).signature
        signature_b64 = base64.b64encode(signature).decode()

        return {
            "X-API-Key": self.api_key,
            "X-Timestamp": str(timestamp),
            "X-Window": str(window),
            "X-Signature": signature_b64
        }

    def _get_instruction_prefix(self, endpoint: str, method: str = "GET") -> str:
        """根据端点和HTTP方法获取指令前缀"""
        # 根据Backpack API文档，不同端点和方法有不同的指令前缀
        if endpoint == "/api/v1/order":
            if method.upper() == "POST":
                return "orderExecute"
            elif method.upper() == "DELETE":
                return "orderCancel"
        elif endpoint == "/api/v1/orders":
            if method.upper() == "GET":
                return "orderQueryAll"
            elif method.upper() == "DELETE":
                return "orderCancelAll"
        elif endpoint == "/api/v1/account":
            if method.upper() == "GET":
                return "accountQuery"
            elif method.upper() == "PATCH":
                return "accountUpdate"

        # 默认映射
        instruction_map = {
            "/api/v1/order/history": "orderHistoryQuery",
            "/api/v1/fills": "fillHistoryQuery",
            "/api/v1/position": "positionQuery",
            "/api/v1/capital": "balanceQuery",
            "/api/v1/markets": "",  # 公开端点无需前缀
            "/api/v1/ticker": "",  # 公开端点无需前缀
            "/api/v1/depth": "",  # 公开端点无需前缀
        }
        return instruction_map.get(endpoint, "")

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                      auth: bool = True) -> Dict[str, Any]:
        """发送API请求"""
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}

        if auth:
            auth_headers = self._generate_signature(method, endpoint, params)
            headers.update(auth_headers)

        try:
            if method.upper() == "GET":
                # GET请求时，参数会被添加到URL中，但签名时已经包含了这些参数
                response = requests.get(url, params=params, headers=headers)
            elif method.upper() == "POST":
                response = requests.post(url, json=params, headers=headers)
            elif method.upper() == "DELETE":
                response = requests.delete(url, json=params, headers=headers)
            elif method.upper() == "PATCH":
                response = requests.patch(url, json=params, headers=headers)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"API请求失败: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"响应状态码: {e.response.status_code}")
                logger.error(f"响应内容: {e.response.text}")
            raise

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """获取ticker信息"""
        endpoint = "/api/v1/ticker"
        params = {"symbol": f"{symbol}_USDC_PERP"}
        return self._make_request("GET", endpoint, params, auth=False)

    def get_depth(self, symbol: str) -> Dict[str, Any]:
        """获取深度信息"""
        endpoint = "/api/v1/depth"
        params = {"symbol": f"{symbol}_USDC_PERP"}
        return self._make_request("GET", endpoint, params, auth=False)

    def get_positions(self) -> Dict[str, Any]:
        """获取当前持仓"""
        endpoint = "/api/v1/position"
        return self._make_request("GET", endpoint, auth=True)

    def get_open_orders(self, symbol: str = None) -> Dict[str, Any]:
        """获取当前挂单"""
        endpoint = "/api/v1/orders"
        params = {}
        if symbol:
            params["symbol"] = f"{symbol}_USDC_PERP"
        return self._make_request("GET", endpoint, params, auth=True)

    def place_order(self, symbol: str, side: str, order_type: str,
                    quantity, price: float = None, time_in_force: str = "GTC",
                    reduce_only: bool = False) -> Dict[str, Any]:
        """下单"""
        endpoint = "/api/v1/order"

        # 确保quantity是正确的字符串格式，避免科学计数法
        if isinstance(quantity, (int, float)):
            quantity_str = f"{float(quantity):f}".rstrip('0').rstrip('.')
        else:
            quantity_str = str(quantity)

        params = {
            "symbol": f"{symbol}_USDC_PERP",
            "side": side,  # "Bid" 或 "Ask"
            "orderType": order_type,  # "Limit" 或 "Market"
            "quantity": quantity_str,
            "timeInForce": time_in_force
        }

        if price and order_type == "Limit":
            params["price"] = str(price)

        if reduce_only:
            params["reduceOnly"] = True

        return self._make_request("POST", endpoint, params, auth=True)

    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """取消订单"""
        endpoint = "/api/v1/order"
        params = {
            "orderId": order_id,
            "symbol": f"{symbol}_USDC_PERP"
        }
        return self._make_request("DELETE", endpoint, params, auth=True)

    def get_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        endpoint = "/api/v1/capital"
        return self._make_request("GET", endpoint, auth=True)

    def get_markets(self) -> Dict[str, Any]:
        """获取可用市场列表"""
        endpoint = "/api/v1/markets"
        return self._make_request("GET", endpoint, auth=False)

    def get_account(self) -> Dict[str, Any]:
        """获取账户信息"""
        endpoint = "/api/v1/account"
        return self._make_request("GET", endpoint, auth=True)

    def update_account_leverage(self, leverage_limit: float) -> Dict[str, Any]:
        """更新账户杠杆限制"""
        endpoint = "/api/v1/account"
        params = {
            "leverageLimit": str(leverage_limit)
        }
        return self._make_request("PATCH", endpoint, params, auth=True)
