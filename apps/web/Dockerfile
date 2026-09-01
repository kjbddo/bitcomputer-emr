FROM node:22-slim AS deps

WORKDIR /app
COPY package*.json ./
RUN npm install

FROM node:22-slim AS build

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/package.json ./
COPY . .
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

# 이 배포에 AI 기능이 있는지. DR 구성은 false 로 빌드한다.
#
# NEXT_PUBLIC_ 값은 **빌드 시점에 번들에 박힌다.** 기동 시 환경변수만 바꿔서는
# 바뀌지 않으므로 build arg 로 받아야 한다 - 그래서 DR 프론트는 별도 이미지다.
# 기본값이 true 인 이유는 서버 쪽 AiFeatures 와 같다: 끄는 것이 명시적
# 선택이어야 하고, 설정 누락으로 조용히 사라지면 안 된다.
ARG NEXT_PUBLIC_AI_FEATURES_ENABLED=true
ENV NEXT_PUBLIC_AI_FEATURES_ENABLED=${NEXT_PUBLIC_AI_FEATURES_ENABLED}
RUN npm run build

FROM node:22-slim AS runner

WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public

EXPOSE 3000
CMD ["npm", "run", "start", "--", "-p", "3000"]
