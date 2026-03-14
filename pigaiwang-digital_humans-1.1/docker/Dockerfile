FROM python:3.10-slim

WORKDIR /epc_backend

# 安装运行依赖

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 dmidecode
RUN apt-get update && apt-get install -y dmidecode && apt-get clean

# 复制代码
COPY . .

CMD ["python", "main.py"]

