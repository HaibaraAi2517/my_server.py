from fastmcp import FastMCP
from tools import check_ticket, book_ticket
from typing import  Dict, Any

# 初始化 MCP 实例
mcp = FastMCP("RailwayTicketSystem")


@mcp.tool()
def check_ticket_tool(start_station: str, end_station: str) -> Dict[str, Any]:
    """
    查询两个城市之间的火车票余量，并返回标准化结果。

    Args:
        start_station (str): 出发城市，例如 "北京"
        end_station (str): 到达城市，例如 "上海"

    Returns:
        dict: 返回标准化查询结果
            - status: "success" 或 "fail"
            - message: 信息描述
            - remaining: 剩余票数，如果查询失败为 None

    Example:
        check_ticket_tool("北京", "上海") ->
        {"status": "success", "message": "查询成功", "remaining": 42}
    """
    try:
        remaining = check_ticket(start_station, end_station)
        return {"status": "success", "message": "查询成功", "remaining": remaining}
    except Exception as e:
        return {"status": "fail", "message": str(e), "remaining": None}


@mcp.tool()
def book_ticket_tool(start_station: str, end_station: str, num_seats: int) -> Dict[str, Any]:
    """
    订票操作，扣减票数，并返回标准化结果。

    Args:
        start_station (str): 出发城市，例如 "北京"
        end_station (str): 到达城市，例如 "上海"
        num_seats (int): 要预订的座位数量，例如 2

    Returns:
        dict: 返回标准化订票结果
            - status: "success" 或 "fail"
            - message: 信息描述
            - booked: 已成功预订票数，如果失败为 0

    Example:
        book_ticket_tool("北京", "上海", 2) ->
        {"status": "success", "message": "订票成功，扣减 2 张票", "booked": 2}
    """
    try:
        remaining = check_ticket(start_station, end_station)
        if remaining is None:
            return {"status": "fail", "message": "查询票数失败", "booked": 0}

        if num_seats > remaining:
            return {"status": "fail", "message": f"余票不足，仅剩 {remaining} 张", "booked": 0}

        book_ticket(start_station, end_station, num_seats)
        return {"status": "success", "message": f"订票成功，扣减 {num_seats} 张票", "booked": num_seats}
    except Exception as e:
        return {"status": "fail", "message": str(e), "booked": 0}


def main():
    """启动 MCP HTTP 服务"""
    mcp.run(transport="stdio")
	#

if __name__ == "__main__":
    main()