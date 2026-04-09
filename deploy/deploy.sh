#!/bin/bash
# 通用客户部署脚本
# 用法: ./deploy.sh <customer_name> <app_name> <acr_prefix> <image_tag>
set -e

CUSTOMER=$1
APP=$2
ACR_PREFIX=$3
TAG=${4:-latest}

if [ -z "$CUSTOMER" ] || [ -z "$APP" ] || [ -z "$ACR_PREFIX" ]; then
  echo "用法: $0 <customer_name> <app_name> <acr_prefix> [image_tag]"
  exit 1
fi

CONFIG_FILE="$(dirname "$0")/customers/${CUSTOMER}.env"
if [ ! -f "$CONFIG_FILE" ]; then
  echo "找不到客户配置文件: $CONFIG_FILE"
  exit 1
fi

source "$CONFIG_FILE"

DEPLOY_DIR=~/customers/$CUSTOMER/$APP
mkdir -p $DEPLOY_DIR

docker pull $ACR_PREFIX/$APP:$TAG

cat > $DEPLOY_DIR/.env << EOF
IMAGE=$ACR_PREFIX/$APP:$TAG
EOF

cat $CONFIG_FILE >> $DEPLOY_DIR/.env

docker compose -f $DEPLOY_DIR/docker-compose.prod.yml --env-file $DEPLOY_DIR/.env up -d --pull always

echo "等待服务启动..."
for i in $(seq 1 10); do
  if curl -sf http://localhost:${APP_PORT:-8003}/health > /dev/null 2>&1; then
    echo "✅ 服务健康检查通过"
    exit 0
  fi
  sleep 3
done

echo "❌ 健康检查失败，执行回滚"
docker compose -f $DEPLOY_DIR/docker-compose.prod.yml --env-file $DEPLOY_DIR/.env down
exit 1
