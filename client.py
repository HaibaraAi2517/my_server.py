import asyncio
import json
import regex as re
from typing import Dict, Any, List, Optional
from fastmcp import Client
import ollama

# -----------------------
# 工具信息定义
# -----------------------
TOOLS_INFO: Dict[str, Dict[str, Any]] = {
    "check_ticket_tool": {
        "description": "查询余票",
        "params": {"start_station": "string", "end_station": "string"}
    },
    "book_ticket_tool": {
        "description": "订票",
        "params": {"start_station": "string", "end_station": "string", "num_seats": "int"}
    }
}

# -----------------------
# Ollama 模型选择
# -----------------------
def select_ollama_model() -> str:
    models = ollama.list().get("models", [])
    if not models:
        raise RuntimeError("未检测到任何 Ollama 模型，请先用 `ollama pull <model>` 下载")

    print("\n检测到的本地模型:")
    for i, m in enumerate(models, 1):
        print(f"{i}. {m['model']}")

    while True:
        choice = input(f"请选择要使用的模型 [1-{len(models)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(models):
            return models[int(choice) - 1]["model"]
        print("输入无效，请重新选择。")

# -----------------------
# 用户意图映射工具
# -----------------------
def map_intent_to_tool(user_input: str) -> Optional[str]:
    user_input = user_input.lower()
    if any(k in user_input for k in ["查询", "余票"]):
        return "check_ticket_tool"
    if any(k in user_input for k in ["订票", "买票", "购买"]):
        return "book_ticket_tool"
    return None

# -----------------------
# Ollama 解析用户输入
# -----------------------
def parse_user_input_local(
    user_input: str,
    provided_params: Optional[Dict[str, Any]] = None,
    memory_pool: Optional[List[Dict[str, Any]]] = None,
    model_name: str = "llama2"
) -> (str, Dict[str, Any], List[str]):
    provided_params = provided_params or {}
    memory_pool = memory_pool or []

    prompt = f"你是 MCP 助手，将用户自然语言意图转换为 MCP 工具调用。\n已知工具: {list(TOOLS_INFO.keys())}\n"
    for t, info in TOOLS_INFO.items():
        prompt += f"{t}({', '.join([f'{k}:{v}' for k,v in info['params'].items()])}): {info['description']}\n"

    if memory_pool:
        prompt += "\n最近的调用历史:\n"
        for i, ctx in enumerate(memory_pool[-5:], 1):
            prompt += f"{i}. 工具={ctx['tool_name']} 参数={ctx['params']}\n"

    prompt += f"""
用户输入: "{user_input}"
当前已提供参数: {provided_params}

指南：
1. 查询票余量 → check_ticket_tool
2. 订票 → book_ticket_tool
3. 只输出 JSON，工具名称必须严格从以上列表选择
4. params 必须是字典
5. 不要输出任何解释文字或 <think> 标签
6. 示例格式:
{{"tool_name": "check_ticket_tool", "params": {{"start_station": "北京", "end_station": "上海"}}, "missing_params": []}}
"""

    response = ollama.chat(model=model_name, messages=[{"role": "user", "content": prompt}])
    text = response["message"]["content"]

    # -------------------------------
    # 安全提取 JSON
    # -------------------------------
    # 提取最外层大括号 JSON（支持嵌套）
    match = re.search(r"\{(?:[^{}]|(?R))*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"解析失败，未找到 JSON: {text}")

    json_str = match.group(0)

    # 替换全角逗号
    json_str = json_str.replace("，", ",")

    # 去掉注释
    json_str = re.sub(r"//.*", "", json_str)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # 备用方法：安全的 literal_eval
        import ast
        try:
            data = ast.literal_eval(json_str)
        except Exception as e:
            raise ValueError(f"解析失败: {e}, 模型输出: {text}")

    # -------------------------------
    # 解析工具名、参数、缺失参数
    # -------------------------------
    tool_name = data["tool_name"]
    params = data.get("params", {})

    missing = data.get("missing_params")
    if not isinstance(missing, list):
        missing = [k for k in TOOLS_INFO[tool_name]["params"] if k not in params]

    # 自动转换列表形式 params
    if not isinstance(params, dict):
        param_names = list(TOOLS_INFO[tool_name]["params"].keys())
        if isinstance(params, list) and len(params) == len(param_names):
            params = dict(zip(param_names, params))
        else:
            raise ValueError(f"params 类型不正确且无法自动转换: {params}")

    return tool_name, params, missing


# -----------------------
# 补全缺失参数
# -----------------------
def fill_missing_params(tool_name: str, missing: List[str], history: Dict[str, Any]) -> Dict[str, Any]:
    params = {}
    for param in missing:
        expected_type = TOOLS_INFO[tool_name]['params'][param]
        default_value = history.get(param)
        while True:
            prompt = f"请输入 {param} ({expected_type})"
            if default_value is not None:
                prompt += f" [默认: {default_value}]"
            prompt += ": "
            value = input(prompt).strip()
            if value == "" and default_value is not None:
                value = default_value
            try:
                if expected_type == "int":
                    value = int(value)
                elif expected_type == "float":
                    value = float(value)
            except ValueError:
                print(f"输入类型错误，应为 {expected_type}，请重新输入。")
                continue
            params[param] = value
            history[param] = value
            break
    return params

# -----------------------
# 工具调用
# -----------------------
async def call_tool(client: Client, tool_name: str, params: Dict[str, Any]) -> Any:
    try:
        result = await client.call_tool(tool_name, params)
        return result.data
    except Exception as e:
        return f"调用失败: {e}"

# -----------------------
# 智能补全缺失站点
# -----------------------
def smart_fill_stations(tool_name: str, params: Dict[str, Any], history: Dict[str, Any]) -> Dict[str, Any]:
    """
    自动补全缺失的 start_station 和 end_station。
    优先使用最近历史记录，如果历史中没有值才提示用户输入。
    """
    for station_param in ["start_station", "end_station"]:
        if station_param not in params or not params[station_param]:
            # 尝试从 history 中补全
            if station_param in history and history[station_param]:
                params[station_param] = history[station_param]
            else:
                # 历史没有值，再提示用户输入
                value = input(f"请输入 {station_param} (string): ").strip()
                params[station_param] = value
                history[station_param] = value
    return params



def extract_num_seats(user_input: str) -> Optional[int]:
    """
    从用户输入中提取票数，例如:
    "买两张票" -> 2
    "购买3张票" -> 3
    """
    # 先尝试提取数字
    match = re.search(r'(\d+)', user_input)
    if match:
        return int(match.group(1))

    # 中文数字转换
    cn_nums = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
               '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
    for cn, num in cn_nums.items():
        if cn + "张" in user_input:
            return num
        if cn in user_input:
            return num
    return None

# -----------------------
# 主循环
# -----------------------
async def main():
    model_name = select_ollama_model()
    print(f"\n已选择模型: {model_name}")

    async with Client("http://localhost:8000/mcp") as client:
        print("智能 MCP 客户端已启动。输入 'quit' 退出")

        memory_pool: List[Dict[str, Any]] = []
        history: Dict[str, Any] = {}
        MAX_MEMORY = 5

        while True:
            user_input = input("\n你: ").strip()
            if user_input.lower() == "quit":
                print("退出客户端")
                break

            try:
                tool_name, params, missing = parse_user_input_local(
                    user_input, {}, memory_pool, model_name
                )

                # 根据关键词修正工具
                tool_override = map_intent_to_tool(user_input)
                if tool_override:
                    tool_name = tool_override

                # 补全缺失参数
                if missing:
                    new_params = fill_missing_params(tool_name, missing, history)
                    params.update(new_params)

                # 智能补全站点和票数
                if tool_name == "book_ticket_tool":
                    params = smart_fill_stations(tool_name, params, history)

                    # 自动解析票数
                    if "num_seats" not in params:
                        num = extract_num_seats(user_input)
                        if num is not None:
                            params["num_seats"] = num
                            history["num_seats"] = num

                # 补全历史参数
                for k, v in history.items():
                    if k in TOOLS_INFO[tool_name]["params"]:
                        params.setdefault(k, v)

                # 检查必填参数
                for required_param in TOOLS_INFO[tool_name]["params"]:
                    if required_param not in params:
                        raise ValueError(f"缺少必填参数: {required_param}")

                # 调用 MCP
                result = await call_tool(client, tool_name, params)
                print(f"调用结果: {result}")

                # 更新记忆池
                memory_pool.append({"tool_name": tool_name, "params": params})
                if len(memory_pool) > MAX_MEMORY:
                    memory_pool.pop(0)
                history.update(params)

            except Exception as e:
                print(f"处理失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())
