# 使用Python 3.12精简版作为基础镜像，减小镜像体积
FROM python:3.12-slim

# 设置工作目录为/app
WORKDIR /app

# 安装系统依赖
# apt-get update 更新包索引
# apt-get install -y gcc 安装gcc编译器(某些Python包需要)
# rm -rf 清理apt缓存以减小镜像体积
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements.txt到容器中
# 这一步单独执行是为了利用Docker的缓存机制
COPY requirements.txt .

# 安装Python依赖包
# --no-cache-dir 不缓存下载的包,减小镜像体积
RUN pip install --no-cache-dir -r requirements.txt

# 将当前目录下的所有文件复制到容器的工作目录
COPY . .

# 设置环境变量
# PYTHONPATH用于Python查找模块
# ENV设置为prod表示生产环境
ENV PYTHONPATH=/app
ENV ENV=prod

# 创建logs目录用于存放日志文件
RUN mkdir -p /app/logs

# 容器启动时执行的命令
# 运行main.py启动应用
CMD ["python", "main.py"] 