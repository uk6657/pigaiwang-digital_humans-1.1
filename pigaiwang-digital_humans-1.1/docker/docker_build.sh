#!/usr/bin/env bash

set -e

#############################################
# 配置区（你可自定义）
#############################################

IMAGE_NAME_SOURCE="epc-backend-source"
IMAGE_NAME_COMPILED="epc-backend"

KEEP_FILES=(
    "Dockerfile"
    ".dockerignore"
    "docker_build.sh"
)

#############################################
# 不要修改以下逻辑
#############################################

DOCKER_DIR="$(dirname "$0")"

# 定义颜色用于警告
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo "================================================="
echo "  Docker 构建脚本 (Backend)"
echo "================================================="
echo "请选择构建类型："
echo "  1) 源码构建（source）"
echo "  2) 编译后构建（compiled）"
echo "-------------------------------------------------"

read -p "请输入选项 (1 或 2)： " OPTION

if [ "$OPTION" = "1" ]; then
    MODE="source"
    IMAGE_NAME=$IMAGE_NAME_SOURCE
elif [ "$OPTION" = "2" ]; then
    MODE="compiled"
    IMAGE_NAME=$IMAGE_NAME_COMPILED
else
    echo "❌ 输入无效，请输入 1 或 2"
    exit 1
fi

echo "-------------------------------------------------"
read -p "请输入镜像 tag： " TAG

if [ -z "$TAG" ]; then
    echo "❌ tag 不能为空"
    exit 1
fi

echo "-------------------------------------------------"
echo "构建配置："
echo " 构建类型 ：$MODE"
echo " 镜像名称 ：$IMAGE_NAME"
echo " 镜像 tag ：$TAG"
echo "-------------------------------------------------"

read -p "确认开始构建吗？ (y/N): " CONFIRM

if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo "🛑 构建已取消"
    exit 0
fi


#############################################
# 🔥 构建前清除 docker 目录（保留必须文件）
#############################################

echo "================================================="
echo " 🔥 清理 docker 目录..."
echo "================================================="

cd "$DOCKER_DIR"

KEEP_SET=$(printf "%s\n" "${KEEP_FILES[@]}")

for ITEM in * .*; do
    if [[ "$ITEM" = "." || "$ITEM" = ".." ]]; then
        continue
    fi
    if echo "$KEEP_SET" | grep -qx "$ITEM"; then
        continue
    fi
    rm -rf "$ITEM"
done


#############################################
# 📦 复制构建内容到 docker 根目录
#############################################

if [ "$MODE" = "source" ]; then
    # ---------------------------------------------------------
    # 🚨 安全修改：源码构建时的显眼警告与二次确认
    # ---------------------------------------------------------
    echo -e "${RED}===================================================================${NC}"
    echo -e "${RED} 🚨 严重警告：您正在构建【源码镜像】(epc-backend-source)！${NC}"
    echo -e "${RED} 🚨 该镜像将包含所有未编译的 .py 源代码。${NC}"
    echo -e "${RED} 🚨 请确保此镜像仅用于开发/测试，严禁用于交付或公开！${NC}"
    echo -e "${RED}===================================================================${NC}"
    
    read -p "⚠️  如果您清楚自己在做什么，请输入 'yes' 继续: " SOURCE_CONFIRM

    if [ "$SOURCE_CONFIRM" != "yes" ]; then
        echo "🛑 用户取消，已停止构建以防止源码泄露。"
        exit 1
    fi

    echo "📦 正在复制源码..."

    cp -r ../app .
    cp -r ../conf .
    cp ../main.py .
    cp ../requirements.txt .

    echo "================================================="
    echo " ✅ 源码复制完成"
    echo "================================================="
fi

if [ "$MODE" = "compiled" ]; then
    echo "⚙️ 正在复制编译后内容..."

    cp -r ../build/compiled/app .
    cp -r ../build/compiled/conf .
    # 注意：此处先不复制 main.py
    cp ../build/compiled/requirements.txt .

    # ---------------------------------------------------------
    # 🚨 安全修改：先检查已复制文件中是否混入 .py，最后再复制 main.py
    # ---------------------------------------------------------
    echo "🔍 正在严格检查编译产物是否混入源代码..."

    # 此时目录下还没有 main.py，所以理论上不应该存在任何 .py 文件
    EXTRA_PY_FILES=$(find . -type f -name "*.py")

    if [ -n "$EXTRA_PY_FILES" ]; then
        echo -e "${RED}❌ 严重错误：检测到编译产物中包含以下未编译的 .py 文件！${NC}"
        echo -e "${YELLOW}------------------------------------------------${NC}"
        echo "$EXTRA_PY_FILES"
        echo -e "${YELLOW}------------------------------------------------${NC}"
        echo -e "${RED}🛑 构建已强制终止。请检查 build/compiled 目录清理是否彻底。${NC}"
        exit 1
    fi

    echo "✅ 检查通过：未发现残留源代码。"

    # 检查通过后，最后复制 main.py
    echo "📄 最后复制入口文件 main.py ..."
    cp ../build/compiled/main.py .
fi


#############################################
# 🚀 构建 Docker 镜像
#############################################

echo "================================================="
echo " 🚀 构建镜像：$IMAGE_NAME:$TAG"
echo "================================================="

docker build -t "${IMAGE_NAME}:${TAG}" "$DOCKER_DIR"

echo "================================================="
echo " 🎉 构建完成：${IMAGE_NAME}:${TAG}"
echo "================================================="

if [ "$MODE" = "source" ]; then
    echo -e "${RED}===================================================================${NC}"
    echo -e "${RED}        🚨 这他妈是源代码镜像，千万别泄露!!!!!!!!!!!!!!!!${NC}"
    echo -e "${RED}===================================================================${NC}"
fi