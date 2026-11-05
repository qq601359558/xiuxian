# 《天道因果录》游戏服镜像（NAS / Docker 部署，见 docs/nas-deploy.md）
# 构建：docker build -t tiandao .   或直接用 docker-compose.yml 一键构建启动
# 基础镜像 python:3.12-slim 为多架构镜像，群晖/威联通的 x86 与 ARM 机型都能拉到。
FROM python:3.12-slim

WORKDIR /app

# 先装依赖（单独成层：只改游戏代码时不用重装依赖）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝运行所需代码。data/、.env、tests/ 等由 .dockerignore 排除：
# 存档在运行时由 compose 把宿主机目录挂到 /app/data，不进镜像、升级不丢档；
# .env 由 compose 以 env_file 方式注入，密钥不进镜像。
COPY config.py ./
COPY ai/ ./ai/
COPY cli/ ./cli/
COPY core/ ./core/
COPY server/ ./server/
COPY storage/ ./storage/
COPY web/ ./web/
COPY tools/ ./tools/

# LAN_PORT 可被 compose / .env 覆盖；PYTHONUNBUFFERED 让日志实时输出到 docker logs
ENV LAN_PORT=8765 \
    PYTHONUNBUFFERED=1

EXPOSE 8765

CMD ["python", "-m", "server.run"]
