# 使用官方 Node.js 20 Alpine 镜像作为基础镜像
FROM node:20-alpine AS base

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

# Next.js 在 Alpine 下常见的兼容性依赖
RUN apk add --no-cache libc6-compat

# 安装依赖阶段
FROM base AS deps

COPY package.json package-lock.json ./
RUN npm ci


# 构建阶段
FROM base AS builder

ENV NODE_ENV=production

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# 防止仓库没有 public/ 导致 COPY 失败
RUN mkdir -p public

RUN npm run build


# 生产运行阶段
FROM base AS runner

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# 创建 nextjs 用户
RUN addgroup --system --gid 1001 nodejs \
	&& adduser --system --uid 1001 nextjs

# 自动利用输出跟踪来减少镜像大小
# https://nextjs.org/docs/advanced-features/output-file-tracing
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

# 使用 standalone 输出启动服务器
CMD ["node", "server.js"]