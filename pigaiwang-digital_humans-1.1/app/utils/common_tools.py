"""通用工具函数模块.

提供常用的工具函数，包括：
- Excel和CSV文件解析功能
- 支持多种编码格式自动识别
- 文件格式验证和错误处理
- 数据行列筛选和限制
- 多工作表支持

使用pandas库进行文件解析，支持xlsx、xls、csv格式。
"""

import io
from typing import Optional

import pandas as pd


def parse_excels_file(
    file,
    max_count: Optional[int] = None,
    usecols: Optional[list[str]] = None,
    sheet_name: Optional[list[str | int]] = None,
):
    """通用解析excel文件的方法，以第一行为表头，后续行为数据行."""
    try:
        # 将文件内容读取到内存缓冲区中以避免 seek 相关问题
        contents = file.file.read()

        # 检查文件是否为空
        if not contents:
            return False, 400, "文件为空", None

        file_buffer = io.BytesIO(contents)

        if file.filename.endswith(".xlsx") or file.filename.endswith(".xls"):
            # 读取Excel文件
            try:
                if usecols is not None:
                    df = pd.read_excel(
                        file_buffer,
                        usecols=usecols,
                        sheet_name=sheet_name,
                        engine="openpyxl",
                    )
                else:
                    df = pd.read_excel(
                        file_buffer, sheet_name=sheet_name, engine="openpyxl"
                    )
            except Exception as excel_error:
                # 如果openpyxl失败，尝试不指定引擎
                try:
                    file_buffer.seek(0)
                    if usecols is not None:
                        df = pd.read_excel(
                            file_buffer, usecols=usecols, sheet_name=sheet_name
                        )
                    else:
                        df = pd.read_excel(file_buffer, sheet_name=sheet_name)
                except Exception:
                    return False, 400, f"无法解析Excel文件: {str(excel_error)}", None

        elif file.filename.endswith(".csv"):
            # 处理CSV文件，需要将其转换为文本流
            # 尝试多种编码方式
            encodings = ["utf-8", "gbk", "gb2312", "latin1"]
            df = None

            for encoding in encodings:
                try:
                    # 重新读取内容并尝试特定编码
                    text_content = contents.decode(encoding)
                    text_buffer = io.StringIO(text_content)

                    if usecols is not None:
                        df = pd.read_csv(text_buffer, usecols=usecols)
                    else:
                        df = pd.read_csv(text_buffer)
                    break  # 成功读取则跳出循环
                except (UnicodeDecodeError, UnicodeError):
                    continue

            if df is None:
                # 如果所有编码都失败，使用错误处理模式
                try:
                    text_content = contents.decode("utf-8", errors="ignore")
                    text_buffer = io.StringIO(text_content)
                    if usecols is not None:
                        df = pd.read_csv(text_buffer, usecols=usecols)
                    else:
                        df = pd.read_csv(text_buffer)
                except Exception:
                    return False, 500, "无法使用任何支持的编码读取CSV文件", None
        else:
            return False, 400, "不支持的文件格式，仅支持xlsx、xls、csv格式", None

        # 处理可能返回字典的情况（多个工作表）
        if isinstance(df, dict):
            # 如果返回的是字典，取第一个工作表的数据
            if df:
                # 获取第一个工作表
                first_sheet = next(iter(df))
                df = df[first_sheet]
            else:
                return False, 400, "Excel文件中没有找到有效的工作表", None

        # 检查DataFrame是否有效
        if df is None or df.empty:
            return False, 400, "文件中未包含任何有效的数据", None

        # 应用max_count限制
        if max_count is not None and max_count > 0:
            df = df.head(max_count)

        # 将DataFrame转换为字典列表
        data = df.to_dict(orient="records")
        if not data:  # 如果数据为空，则返回错误
            return False, 400, "文件中未包含任何有效的项目数据。", None
        return True, 200, "文件解析成功", data
    except Exception as e:
        return False, 500, f"文件解析失败: {str(e)}", None
