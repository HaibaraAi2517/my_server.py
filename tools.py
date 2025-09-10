from db import get_db_connection

def check_ticket(start_station: str, end_station: str) -> int:
    """
    查询余票：按起始站和终点站统计状态为0（可用）的座位数量
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT COUNT(*) AS available_seats
                FROM t_seat
                WHERE seat_status=0
                  AND start_station=%s
                  AND end_station=%s
            """
            cursor.execute(sql, (start_station, end_station))
            result = cursor.fetchone()
            return result["available_seats"] if result else 0
    finally:
        conn.close()

def book_ticket(start_station: str, end_station: str, num_seats: int) -> str:
    """
    扣减票数：按起始站和终点站查询可用座位，将 seat_status 改为1
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 查询可用座位，并加锁
            cursor.execute(
                """
                SELECT id
                FROM t_seat
                WHERE seat_status=0
                  AND start_station=%s
                  AND end_station=%s
                LIMIT %s FOR UPDATE
                """,
                (start_station, end_station, num_seats)
            )
            seats = cursor.fetchall()

            if len(seats) < num_seats:
                return f"余票不足，当前可用 {len(seats)} 张票"

            # 扣票操作
            seat_ids = [str(seat['id']) for seat in seats]
            seat_ids_str = ",".join(seat_ids)
            update_sql = f"""
                UPDATE t_seat
                SET seat_status=1
                WHERE id IN ({seat_ids_str})
            """
            cursor.execute(update_sql)
            conn.commit()
            return f"订票成功，扣减 {num_seats} 张票"

    except Exception as e:
        conn.rollback()
        return f"订票失败: {e}"
    finally:
        conn.close()

