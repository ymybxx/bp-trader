#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(__file__))

from service.backpack_client import BackpackClient

def debug_account():
    client = BackpackClient()
    try:
        print("=== 账户余额 ===")
        balance = client.get_balance()
        print(balance)
        
        print("\n=== 持仓信息 ===")
        positions = client.get_positions()
        print(f"持仓类型: {type(positions)}")
        print(f"持仓内容: {positions}")
        
        print("\n=== 挂单信息 ===")
        orders = client.get_open_orders("SOL")
        print(f"订单类型: {type(orders)}")
        print(f"订单内容: {orders}")
        
    except Exception as e:
        print(f"获取账户信息失败: {e}")

if __name__ == "__main__":
    debug_account()